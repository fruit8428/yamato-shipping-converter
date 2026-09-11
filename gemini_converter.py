#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Google Gemini 3.6 Flash API 辨識模組
專為黑貓宅急便出貨單設計，支援 PDF、JPG、PNG、WEBP、HEIC
雲端伺服器 (Vercel Serverless) 與跨平台 (Windows / Mac / Linux) 均可無縫執行
"""

import os
import re
import io
import csv
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

YAMATO_HEADERS = [
    "收件人姓名",
    "收件人電話",
    "收件人手機",
    "收件人地址",
    "代收金額或到付",
    "件數",
    "品名(詳參數表)",
    "備註",
    "訂單編號",
    "希望配達時間(詳參數表)",
    "出貨日期(YYYY/MM/DD)",
    "預定配達日期(YYYY/MM/DD)",
    "溫層(詳參數表)",
    "尺寸(詳參數表)",
    "寄件人姓名",
    "寄件人電話",
    "寄件人手機",
    "寄件人地址",
    "保值金額(20001~10萬之間)-會產生額外費用",
    "品名說明",
    "是否列印(Y/N)",
    "是否捐贈(Y/N)",
    "統一編號",
    "手機載具",
    "愛心碼",
    "可刷卡(Y/N)",
    "手機支付(Y/N)"
]

DEFAULT_CONFIG = {
    '品名代號': '2',
    '希望配達時間': '1',  # 1: 不指定
    '溫層': '2',         # 2: 冷藏 (生鮮水果)
    '尺寸': '2',         # 2: 90cm
    '品名說明': '水果禮盒',
    '可刷卡': 'N',
    '手機支付': 'N'
}

GEMINI_PROMPT = """你是一個專精於台灣物流與黑貓宅急便出貨單辨識的繁體中文專家。
請從所提供的圖片或 PDF 文件中，精確萃取所有收件人訂單資料與寄件人資訊。

請務必遵守以下規範：
1. 僅回傳合法的 JSON 物件，結構必須如下：
{
  "sender": {
    "name": "寄件人或送禮人姓名",
    "phone": "寄件人市話",
    "mobile": "寄件人手機",
    "address": "寄件人地址"
  },
  "orders": [
    {
      "recipient_name": "收件人姓名 (包含先生/小姐/公司等抬頭)",
      "phone": "收件人市話 (例如 02-xxxxxxx#分機)",
      "mobile": "收件人手機 (例如 09xxxxxxxx)",
      "address": "收件人地址 (完整地址，含縣市、鄉鎮市區、路街、巷弄號、樓層與之幾)",
      "quantity": 1,
      "cod_amount": "",
      "remarks": "備註 (如公司抬頭、分機、次要電話、禮盒賀詞等)",
      "product_name": "水果禮盒"
    }
  ]
}

2. 關鍵解析原則：
- 寄件人資訊：檢視標題、檔案名稱或文字中提到的「送禮人」、「寄件人」；若表格最後一筆是寄件人「自留」或「自己留」，該筆的姓名、電話與地址即為寄件人資訊，其餘每筆均寄給該收件人。
- 件數解析：LINE 等聊天截圖中，若序號寫「1.2」或「1&2」代表 1 到 2 號共 2 件，quantity 請設為 2，並在 remarks 加上註記。單純「3.」代表 1 件。
- 電話號碼：09 開頭歸入 mobile；02/03/04/05/06/07/08 等市話歸入 phone。若有多組電話，主要的放 phone/mobile，次要電話記錄在 remarks。
- 地址：必須完整正確，並將簡體字或異體字轉為繁體（如「台」->「臺」、「楼」->「樓」）。
- 完整性：必須將所有收件人每一筆完整列出，絕不可省略或使用縮寫代表。
"""

def clean_address(addr: str) -> str:
    """清理地址字串與異體字"""
    if not addr:
        return ""
    addr = re.sub(r'\s+', '', addr)
    addr = addr.replace("楼", "樓").replace("台", "臺")
    return addr

def normalize_phone(raw: str):
    """
    標準化台灣電話號碼：
    - 處理國碼 886
    - 區分手機 (09...) 與市話 (02..., 04...)
    - 擷取分機號碼
    - 格式化為黑貓 CSV 標準 (前綴單引號 ' 防止 Excel 截斷 0)
    """
    if not raw:
        return "", "", ""
    raw = str(raw).strip()
    ext = ""
    m_ext = re.search(r'(?:分機|機|ext|#)\s*(\d+)', raw, re.I)
    if m_ext:
        ext = m_ext.group(1)
        raw = raw[:m_ext.start()] + " " + raw[m_ext.end():]
        
    digits = re.sub(r'\D', '', raw)
    if digits.startswith('886'):
        digits = '0' + digits[3:]
        
    tel = ""
    mobile = ""
    if digits.startswith('09'):
        mobile = f"'{digits[:10]}"
    elif len(digits) >= 7:
        if ext:
            tel = f"'{digits}#{ext}"
        else:
            tel = f"'{digits}"
            
    return tel, mobile, ext

def get_mime_type(filename: str, file_bytes: bytes = b"") -> str:
    """根據副檔名或檔案簽章判斷 MIME Type"""
    ext = Path(filename).suffix.lower()
    if ext == '.pdf':
        return 'application/pdf'
    elif ext in ['.jpg', '.jpeg']:
        return 'image/jpeg'
    elif ext == '.png':
        return 'image/png'
    elif ext == '.webp':
        return 'image/webp'
    elif ext == '.heic':
        return 'image/heic'
        
    # Magic bytes check
    if file_bytes.startswith(b'%PDF'):
        return 'application/pdf'
    elif file_bytes.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    elif file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
        
    return 'application/octet-stream'

def call_gemini_api(
    file_bytes: bytes, 
    mime_type: str, 
    filename: str = "", 
    api_key: Optional[str] = None,
    model: str = "gemini-3.6-flash"
) -> Dict[str, Any]:
    """
    呼叫 Google Gemini 3.6 Flash API 進行多模態文件辨識
    支援傳入 API Key 或從環境變數 GEMINI_API_KEY 讀取
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError("缺少 Google Gemini API 金鑰 (GEMINI_API_KEY)，請在網頁設定中輸入或於環境變數中設定。")
        
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    
    prompt_text = GEMINI_PROMPT
    if filename:
        prompt_text = f"檔案名稱參考：{filename}\n\n" + prompt_text
        
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }
    
    data_json = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=data_json,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp_body = resp.read().decode("utf-8")
            result = json.loads(resp_body)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini API 請求失敗 (HTTP {e.code}): {err_msg}")
    except Exception as e:
        raise RuntimeError(f"Gemini API 連線失敗: {str(e)}")
        
    # 解析 Gemini 回傳之文字內容
    try:
        candidates = result.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini 未回傳任何候選結果。")
        content_part = candidates[0]["content"]["parts"][0]["text"]
        
        # 移除非 JSON 標記 (如 markdown ```json ... ```)
        cleaned_text = content_part.strip()
        if cleaned_text.startswith("```"):
            cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
            cleaned_text = re.sub(r"\s*```$", "", cleaned_text)
            
        parsed_data = json.loads(cleaned_text)
        return parsed_data
    except Exception as e:
        raise ValueError(f"無法解析 Gemini 回傳之 JSON 資料: {str(e)}\n原始回傳內容: {resp_body[:500]}")

def convert_gemini_response_to_yamato_records(
    gemini_data: Dict[str, Any], 
    filename: str = "",
    default_config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    將 Gemini 回傳的結構化 JSON 轉換為黑貓標準 27 欄位訂單列表
    """
    cfg = default_config or DEFAULT_CONFIG
    sender_info = gemini_data.get("sender", {}) or {}
    orders = gemini_data.get("orders", []) or []
    
    # 寄件人聯絡電話處理
    s_tel, s_mob, _ = normalize_phone(sender_info.get("mobile") or sender_info.get("phone", ""))
    if not s_mob and sender_info.get("mobile"):
        s_mob = f"'{sender_info.get('mobile').strip()}"
        
    sender_name = sender_info.get("name", "")
    sender_addr = clean_address(sender_info.get("address", ""))
    
    records = []
    for ord_item in orders:
        name = ord_item.get("recipient_name", "").strip()
        raw_phone = ord_item.get("phone", "")
        raw_mobile = ord_item.get("mobile", "")
        raw_addr = ord_item.get("address", "")
        qty = int(ord_item.get("quantity", 1) or 1)
        cod = ord_item.get("cod_amount", "")
        remarks = ord_item.get("remarks", "")
        product_name = ord_item.get("product_name", cfg.get("品名說明", "水果禮盒"))
        
        # 標準化電話
        tel = ""
        mobile = ""
        if raw_mobile:
            t, m, _ = normalize_phone(raw_mobile)
            mobile = m or t
        if raw_phone:
            t, m, ext = normalize_phone(raw_phone)
            tel = t or m
            
        # 若電話/手機顛倒，調整之
        if tel.startswith("'09") and not mobile:
            mobile, tel = tel, ""
        elif mobile and not mobile.startswith("'09") and not tel:
            tel, mobile = mobile, ""
            
        clean_addr = clean_address(raw_addr)
        
        rec = {
            "收件人姓名": name,
            "收件人電話": tel,
            "收件人手機": mobile,
            "收件人地址": clean_addr,
            "代收金額或到付": cod,
            "件數": qty,
            "品名(詳參數表)": cfg.get("品名代號", "2"),
            "備註": remarks,
            "訂單編號": "",
            "希望配達時間(詳參數表)": cfg.get("希望配達時間", "1"),
            "出貨日期(YYYY/MM/DD)": "",
            "預定配達日期(YYYY/MM/DD)": "",
            "溫層(詳參數表)": cfg.get("溫層", "2"),
            "尺寸(詳參數表)": cfg.get("尺寸", "2"),
            "寄件人姓名": sender_name,
            "寄件人電話": s_tel,
            "寄件人手機": s_mob,
            "寄件人地址": sender_addr,
            "保值金額(20001~10萬之間)-會產生額外費用": "",
            "品名說明": product_name,
            "是否列印(Y/N)": "",
            "是否捐贈(Y/N)": "",
            "統一編號": "",
            "手機載具": "",
            "愛心碼": "",
            "可刷卡(Y/N)": cfg.get("可刷卡", "N"),
            "手機支付(Y/N)": cfg.get("手機支付", "N"),
            "_來源檔案": filename
        }
        records.append(rec)
        
    return records

def export_records_to_csv_text(records: List[Dict[str, Any]], start_order_idx: int = 1, default_config: Optional[Dict[str, Any]] = None) -> str:
    """
    將訂單列表轉為黑貓標準 27 欄位 CSV 字串 (不含 BOM，由外層決定)
    """
    cfg = default_config or DEFAULT_CONFIG
    rows = []
    for idx, r in enumerate(records, start=start_order_idx):
        order_no = r.get('訂單編號') or f"ORD{datetime.now().strftime('%Y%m%d')}-{idx:03d}"
        row = {
            "收件人姓名": r.get('收件人姓名', ''),
            "收件人電話": r.get('收件人電話', ''),
            "收件人手機": r.get('收件人手機', ''),
            "收件人地址": r.get('收件人地址', ''),
            "代收金額或到付": r.get('代收金額或到付', ''),
            "件數": r.get('件數', 1),
            "品名(詳參數表)": r.get('品名(詳參數表)', cfg.get('品名代號', '2')),
            "備註": r.get('備註', ''),
            "訂單編號": order_no,
            "希望配達時間(詳參數表)": r.get('希望配達時間(詳參數表)', cfg.get('希望配達時間', '1')),
            "出貨日期(YYYY/MM/DD)": r.get('出貨日期(YYYY/MM/DD)', ''),
            "預定配達日期(YYYY/MM/DD)": r.get('預定配達日期(YYYY/MM/DD)', ''),
            "溫層(詳參數表)": r.get('溫層(詳參數表)', cfg.get('溫層', '2')),
            "尺寸(詳參數表)": r.get('尺寸(詳參數表)', cfg.get('尺寸', '2')),
            "寄件人姓名": r.get('寄件人姓名', ''),
            "寄件人電話": r.get('寄件人電話', ''),
            "寄件人手機": r.get('寄件人手機', ''),
            "寄件人地址": r.get('寄件人地址', ''),
            "保值金額(20001~10萬之間)-會產生額外費用": r.get('保值金額(20001~10萬之間)-會產生額外費用', ''),
            "品名說明": r.get('品名說明', cfg.get('品名說明', '水果禮盒')),
            "是否列印(Y/N)": r.get('是否列印(Y/N)', ''),
            "是否捐贈(Y/N)": r.get('是否捐贈(Y/N)', ''),
            "統一編號": r.get('統一編號', ''),
            "手機載具": r.get('手機載具', ''),
            "愛心碼": r.get('愛心碼', ''),
            "可刷卡(Y/N)": r.get('可刷卡(Y/N)', cfg.get('可刷卡', 'N')),
            "手機支付(Y/N)": r.get('手機支付(Y/N)', cfg.get('手機支付', 'N'))
        }
        rows.append(row)
        
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=YAMATO_HEADERS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()

def export_records_to_csv_file(records: List[Dict[str, Any]], output_path: str, default_config: Optional[Dict[str, Any]] = None) -> Path:
    """
    將訂單資料依照黑貓標準規格寫出為 UTF-8 with BOM CSV
    """
    csv_text = export_records_to_csv_text(records, default_config=default_config)
    p = Path(output_path)
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(csv_text)
    return p

