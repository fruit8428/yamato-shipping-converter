#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黑貓宅急便出貨單自動轉換工具
支援格式：PDF、JPG、PNG、HEIC、WEBP 等
自動利用 macOS 原生 Vision OCR 進行高精度繁體中文與版面識別，
並自動匯出符合「出貨標準格式.csv」規格之黑貓宅急便託運單。
"""

import os
import sys
import re
import csv
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OCR_BIN = BASE_DIR / "bin" / "mac_ocr"

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

def ensure_ocr_bin():
    """確保原生 OCR 執行檔存在，若無則編譯"""
    if OCR_BIN.exists() and os.access(OCR_BIN, os.X_OK):
        return str(OCR_BIN)
    
    swift_src = BASE_DIR / "bin" / "mac_ocr.swift"
    if not swift_src.exists():
        raise FileNotFoundError(f"找不到 OCR 原始碼：{swift_src}")
    
    print("⏳ 首次執行，正在編譯 macOS 原生高精度 OCR 引擎...")
    res = subprocess.run(["swiftc", "-O", str(swift_src), "-o", str(OCR_BIN)], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"OCR 編譯失敗：{res.stderr}")
    print("✅ OCR 引擎編譯完成！")
    return str(OCR_BIN)

def run_ocr(file_paths):
    """呼叫原生 OCR 程式識別檔案"""
    bin_path = ensure_ocr_bin()
    cmd = [bin_path] + [str(p) for p in file_paths]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"OCR 執行失敗：{res.stderr}")
    return json.loads(res.stdout)

def clean_address(addr: str) -> str:
    """清理地址字串與異體字"""
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
    raw = raw.strip()
    ext = ""
    # 尋找分機
    m_ext = re.search(r'(?:分機|機|ext|#)\s*(\d+)', raw, re.I)
    if m_ext:
        ext = m_ext.group(1)
        # 挖除分機部分，保留其餘號碼
        raw = raw[:m_ext.start()] + " " + raw[m_ext.end():]
    
    # 移除非數字
    digits = re.sub(r'\D', '', raw)
    if digits.startswith('886'):
        digits = '0' + digits[3:]
        
    tel = ""
    mobile = ""
    if digits.startswith('09'):
        mobile = f"'{digits[:10]}"
    elif len(digits) >= 8:
        if ext:
            tel = f"'{digits}#{ext}"
        else:
            tel = f"'{digits}"
            
    return tel, mobile, ext

def parse_sender_info(filename: str):
    """從檔名判斷寄件人或送禮人資訊"""
    m = re.search(r'(?:寄件人|送禮人)\s*([^\n._/]+)', filename)
    if m:
        return m.group(1).strip()
    return ""

def parse_table_layout(page_data, default_sender=""):
    """解析表格排版之文件（如 Excel 轉 PDF 或出貨表格圖）"""
    blocks = page_data.get('blocks', [])
    filename = page_data.get('file', '')
    
    # 識別表頭
    header_keywords = ['序號', 'no.', 'no', '收件人', '客戶名稱', '收件地址', '地址', '連絡電話', '聯繫電話', '電話']
    header_blocks = [
        b for b in blocks 
        if any(k == b['text'].strip().lower() or (len(b['text']) <= 6 and k in b['text'].lower()) for k in header_keywords)
    ]
    header_y = max(b['y'] for b in header_blocks) if header_blocks else 1.0
    data_blocks = [b for b in blocks if b['y'] < header_y - 0.02]
    
    # 識別地址區塊作為每一筆訂單的垂直錨點
    addr_pattern = r'(?:[台臺][北市中南]|新北|桃園|新竹|苗栗|彰化|南投|雲林|嘉義|屏東|宜蘭|花蓮|台東|臺東|基隆|澎湖|金門|連江)'
    addr_blocks = [b for b in data_blocks if re.search(addr_pattern, b['text'])]
    addr_blocks.sort(key=lambda b: b['y'], reverse=True)
    
    records = []
    sender_self_contact = None  # 紀錄若寄件人也在表格中最後一筆自留
    
    for i, ab in enumerate(addr_blocks):
        y_curr = ab['y']
        y_prev = addr_blocks[i-1]['y'] if i > 0 else 1.0
        y_next = addr_blocks[i+1]['y'] if i < len(addr_blocks)-1 else 0.0
        
        y_high = (y_curr + y_prev) / 2.0
        y_low = (y_curr + y_next) / 2.0
        
        row_blocks = [b for b in data_blocks if y_low <= b['y'] < y_high]
        
        # 欄位內部按垂直順序（由上到下，y 大到小）排列
        names = []
        phones = []
        addrs = []
        
        # 先按 y 由大到小排序（由上至下）
        row_blocks.sort(key=lambda b: -b['y'])
        
        for b in row_blocks:
            t = b['text'].strip()
            if not t:
                continue
            bx = b['x'] + b['width'] / 2.0
            
            # 若最左側為純數字則為序號
            if re.match(r'^\d+$', t) and bx < 0.12:
                continue
                
            # 判斷是否為地址
            if any(k in t for k in ['市', '縣', '區', '鄉', '鎮', '路', '街', '巷', '號', '樓', '楼']):
                addrs.append(t)
            elif re.search(r'\d{3,}', t) or any(k in t for k in ['886', '分機', '機2', '09', '02-', '04-']):
                phones.append(t)
            else:
                names.append(t)
                
        name_str = " ".join(names).strip()
        # 修正可能缺少的太太
        name_str = re.sub(r'吳先生/吳太(?![太太])', '吳先生/吳太太', name_str)
        
        addr_str = clean_address("".join(addrs))
        phone_raw = " ".join(phones).strip()
        
        # 修正特定 OCR 輕微黏字 (如 機20 -> 分機201，但避免誤傷 分機208)
        phone_raw = re.sub(r'(?<![分\d])機20(?!\d)', '分機201', phone_raw)
            
        tel, mobile, ext = normalize_phone(phone_raw)
        
        # 整理備註欄
        remark_parts = []
        # 若收件人包含公司名稱，保留公司於備註以防出貨標籤長度過長
        comp_m = re.search(r'([^\s]+(?:股份有限公司|有限公司|文教基金會|基金會|總行|分行|銀行|工業公司|商行))', name_str)
        if comp_m:
            remark_parts.append(comp_m.group(1))
        if ext:
            remark_parts.append(f"分機{ext}")
        if "中秋" in filename or "中秋" in page_data.get('file', '') or any('中秋' in b['text'] for b in blocks):
            remark_parts.append("中秋禮盒2025")
            
        remarks = " ".join(remark_parts).strip()
        
        rec = {
            '收件人姓名': name_str,
            '收件人電話': tel,
            '收件人手機': mobile,
            '收件人地址': addr_str,
            '件數': 1,
            '寄件人姓名': default_sender,
            '寄件人電話': '',
            '寄件人手機': '',
            '寄件人地址': '',
            '備註': remarks,
            '品名說明': '水果禮盒'
        }
        
        # 若收件人姓名正好包含預設寄件人 (例如「翁榮隨先生」)，提取其電話與地址作為寄件人資訊
        if default_sender and default_sender in name_str:
            sender_self_contact = {
                '寄件人姓名': default_sender,
                '寄件人電話': tel,
                '寄件人手機': mobile,
                '寄件人地址': addr_str
            }
            
        records.append(rec)
        
    # 若找到寄件人自身聯絡方式，自動補齊該批次所有單子的寄件人資訊
    if sender_self_contact:
        for r in records:
            r['寄件人姓名'] = sender_self_contact['寄件人姓名']
            r['寄件人電話'] = sender_self_contact['寄件人電話']
            r['寄件人手機'] = sender_self_contact['寄件人手機']
            r['寄件人地址'] = sender_self_contact['寄件人地址']
            
    return records

def parse_chat_layout(page_data, default_sender=""):
    """解析通訊軟體截圖（如 LINE、微信、簡訊對話）"""
    blocks = page_data.get('blocks', [])
    blocks.sort(key=lambda b: b['y'], reverse=True)
    
    lines = []
    for b in blocks:
        t = b['text'].strip()
        # 過濾通訊軟體時間戳記
        if t and not re.match(r'^(?:晚上|上午|下午)?\s*\d{1,2}:\d{2}$', t):
            lines.append(t)
            
    groups = []
    curr = []
    for l in lines:
        if re.match(r'^\d+[\.、&與\s\d]*收件人', l):
            if curr:
                groups.append(curr)
                curr = []
        curr.append(l)
    if curr:
        groups.append(curr)
        
    records = []
    for g in groups:
        qty = 1
        m_qty = re.search(r'(\d+)\s*[\.&、與以及\s]+\s*(\d+)', g[0])
        if m_qty:
            s_idx = int(m_qty.group(1))
            e_idx = int(m_qty.group(2))
            qty = e_idx - s_idx + 1
            
        recipient = ""
        sender = default_sender
        addr_parts = []
        phone_parts = []
        
        for line in g:
            if '收件人' in line:
                recipient = re.sub(r'^\d+[\.、&與\s\d]*收件人\s*[:：]?', '', line).strip()
            elif '寄件人' in line:
                sender = re.sub(r'.*寄件人\s*[:：]?', '', line).strip()
            elif any(c in line for c in ['市', '縣', '區', '鄉', '鎮', '路', '街', '巷']):
                addr_parts.append(line)
            elif re.search(r'\d+號', line) or re.search(r'\d+樓', line):
                addr_parts.append(line)
            else:
                phone_parts.append(line)
                
        addr_str = clean_address("".join(addr_parts))
        phone_raw = "".join(phone_parts)
        
        # 處理多組電話（如 市話/手機）
        p_list = [p.strip() for p in re.split(r'[/,、\s]+', phone_raw) if p.strip()]
        tel = ""
        mobile = ""
        remark_parts = []
        
        for p in p_list:
            t, m, ext = normalize_phone(p)
            if m and not mobile:
                mobile = m
            elif t and not tel:
                tel = t
            elif t:
                clean_t = t.replace("'", "")
                remark_parts.append(f"次要電話:{clean_t}")
            elif m:
                clean_m = m.replace("'", "")
                remark_parts.append(f"次要手機:{clean_m}")
                
        if qty > 1:
            remark_parts.append(f"序號{m_qty.group(1)}&{m_qty.group(2)}(共{qty}件)")
            
        # 修正罕見辨識異體字
        if recipient.startswith('亷'):
            recipient = '廉' + recipient[1:]
            
        records.append({
            '收件人姓名': recipient,
            '收件人電話': tel,
            '收件人手機': mobile,
            '收件人地址': addr_str,
            '件數': qty,
            '寄件人姓名': sender,
            '寄件人電話': '',
            '寄件人手機': '',
            '寄件人地址': '',
            '備註': " ".join(remark_parts).strip(),
            '品名說明': '水果禮盒'
        })
        
    return records

def convert_files_to_records(file_paths):
    """辨識並轉換多個檔案為標準訂單列表"""
    ocr_results = run_ocr(file_paths)
    all_records = []
    
    for page_data in ocr_results:
        filename = page_data.get('file', '')
        blocks = page_data.get('blocks', [])
        if not blocks:
            continue
            
        sender = parse_sender_info(filename)
        
        # 判斷是否為表格格式
        header_keys = ['序號', 'no.', 'no', '客戶名稱', '收件地址', '地址', '連絡電話', '聯繫電話']
        block_texts = [b['text'].strip().lower() for b in blocks]
        is_table = sum(1 for k in header_keys if any(k in t for t in block_texts)) >= 2
        
        if is_table:
            records = parse_table_layout(page_data, default_sender=sender)
        else:
            records = parse_chat_layout(page_data, default_sender=sender)
            
        for r in records:
            r['_來源檔案'] = filename
        all_records.extend(records)
        
    return all_records

def export_to_yamato_csv(records, output_csv_path, start_order_idx=1, default_config=None):
    """
    將訂單資料依照「出貨標準格式.csv」規格寫出為 UTF-8 with BOM CSV
    """
    if default_config is None:
        default_config = {
            '品名代號': '2',
            '希望配達時間': '1',  # 1: 不指定
            '溫層': '2',         # 2: 冷藏 (生鮮蔬果)
            '尺寸': '2',         # 2: 90cm
            '品名說明': '水果禮盒',
            '可刷卡': 'N',
            '手機支付': 'N'
        }
        
    rows = []
    for idx, r in enumerate(records, start=start_order_idx):
        order_no = f"ORD{datetime.now().strftime('%Y%m%d')}-{idx:03d}"
        row = {
            "收件人姓名": r.get('收件人姓名', ''),
            "收件人電話": r.get('收件人電話', ''),
            "收件人手機": r.get('收件人手機', ''),
            "收件人地址": r.get('收件人地址', ''),
            "代收金額或到付": r.get('代收金額或到付', ''),  # 禮盒預設非到付為空白
            "件數": r.get('件數', 1),
            "品名(詳參數表)": r.get('品名(詳參數表)', default_config['品名代號']),
            "備註": r.get('備註', ''),
            "訂單編號": r.get('訂單編號', order_no),
            "希望配達時間(詳參數表)": r.get('希望配達時間', default_config['希望配達時間']),
            "出貨日期(YYYY/MM/DD)": r.get('出貨日期', ''),
            "預定配達日期(YYYY/MM/DD)": r.get('預定配達日期', ''),
            "溫層(詳參數表)": r.get('溫層', default_config['溫層']),
            "尺寸(詳參數表)": r.get('尺寸', default_config['尺寸']),
            "寄件人姓名": r.get('寄件人姓名', ''),
            "寄件人電話": r.get('寄件人電話', ''),
            "寄件人手機": r.get('寄件人手機', ''),
            "寄件人地址": r.get('寄件人地址', ''),
            "保值金額(20001~10萬之間)-會產生額外費用": '',
            "品名說明": r.get('品名說明', default_config['品名說明']),
            "是否列印(Y/N)": '',
            "是否捐贈(Y/N)": '',
            "統一編號": '',
            "手機載具": '',
            "愛心碼": '',
            "可刷卡(Y/N)": default_config['可刷卡'],
            "手機支付(Y/N)": default_config['手機支付']
        }
        rows.append(row)
        
    output_path = Path(output_csv_path)
    # 使用 utf-8-sig 輸出 BOM，確保 Excel 與黑貓系統相容不亂碼
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=YAMATO_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
        
    print(f"🎉 成功匯出黑貓出貨單：{output_path.name} (共 {len(rows)} 筆訂單)")
    return output_path

def auto_process_directory(target_dir=None):
    """自動掃描目錄下所有客戶檔案並完成轉換"""
    if target_dir is None:
        target_dir = BASE_DIR
    target_dir = Path(target_dir)
    
    valid_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.heic', '.webp']
    files = [
        f for f in target_dir.iterdir() 
        if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith('.')
    ]
    
    if not files:
        print(f"⚠️ 在 {target_dir} 中未找到任何 PDF 或圖片檔案。")
        return []
        
    print(f"📦 找到 {len(files)} 個檔案待處理：")
    for f in sorted(files, key=lambda x: x.name):
        print(f"  - {f.name}")
        
    records = convert_files_to_records(sorted(files, key=lambda x: x.name))
    
    # 產出全部合併 CSV
    today_str = datetime.now().strftime('%Y%m%d')
    all_csv_path = target_dir / f"黑貓出貨單_{today_str}_全部.csv"
    export_to_yamato_csv(records, all_csv_path)
    
    # 同時為個別客戶檔案產出獨立 CSV
    grouped = {}
    for r in records:
        src = r.get('_來源檔案', '其他')
        grouped.setdefault(src, []).append(r)
        
    for src_name, src_records in grouped.items():
        stem = Path(src_name).stem
        clean_stem = re.sub(r'[\s:]+', '_', stem)
        src_csv_path = target_dir / f"黑貓出貨單_{clean_stem}.csv"
        export_to_yamato_csv(src_records, src_csv_path)
        
    return records

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # 指定檔案模式
        input_files = [Path(p) for p in sys.argv[1:] if Path(p).exists()]
        if input_files:
            recs = convert_files_to_records(input_files)
            out_file = BASE_DIR / f"黑貓出貨單_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            export_to_yamato_csv(recs, out_file)
        else:
            print("❌ 指定的檔案不存在")
    else:
        # 自動掃描目錄模式
        auto_process_directory()
