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
app = FastAPI(title="Earth Greens Dashboard v32.1")
templates = Jinja2Templates(directory="app/templates")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
def customer_key(r):
    if r.customer_email: return ("email", r.customer_email.lower())
    if r.customer_phone: return ("phone", r.customer_phone)
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
    with open(order_path, "wb") as f: f.write(await order_file.read())
    with open(inventory_path, "wb") as f: f.write(await inventory_file.read())
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
    if not start_date and all_dates: start_date = all_dates[0]
    if not end_date and all_dates: end_date = all_dates[-1]
    sales = [x for x in all_sales if (not start_date or x.order_date >= start_date) and (not end_date or x.order_date <= end_date) and (not product or x.normalized_product_name == product)]
    inventory = [x for x in all_inventory if (not product or x.normalized_product_name == product)]
    revenue = sum(x.amount for x in sales)
    qty = sum(x.qty for x in sales)
    orders = len(sales)
    by_date, by_quarter_amount, by_quarter_qty = defaultdict(float), defaultdict(float), defaultdict(float)
    by_product = defaultdict(lambda: {"amount": 0.0, "qty": 0.0, "orders": 0, "inventory_qty": 0.0})
    for s in sales:
        by_date[s.order_date] += s.amount
        by_product[s.normalized_product_name]["amount"] += s.amount
        by_product[s.normalized_product_name]["qty"] += s.qty
        by_product[s.normalized_product_name]["orders"] += 1
        y = s.order_date.split("-")[0]
        m = int(s.order_date.split("-")[1])
        q = f"Q{((m-1)//3)+1}"
        by_quarter_amount[f"{y} {q}"] += s.amount
        by_quarter_qty[f"{y} {q}"] += s.qty
    for i in inventory:
        by_product[i.normalized_product_name]["inventory_qty"] += i.inventory_qty
    quarter_labels = sorted(by_quarter_amount.keys())
    quarter_values = [by_quarter_amount[k] for k in quarter_labels]
    quarter_qty_values = [by_quarter_qty[k] for k in quarter_labels]
    yoy_values = []
    for lbl in quarter_labels:
        year, q = lbl.split()
        prev = f"{int(year)-1} {q}"
        prev_val = by_quarter_amount.get(prev, 0)
        curr_val = by_quarter_amount.get(lbl, 0)
        yoy_values.append(round((curr_val-prev_val)/prev_val*100,1) if prev_val > 0 else None)
    valid_customer_sales = [s for s in sales if ("完成" in s.order_status or s.order_status == "") and ("付款" in s.payment_status or "已付款" in s.payment_status or s.payment_status == "")]
    customers, first_purchase_month, first_purchase_date = {}, {}, {}
    repeat_customer_by_month = defaultdict(int)
    new_customer_by_month = defaultdict(int)
    repeat_customer_revenue = 0.0
    new_customer_revenue = 0.0
    segment_counts = {"只買1次": 0, "2-3次": 0, "4次以上": 0}
    customer_months = defaultdict(set)
    for s in valid_customer_sales:
        key = customer_key(s)
        month = s.order_date[:7]
        customer_months[key].add(month)
        if key not in customers:
            customers[key] = {"name": s.customer_name or key[1], "identifier": s.customer_email or s.customer_phone or s.customer_name, "orders": 0, "qty": 0.0, "revenue": 0.0, "products": Counter()}
            first_purchase_month[key] = month
            first_purchase_date[key] = s.order_date
        elif s.order_date < first_purchase_date[key]:
            first_purchase_date[key] = s.order_date
            first_purchase_month[key] = month
        customers[key]["orders"] += 1
        customers[key]["qty"] += s.qty
        customers[key]["revenue"] += s.amount
        customers[key]["products"][s.normalized_product_name] += s.qty
    for k, c in customers.items():
        new_customer_by_month[first_purchase_month[k]] += 1
        ordered_months = sorted(customer_months[k])
        if len(ordered_months) > 1:
            for m in ordered_months[1:]:
                repeat_customer_by_month[m] += 1
        if c["orders"] == 1: segment_counts["只買1次"] += 1
        elif 2 <= c["orders"] <= 3: segment_counts["2-3次"] += 1
        else: segment_counts["4次以上"] += 1
    for s in valid_customer_sales:
        key = customer_key(s)
        if s.order_date == first_purchase_date[key]: new_customer_revenue += s.amount
        else: repeat_customer_revenue += s.amount
    top_customers = []
    for c in customers.values():
        fav = c["products"].most_common(1)
        top_customers.append({"name": c["name"], "identifier": c["identifier"], "orders": c["orders"], "qty": c["qty"], "revenue": c["revenue"], "favorite_product": fav[0][0] if fav else ""})
    top_customers.sort(key=lambda x: x["revenue"], reverse=True)
    top_customers = top_customers[:10]
    product_rows = [{"product": k, **v} for k, v in by_product.items()]
    product_rows.sort(key=lambda x: x["amount"], reverse=True)
    return templates.TemplateResponse("dashboard.html", {"request": request, "latest": latest, "revenue": revenue, "qty": qty, "orders": orders, "product_rows": product_rows, "all_products": all_products, "daily_labels": list(by_date.keys()), "daily_values": list(by_date.values()), "quarter_labels": quarter_labels, "quarter_values": quarter_values, "quarter_qty_values": quarter_qty_values, "quarter_yoy_values": yoy_values, "segment_labels": list(segment_counts.keys()), "segment_values": list(segment_counts.values()), "new_customer_month_labels": sorted(new_customer_by_month.keys()), "new_customer_month_values": [new_customer_by_month[k] for k in sorted(new_customer_by_month.keys())], "repeat_customer_month_labels": sorted(repeat_customer_by_month.keys()), "repeat_customer_month_values": [repeat_customer_by_month[k] for k in sorted(repeat_customer_by_month.keys())], "new_vs_repeat_labels": ["新客營收", "舊客營收"], "new_vs_repeat_values": [new_customer_revenue, repeat_customer_revenue], "selected_start": start_date or "", "selected_end": end_date or "", "selected_product": product or "", "unique_customer_count": len(customers), "top_customers": top_customers})
