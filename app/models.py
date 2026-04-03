from sqlalchemy import Column, Integer, String, Float
from .database import Base

class SalesRecord(Base):
    __tablename__ = "sales_records"
    id = Column(Integer, primary_key=True, index=True)
    order_date = Column(String, index=True)
    raw_product_name = Column(String, index=True)
    normalized_product_name = Column(String, index=True)
    qty = Column(Float, default=0)
    amount = Column(Float, default=0)
    customer_name = Column(String, index=True)
    customer_phone = Column(String, index=True)
    customer_email = Column(String, index=True)
    order_status = Column(String, index=True)
    payment_status = Column(String, index=True)

class InventoryRecord(Base):
    __tablename__ = "inventory_records"
    id = Column(Integer, primary_key=True, index=True)
    raw_product_name = Column(String, index=True)
    normalized_product_name = Column(String, index=True)
    inventory_qty = Column(Float, default=0)

class UploadBatch(Base):
    __tablename__ = "upload_batches"
    id = Column(Integer, primary_key=True, index=True)
    uploaded_at = Column(String, index=True)
    order_file_name = Column(String)
    inventory_file_name = Column(String)
    status = Column(String, default="success")
