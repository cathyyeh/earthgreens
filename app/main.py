from pathlib import Path
from collections import defaultdict, Counter
from fastapi import FastAPI, Request, UploadFile, File, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import SalesRecord, InventoryRecord, UploadBatch
from .importer import import_files

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Earth Greens Dashboard v31")
templates = Jinja2Templates(directory="app/templates")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

def customer_key(r):
    if r.customer_email:
        return ("email", r.customer_email.lower())
    if r.customer_phone:
        return ("phone", r.customer_phone)
    return ("name", r.customer_name)

@app.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse(url="/dashboard")

@app.get("/admin/upload", response_class=HTMLResponse)
def upload_page(request: Request, db: Session = Depends(get_db)):
    latest = db.query(UploadBatch).order_by(UploadBatch.id.desc()).first()
    return templates.TemplateResponse("upload.html", {"request": request, "latest": latest})

@app.post("/admin/upload", response_class=HTMLResponse)
async def upload_files(request: Request, order_file: UploadFile = File(...), inventory_file: UploadFile = File(...), db: Session = Depends(get_db)):
    order_path = UPLOAD_DIR / order_file.filename
    inventory_path = UPLOAD_DIR / inventory_file.filename
    with open(order_path, "wb") as f:
        f.write(await order_file.read())
    with open(inventory_path, "wb") as f:
        f.write(await inventory_file.read())
    import_files(db, str(order_path), str(inventory_path))
    latest = db.query(UploadBatch).order_by(UploadBatch.id.desc()).first()
    return templates.TemplateResponse("upload.html", {"request": request, "latest": latest, "message": "資料已更新成功"})

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, start_date: str | None = Query(default=None), end_date: str | None = Query(default=None), product: str | None = Query(default=None), db: Session = Depends(get_db)):
    all_sales = db.query(SalesRecord).all()
    all_inventory = db.query(InventoryRecord).all()
    latest = db.query(UploadBatch).order_by(UploadBatch.id.desc()).first()

    all_products = sorted(set([x.normalized_product_name for x in all_sales] + [x.normalized_product_name for x in all_inventory]))
    all_dates = sorted(set([x.order_date for x in all_sales]))
    if not start_date and all_dates:
        start_date = all_dates[0]
    if not end_date and all_dates:
        end_date = all_dates[-1]

    sales = [x for x in all_sales if (not start_date or x.order_date >= start_date) and (not end_date or x.order_date <= end_date) and (not product or x.normalized_product_name == product)]
    inventory = [x for x in all_inventory if (not product or x.normalized_product_name == product)]

    revenue = sum(x.amount for x in sales)
    qty = sum(x.qty for x in sales)
    orders = len(sales)

    by_date = defaultdict(float)
    by_product = defaultdict(lambda: {"amount": 0.0, "qty": 0.0, "orders": 0, "inventory_qty": 0.0})
    by_quarter_amount = defaultdict(float)
    by_quarter_qty = defaultdict(float)

    for s in sales:
        by_date[s.order_date] += s.amount
        by_product[s.normalized_product_name]["amount"] += s.amount
        by_product[s.normalized_product_name]["qty"] += s.qty
        by_product[s.normalized_product_name]["orders"] += 1
        year = s.order_date.split("-")[0]
        month = int(s.order_date.split("-")[1])
        q = f"Q{((month - 1) // 3) + 1}"
        key = f"{year} {q}"
        by_quarter_amount[key] += s.amount
        by_quarter_qty[key] += s.qty

    for i in inventory:
        by_product[i.normalized_product_name]["inventory_qty"] += i.inventory_qty

    product_rows = [{"product": k, **v} for k, v in by_product.items()]
    product_rows.sort(key=lambda x: x["amount"], reverse=True)

    inventory_rows = [{"product": i.normalized_product_name, "inventory_qty": i.inventory_qty} for i in inventory]
    inventory_rows.sort(key=lambda x: x["inventory_qty"], reverse=True)

    valid_customer_sales = [s for s in sales if ("完成" in s.order_status or s.order_status == "") and ("付款" in s.payment_status or "已付款" in s.payment_status or s.payment_status == "")]
    customers = {}
    for s in valid_customer_sales:
        key = customer_key(s)
        if key not in customers:
            customers[key] = {
                "name": s.customer_name or key[1],
                "identifier": s.customer_email or s.customer_phone or s.customer_name,
                "orders": 0,
                "qty": 0.0,
                "revenue": 0.0,
                "products": Counter()
            }
        customers[key]["orders"] += 1
        customers[key]["qty"] += s.qty
        customers[key]["revenue"] += s.amount
        customers[key]["products"][s.normalized_product_name] += s.qty

    unique_customer_count = len(customers)
    top_customers = []
    for c in customers.values():
        fav = c["products"].most_common(1)
        favorite_product = fav[0][0] if fav else ""
        top_customers.append({
            "name": c["name"],
            "identifier": c["identifier"],
            "orders": c["orders"],
            "qty": c["qty"],
            "revenue": c["revenue"],
            "favorite_product": favorite_product
        })
    top_customers.sort(key=lambda x: x["revenue"], reverse=True)
    top_customers = top_customers[:10]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "latest": latest,
        "revenue": revenue,
        "qty": qty,
        "orders": orders,
        "product_rows": product_rows,
        "inventory_rows": inventory_rows,
        "all_products": all_products,
        "daily_labels": list(by_date.keys()),
        "daily_values": list(by_date.values()),
        "quarter_labels": list(by_quarter_amount.keys()),
        "quarter_values": list(by_quarter_amount.values()),
        "quarter_qty_values": list(by_quarter_qty.values()),
        "selected_start": start_date or "",
        "selected_end": end_date or "",
        "selected_product": product or "",
        "unique_customer_count": unique_customer_count,
        "top_customers": top_customers
    })
