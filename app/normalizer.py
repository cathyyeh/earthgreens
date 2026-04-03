import re
EXCLUDED = {"品名", "吉安農會暫存品", "B70 P80", "總計", "", "nan"}

def is_excluded_sales_product(name: str) -> bool:
    s = str(name).strip()
    if s in EXCLUDED:
        return True
    patterns = [r"20\d{2}", r"\d{1,2}[/-]\d{1,2}", r"\d{4}[/-]\d{1,2}", r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", r"月份", r"期初庫存", r"全年出貨", r"帳上", r"庫存#", r"^#dt$"]
    return any(re.search(p, s.lower()) for p in patterns)

def is_excluded_inventory_product(name: str) -> bool:
    s = str(name).strip()
    if s in EXCLUDED:
        return True
    keep_keywords = ["紫蘇茶包", "紫蘇", "按摩油", "精華油", "頭皮調理液", "潔顏液", "純露", "凝露", "福袋"]
    if any(k in s for k in keep_keywords):
        return False
    patterns = [r"月份", r"期初庫存", r"全年出貨", r"帳上", r"庫存#", r"^#dt$"]
    return any(re.search(p, s.lower()) for p in patterns)

def normalize_product(name: str):
    s = str(name).strip()
    if s == "總計":
        return None
    mapping = {"紫蘇。植萃純露": "紫蘇植萃純露[100ml]", "紫蘇。潔顏液": "紫蘇潔顏液[100ml]", "紫蘇。潤澤凝露": "紫蘇潤澤凝露[100ml]"}
    if s in mapping:
        return mapping[s]
    if "紫蘇植萃純露" in s: return "紫蘇植萃純露[100ml]"
    if "紫蘇潔顏液" in s: return "紫蘇潔顏液[100ml]"
    if "紫蘇潤澤凝露" in s: return "紫蘇潤澤凝露[100ml]"
    if "頭皮調理液" in s: return "頭皮調理液"
    if "按摩油" in s: return "按摩油"
    if "精華油" in s: return "精華油"
    if "福袋" in s: return "福袋"
    if "紫蘇梗" in s: return "紫蘇梗茶包"
    if ("紫蘇" in s or "紫蘇茶" in s or "紫蘇茶包" in s) and any(k in s for k in ["按摩油", "精華油", "頭皮調理液", "保養", "外養"]):
        return "紫蘇茶＋保養品組合"
    if "紫蘇" in s and any(k in s for k in ["150g", "300g", "茶葉"]): return "紫蘇茶葉"
    if "紫蘇" in s and any(k in s for k in ["入", "盒裝", "無盒", "單包"]): return "紫蘇茶包"
    if "紫蘇茶包" in s: return "紫蘇茶包"
    if "紫蘇" in s and "茶葉" in s: return "紫蘇茶葉"
    return s
