from pathlib import Path
from datetime import datetime
import pandas as pd
from .normalizer import normalize_product, is_excluded_sales_product, is_excluded_inventory_product
from .models import SalesRecord, InventoryRecord, UploadBatch

def find_col(cols, candidates):
    for cand in candidates:
        for c in cols:
            if cand in str(c).lower():
                return c
    return None

def import_files(db, order_file_path: str, inventory_file_path: str):
    order_path = Path(order_file_path)
    inventory_path = Path(inventory_file_path)

    sales_raw = pd.read_excel(order_path)
    sales_raw.columns = [str(c).strip() for c in sales_raw.columns]
    date_col = find_col(sales_raw.columns, ["日期", "date", "下單", "created", "order"])
    product_col = find_col(sales_raw.columns, ["品項", "商品", "product", "名稱", "品名"])
    qty_col = find_col(sales_raw.columns, ["數量", "件數", "qty", "quantity"])
    amount_col = find_col(sales_raw.columns, ["金額", "總額", "小計", "amount", "total", "營收"])

    sales = sales_raw[[date_col, product_col, qty_col, amount_col]].copy()
    sales.columns = ["date", "product_raw", "qty", "amount"]
    sales["date"] = pd.to_datetime(sales["date"], errors="coerce")
    sales = sales.dropna(subset=["date", "product_raw"]).copy()
    sales["product_raw"] = sales["product_raw"].astype(str).str.strip()
    sales = sales[~sales["product_raw"].map(is_excluded_sales_product)].copy()
    sales["qty"] = pd.to_numeric(sales["qty"], errors="coerce").fillna(0)
    sales["amount"] = pd.to_numeric(sales["amount"], errors="coerce").fillna(0)
    sales["product"] = sales["product_raw"].map(normalize_product)
    sales = sales[sales["product"].notna()].copy()
    sales["date_str"] = sales["date"].dt.strftime("%Y-%m-%d")

    inv_raw = pd.read_excel(inventory_file_path, sheet_name="成品即時庫存", header=3)
    inv_raw.columns = [str(c).strip().replace("\n", "") for c in inv_raw.columns]
    prod_col = next((c for c in inv_raw.columns if "品名" in c), inv_raw.columns[1])
    stock_col = next((c for c in inv_raw.columns if "即期庫存" in c), None)

    inventory = inv_raw[[prod_col, stock_col]].copy()
    inventory.columns = ["product_raw", "inventory_qty"]
    inventory["product_raw"] = inventory["product_raw"].astype(str).str.strip()
    inventory = inventory[(inventory["product_raw"] != "") & (inventory["product_raw"].str.lower() != "nan")].copy()
    inventory = inventory[~inventory["product_raw"].map(is_excluded_inventory_product)].copy()
    inventory["inventory_qty"] = pd.to_numeric(inventory["inventory_qty"], errors="coerce").fillna(0)
    inventory["product"] = inventory["product_raw"].map(normalize_product)
    inventory = inventory[inventory["product"].notna()].copy()

    db.query(SalesRecord).delete()
    db.query(InventoryRecord).delete()

    for _, row in sales.iterrows():
        db.add(SalesRecord(
            order_date=row["date_str"],
            raw_product_name=row["product_raw"],
            normalized_product_name=row["product"],
            qty=float(row["qty"]),
            amount=float(row["amount"]),
        ))

    grouped_inventory = inventory.groupby("product", as_index=False)["inventory_qty"].sum()
    for _, row in grouped_inventory.iterrows():
        db.add(InventoryRecord(
            raw_product_name=row["product"],
            normalized_product_name=row["product"],
            inventory_qty=float(row["inventory_qty"]),
        ))

    db.add(UploadBatch(
        uploaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        order_file_name=order_path.name,
        inventory_file_name=inventory_path.name,
        status="success"
    ))
    db.commit()
