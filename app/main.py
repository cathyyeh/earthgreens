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
app = FastAPI(title="Earth Greens Dashboard v31.6")
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
        key = f"{y} Q{((m-1)//3)+1}"
        by_quarter_amount[key] += s.amount
        by_quarter_qty[key] += s.qty
    for i in inventory:
        by_product[i.normalized_product_name]["inventory_qty"] += i.inventory_qty
    product_rows = [{"product": k, **v} for k, v in by_product.items()]
    product_rows.sort(key=lambda x: x["amount"], reverse=True)
    valid_customer_sales = [s for s in sales if ("完成" in s.order_status or s.order_status == "") and ("付款" in s.payment_status or "已付款" in s.payment_status or s.payment_status == "")]
    customers, first_purchase_month, first_purchase_date = {}, {}, {}
    customer_month_orders = defaultdict(lambda: defaultdict(int))
    for s in valid_customer_sales:
        key = customer_key(s)
        month = s.order_date[:7]
        customer_month_orders[key][month] += 1
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
    new_customer_by_month, repeat_customer_by_month = defaultdict(int), defaultdict(int)
    segment_counts = {"只買1次": 0, "2-3次": 0, "4次以上": 0}
    new_customer_revenue = 0.0
    repeat_customer_revenue = 0.0
    repeat_customer_count = 0
    for k, c in customers.items():
        new_customer_by_month[first_purchase_month[k]] += 1
        if c["orders"] > 1: repeat_customer_count += 1
        if c["orders"] == 1: segment_counts["只買1次"] += 1
        elif 2 <= c["orders"] <= 3: segment_counts["2-3次"] += 1
        else: segment_counts["4次以上"] += 1
    for k, month_counts in customer_month_orders.items():
        ordered_months = sorted(month_counts.keys())
        if len(ordered_months) >= 2:
            for m in ordered_months[1:]:
                repeat_customer_by_month[m] += 1
    for s in valid_customer_sales:
        key = customer_key(s)
        if s.order_date == first_purchase_date[key]: new_customer_revenue += s.amount
        else: repeat_customer_revenue += s.amount
    unique_customer_count = len(customers)
    repurchase_rate = (repeat_customer_count / unique_customer_count * 100) if unique_customer_count else 0
    top_customers = []
    for c in customers.values():
        fav = c["products"].most_common(1)
        top_customers.append({"name": c["name"], "identifier": c["identifier"], "orders": c["orders"], "qty": c["qty"], "revenue": c["revenue"], "favorite_product": fav[0][0] if fav else ""})
    top_customers.sort(key=lambda x: x["revenue"], reverse=True)
    top_customers = top_customers[:10]
    return templates.TemplateResponse("dashboard.html", {"request": request, "latest": latest, "revenue": revenue, "qty": qty, "orders": orders, "product_rows": product_rows, "all_products": all_products, "daily_labels": list(by_date.keys()), "daily_values": list(by_date.values()), "quarter_labels": list(by_quarter_amount.keys()), "quarter_values": list(by_quarter_amount.values()), "quarter_qty_values": list(by_quarter_qty.values()), "new_customer_month_labels": sorted(new_customer_by_month.keys()), "new_customer_month_values": [new_customer_by_month[k] for k in sorted(new_customer_by_month.keys())], "repeat_customer_month_labels": sorted(repeat_customer_by_month.keys()), "repeat_customer_month_values": [repeat_customer_by_month[k] for k in sorted(repeat_customer_by_month.keys())], "new_vs_repeat_labels": ["新客營收", "舊客營收"], "new_vs_repeat_values": [new_customer_revenue, repeat_customer_revenue], "segment_labels": list(segment_counts.keys()), "segment_values": list(segment_counts.values()), "selected_start": start_date or "", "selected_end": end_date or "", "selected_product": product or "", "unique_customer_count": unique_customer_count, "repurchase_rate": repurchase_rate, "top_customers": top_customers})
