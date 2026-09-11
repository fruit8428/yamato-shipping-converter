#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黑貓宅急便出貨單自動轉換系統 - Web 視覺化操作介面
無需安裝第三方套件，使用 Python 內建 HTTP Server
支援自訂切換工作目錄、拖曳上傳、單檔獨立辨識、線上編輯與一鍵匯出黑貓標準 CSV
"""

import os
import sys
import re
import json
import mimetypes
import urllib.parse
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

import yamato_converter

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
CURRENT_DIR = BASE_DIR
PORT = 8765

def get_current_dir() -> Path:
    """取得當前工作目錄"""
    global CURRENT_DIR
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
                custom_dir = d.get('current_dir')
                if custom_dir and os.path.isdir(custom_dir):
                    CURRENT_DIR = Path(custom_dir)
        except Exception:
            pass
    return CURRENT_DIR

def set_current_dir(new_path: Path):
    """設定並持久化當前工作目錄"""
    global CURRENT_DIR
    CURRENT_DIR = new_path.resolve()
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({'current_dir': str(CURRENT_DIR)}, f, ensure_ascii=False)
    except Exception as e:
        print("儲存設定失敗:", e)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>黑貓宅急便出貨單自動轉換系統 - 都匯水果</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --primary: #005a36;
  --primary-dark: #004328;
  --primary-light: #e6f4ea;
  --accent: #f59e0b;
  --text-main: #1f2937;
  --text-muted: #6b7280;
  --bg-main: #f8fafc;
  --card-bg: #ffffff;
  --border: #e2e8f0;
}
* { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Noto Sans TC', sans-serif; }
body { background: var(--bg-main); color: var(--text-main); min-height: 100vh; padding: 20px; }
.container { max-width: 98%; margin: 0 auto; }
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; padding-bottom: 14px; border-bottom: 2px solid var(--border); }
.brand { display: flex; align-items: center; gap: 14px; }
.brand-logo { width: 44px; height: 44px; background: var(--primary); color: white; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: bold; }
.brand-title h1 { font-size: 22px; font-weight: 700; color: var(--primary-dark); }
.brand-title p { font-size: 13px; color: var(--text-muted); }

.action-bar { display: flex; gap: 10px; }
.btn { padding: 9px 16px; border-radius: 8px; font-size: 13.5px; font-weight: 600; cursor: pointer; border: none; transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px; text-decoration: none; }
.btn-primary { background: var(--primary); color: white; }
.btn-primary:hover { background: var(--primary-dark); }
.btn-outline { background: white; border: 1px solid var(--border); color: var(--text-main); }
.btn-outline:hover { background: #f1f5f9; }
.btn-export { background: #0284c7; color: white; }
.btn-export:hover { background: #0369a1; }
.btn-danger-outline { background: white; border: 1px solid #fca5a5; color: #dc2626; }
.btn-danger-outline:hover { background: #fee2e2; }

.grid-layout { display: grid; grid-template-columns: 330px 1fr; gap: 20px; }
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }

/* Directory switch card */
.dir-card { margin-bottom: 16px; border-left: 4px solid var(--primary); }
.dir-badge { font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px; background: var(--primary-light); color: var(--primary-dark); }
.dir-input { width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--border); font-size: 12px; font-family: monospace; background: #f8fafc; color: #334155; }
.dir-input:focus { background: white; border-color: var(--primary); outline: none; }

/* Dropzone */
.dropzone { 
  border: 2px dashed #94a3b8; 
  border-radius: 12px; 
  padding: 26px 16px; 
  text-align: center; 
  cursor: pointer; 
  background: #f8fafc; 
  transition: all 0.2s; 
}
.dropzone:hover, .dropzone.dragover { 
  border-color: var(--primary); 
  background: var(--primary-light); 
  transform: scale(1.01);
}
.drop-icon { font-size: 36px; margin-bottom: 6px; }
.drop-title { font-size: 14px; font-weight: 700; color: var(--text-main); }
.drop-subtitle { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

/* Settings */
.settings-group { margin-top: 16px; }
.settings-group h3 { font-size: 12.5px; font-weight: 700; margin-bottom: 8px; color: var(--text-main); text-transform: uppercase; letter-spacing: 0.5px; }
.field-row { display: flex; flex-direction: column; gap: 5px; margin-bottom: 10px; }
.field-row label { font-size: 12px; font-weight: 600; color: var(--text-muted); }
.field-row select, .field-row input { padding: 7px 10px; border-radius: 6px; border: 1px solid var(--border); font-size: 13px; }

/* Existing files list */
.file-list { margin-top: 6px; display: flex; flex-direction: column; gap: 6px; max-height: 180px; overflow-y: auto; }
.file-chip { display: flex; align-items: center; justify-content: space-between; background: #f1f5f9; padding: 7px 10px; border-radius: 6px; font-size: 12px; }
.file-chip-name { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px; }
.btn-mini { padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; cursor: pointer; border: 1px solid var(--primary); background: white; color: var(--primary); }
.btn-mini:hover { background: var(--primary); color: white; }

/* Table section */
.table-header-wrap { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.table-title { display: flex; align-items: center; gap: 10px; }
.table-title h2 { font-size: 18px; font-weight: 700; }
.badge { background: var(--primary-light); color: var(--primary-dark); font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 999px; }
.source-tag { background: #e0f2fe; color: #0369a1; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 6px; display: none; }

.table-responsive { 
  overflow-x: auto; 
  border: 1px solid var(--border); 
  border-radius: 10px; 
  max-height: calc(100vh - 200px); 
  background: white;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.table-responsive::-webkit-scrollbar { height: 11px; width: 8px; }
.table-responsive::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 6px; }
.table-responsive::-webkit-scrollbar-thumb { background: #94a3b8; border-radius: 6px; border: 2px solid #f1f5f9; }
.table-responsive::-webkit-scrollbar-thumb:hover { background: #64748b; }

table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
th { 
  background: #f1f5f9; 
  padding: 12px 10px; 
  font-weight: 700; 
  color: #334155; 
  position: sticky; 
  top: 0; 
  z-index: 10; 
  border-bottom: 2px solid #cbd5e1; 
  white-space: nowrap; 
}
td { 
  padding: 6px 8px; 
  border-bottom: 1px solid #e2e8f0; 
  vertical-align: middle; 
  white-space: nowrap; 
}
tr:hover td { background: #f8fafc; }
td input { 
  width: 100%; 
  border: 1px solid #cbd5e1; 
  background: #ffffff; 
  padding: 6px 10px; 
  border-radius: 6px; 
  font-size: 13.5px; 
  color: #1e293b;
  box-sizing: border-box;
  transition: all 0.15s ease-in-out;
}
td input:focus { 
  border-color: var(--primary); 
  background: #f0fdf4; 
  box-shadow: 0 0 0 3px rgba(0, 90, 54, 0.15); 
  outline: none; 
}
.col-num { width: 45px; min-width: 45px; text-align: center; color: var(--text-muted); font-weight: 700; }
.col-del { width: 45px; min-width: 45px; text-align: center; cursor: pointer; color: #ef4444; font-weight: bold; font-size: 15px; }
.col-del:hover { background: #fee2e2; border-radius: 6px; }

/* Explicit column width styles */
.th-name { min-width: 250px; }
.th-mobile { min-width: 140px; }
.th-tel { min-width: 170px; }
.th-addr { min-width: 440px; }
.th-qty { width: 65px; min-width: 65px; text-align: center; }
.th-sender { min-width: 140px; }
.th-sender-mobile { min-width: 140px; }
.th-remark { min-width: 260px; }
.th-src { min-width: 200px; }

.history-card { margin-top: 16px; }
.history-title { font-size: 12.5px; font-weight: 700; margin-bottom: 8px; color: var(--text-main); text-transform: uppercase; letter-spacing: 0.5px; }
.history-item { display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 6px; background: #fafafa; font-size: 12px; }
.history-name { font-weight: 600; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-date { font-size: 11px; color: var(--text-muted); }

/* Loading overlay */
#loading-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 100; align-items: center; justify-content: center; flex-direction: column; color: white; backdrop-filter: blur(2px); }
.spinner { width: 50px; height: 50px; border: 5px solid rgba(255,255,255,0.3); border-top-color: #ffffff; border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div id="loading-overlay">
  <div class="spinner"></div>
  <div style="font-size: 18px; font-weight: 700;" id="loadingText">正在處理中...</div>
  <div style="font-size: 13px; opacity: 0.85; margin-top: 6px;" id="loadingSubtext">透過 Apple Vision 引擎進行高精度繁體中文與版面識別</div>
</div>

<div class="container">
  <header>
    <div class="brand">
      <div class="brand-logo">🐱</div>
      <div class="brand-title">
        <h1>黑貓宅急便出貨單自動轉換系統</h1>
        <p>都匯水果專用版 ｜ 支援自訂目錄、PDF、訂單截圖自動辨識</p>
      </div>
    </div>
    <div class="action-bar">
      <button class="btn btn-outline" onclick="refreshDirectoryData()">🔄 重新整理目錄</button>
      <button class="btn btn-outline" onclick="recognizeAllFiles()" title="將當前目錄中所有客戶檔案一次合併辨識">📦 批次辨識當前目錄全部檔案</button>
      <button class="btn btn-export" onclick="exportCsv()">📥 匯出黑貓標準 CSV</button>
    </div>
  </header>

  <div class="grid-layout">
    <!-- Left Sidebar -->
    <div class="sidebar">
      <!-- Directory Switch Card -->
      <div class="card dir-card">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
          <div style="font-size:13px; font-weight:700; color:var(--text-main); display:flex; align-items:center; gap:6px;">
            <span>📂</span> 工作檔案目錄
          </div>
          <span class="dir-badge" id="dirBadge">載入中...</span>
        </div>
        <div style="display:flex; gap:6px; margin-bottom:8px;">
          <input type="text" id="dirInput" class="dir-input" placeholder="/路徑/至/資料夾" title="可手動貼上或輸入目錄路徑">
          <button class="btn btn-outline" style="padding:6px 12px; font-size:12px; white-space:nowrap;" onclick="applyManualDir()">套用</button>
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn btn-primary" style="flex:1; padding:7px 10px; font-size:12px; justify-content:center;" onclick="browseFolder()">🖥️ 瀏覽選擇資料夾...</button>
          <button class="btn btn-outline" style="padding:7px 10px; font-size:12px;" onclick="resetDefaultDir()" title="切換回系統預設出貨目錄">預設</button>
        </div>
      </div>

      <div class="card">
        <!-- Drop Zone -->
        <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
          <div class="drop-icon">📥</div>
          <div class="drop-title">拖曳單一檔案至此辨識</div>
          <div class="drop-subtitle">支援 PDF、JPG、PNG、HEIC</div>
          <div style="font-size: 11px; color: var(--primary); margin-top: 6px; font-weight:600;">放開後自動存入目錄並立即辨識</div>
          <input type="file" id="fileInput" multiple style="display:none;" onchange="handleFileSelect(event)">
        </div>

        <div class="settings-group">
          <h3>目錄中檔案清單</h3>
          <div class="file-list" id="fileListContainer">
            <div style="color:var(--text-muted); font-size:12px; text-align:center; padding:12px;">載入中...</div>
          </div>
        </div>

        <div class="settings-group">
          <h3>黑貓出貨預設參數</h3>
          <div class="field-row">
            <label>溫層規格 (詳參數表)</label>
            <select id="cfg-temp">
              <option value="2" selected>2 - 冷藏 (水果生鮮)</option>
              <option value="1">1 - 常溫</option>
              <option value="3">3 - 冷凍</option>
            </select>
          </div>
          <div class="field-row">
            <label>包裹尺寸 (詳參數表)</label>
            <select id="cfg-size">
              <option value="2" selected>2 - 90 公分以下 (標準果盒)</option>
              <option value="1">1 - 60 公分以下</option>
              <option value="3">3 - 120 公分以下</option>
              <option value="4">4 - 150 公分以下 (限常溫)</option>
            </select>
          </div>
          <div class="field-row">
            <label>希望配達時段</label>
            <select id="cfg-time">
              <option value="1" selected>1 - 不指定</option>
              <option value="2">2 - 13點前</option>
              <option value="3">3 - 14~18點</option>
            </select>
          </div>
          <div class="field-row">
            <label>品名說明</label>
            <input type="text" id="cfg-item-desc" value="生鮮水果禮盒">
          </div>
        </div>
      </div>

      <!-- History / Exported CSVs -->
      <div class="card history-card">
        <div class="history-title">當前目錄產出之 CSV</div>
        <div id="historyList">載入中...</div>
      </div>
    </div>

    <!-- Right Table Content -->
    <div class="main-content">
      <div class="card">
        <div class="table-header-wrap">
          <div class="table-title">
            <h2>已辨識出貨訂單清單</h2>
            <span class="badge" id="orderCountBadge">目前無資料</span>
            <span class="source-tag" id="currentSourceTag"></span>
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-outline" style="padding: 6px 12px; font-size: 12px;" onclick="addNewRow()">➕ 新增一筆</button>
            <button class="btn btn-danger-outline" style="padding: 6px 12px; font-size: 12px;" onclick="clearTable()">🗑️ 清空清單</button>
          </div>
        </div>

        <div class="table-responsive">
          <table id="ordersTable">
            <thead>
              <tr>
                <th class="col-num">#</th>
                <th class="th-name">收件人姓名</th>
                <th class="th-mobile">收件人手機</th>
                <th class="th-tel">收件人市話 (含分機)</th>
                <th class="th-addr">收件人完整地址</th>
                <th class="th-qty">件數</th>
                <th class="th-sender">寄件人姓名</th>
                <th class="th-sender-mobile">寄件人手機</th>
                <th class="th-remark">備註說明</th>
                <th class="th-src">來源檔案</th>
                <th class="col-del">操作</th>
              </tr>
            </thead>
            <tbody id="ordersTbody">
              <tr>
                <td colspan="11" style="text-align: center; padding: 80px 20px; color: var(--text-muted);">
                  <div style="font-size: 40px; margin-bottom: 12px;">📥</div>
                  <div style="font-size: 16px; font-weight: 700; color: #334155;">清單目前為空</div>
                  <div style="font-size: 13px; margin-top: 6px; color: #64748b;">請將客戶的 PDF、訂單截圖或照片拖曳至左側上傳區，系統將自動進行單檔辨識</div>
                  <div style="font-size: 12px; margin-top: 10px; color: #94a3b8;">（也可點擊左側目錄檔案旁的「辨識此檔」直接測試）</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</div>

<script>
let currentOrders = [];
let currentSourceFileName = "";

// 初始化
window.onload = function() {
  loadCurrentDir();
  renderTable();
};

// 取得當前工作目錄
function loadCurrentDir() {
  fetch('/api/get_current_dir')
    .then(r => r.json())
    .then(data => {
      if (data.dir) {
        document.getElementById('dirInput').value = data.dir;
        document.getElementById('dirBadge').textContent = data.name || "現行目錄";
        document.getElementById('dirBadge').title = data.dir;
        loadDirectoryFiles();
        loadHistoryCsvs();
      }
    });
}

// 瀏覽選擇目錄 (叫起 Mac 原生資料夾選擇視窗)
function browseFolder() {
  showLoading(true, "請在跳出的 Mac 視窗中選擇資料夾...", "若未跳出，請檢查 Mac 畫面中間提示");
  fetch('/api/browse_dir', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      showLoading(false);
      if (data.success && data.dir) {
        document.getElementById('dirInput').value = data.dir;
        document.getElementById('dirBadge').textContent = data.name;
        document.getElementById('dirBadge').title = data.dir;
        loadDirectoryFiles();
        loadHistoryCsvs();
      } else if (data.canceled) {
        // 使用者取消，不動作
      }
    })
    .catch(err => {
      showLoading(false);
      alert('切換目錄失敗：' + err);
    });
}

// 手動套用輸入框的目錄路徑
function applyManualDir() {
  const dirPath = document.getElementById('dirInput').value.trim();
  if (!dirPath) {
    alert('請輸入有效的目錄路徑！');
    return;
  }
  showLoading(true, "正在切換目錄...", dirPath);
  fetch('/api/set_current_dir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dir: dirPath })
  })
  .then(r => r.json())
  .then(data => {
    showLoading(false);
    if (data.success) {
      document.getElementById('dirBadge').textContent = data.name;
      document.getElementById('dirBadge').title = data.dir;
      loadDirectoryFiles();
      loadHistoryCsvs();
      alert(`✅ 已成功切換至目錄：\n${data.dir}`);
    } else {
      alert('❌ 切換失敗：' + (data.error || '路徑無效'));
    }
  })
  .catch(err => {
    showLoading(false);
    alert('切換失敗：' + err);
  });
}

// 切換回系統預設出貨目錄
function resetDefaultDir() {
  fetch('/api/reset_default_dir', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.dir) {
        document.getElementById('dirInput').value = data.dir;
        document.getElementById('dirBadge').textContent = data.name;
        document.getElementById('dirBadge').title = data.dir;
        loadDirectoryFiles();
        loadHistoryCsvs();
      }
    });
}

// 刷新目錄資料
function refreshDirectoryData() {
  loadCurrentDir();
}

// 阻止瀏覽器預設開啟拖進來檔案的行為
window.addEventListener('dragover', function(e) { e.preventDefault(); }, false);
window.addEventListener('drop', function(e) { e.preventDefault(); }, false);

// 拖曳區事件
const dropzone = document.getElementById('dropzone');
['dragenter', 'dragover'].forEach(n => {
  dropzone.addEventListener(n, e => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.add('dragover');
  });
});

['dragleave', 'drop'].forEach(n => {
  dropzone.addEventListener(n, e => {
    e.preventDefault();
    e.stopPropagation();
    dropzone.classList.remove('dragover');
  });
});

dropzone.addEventListener('drop', e => {
  e.preventDefault();
  e.stopPropagation();
  const files = e.dataTransfer.files;
  if (files && files.length > 0) {
    uploadAndRecognizeSingle(files);
  }
});

function handleFileSelect(e) {
  if (e.target.files && e.target.files.length > 0) {
    uploadAndRecognizeSingle(e.target.files);
  }
}

// 拖曳檔案後：單筆檔案精準辨識，只呈現在當前表格
function uploadAndRecognizeSingle(files) {
  const formData = new FormData();
  for (let f of files) {
    formData.append('files', f);
  }

  showLoading(true, "正在上傳並進行單檔高精度辨識...", "使用 Apple Vision 神經網路 OCR 分析");
  fetch('/api/upload', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(res => {
      showLoading(false);
      if (res.success && res.records) {
        currentOrders = res.records;
        currentSourceFileName = (res.uploaded && res.uploaded.length > 0) ? res.uploaded[0] : "";
        renderTable();
        loadDirectoryFiles();
        loadHistoryCsvs();
      } else {
        alert('⚠️ 提示：' + (res.error || '無法辨識檔案內容'));
        loadDirectoryFiles();
      }
    })
    .catch(err => {
      showLoading(false);
      alert('❌ 上傳辨識失敗：' + err);
    });
}

// 辨識當前目錄中指定的個別檔案
function recognizeSingleFile(filename) {
  showLoading(true, `正在辨識檔案：${filename}...`, "分析表格或截圖文字排版");
  fetch('/api/process_file', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: filename })
  })
  .then(r => r.json())
  .then(data => {
    showLoading(false);
    if (data.records) {
      currentOrders = data.records;
      currentSourceFileName = filename;
      renderTable();
    }
  })
  .catch(err => {
    showLoading(false);
    alert('辨識失敗：' + err);
  });
}

// 批次辨識當前目錄全部檔案
function recognizeAllFiles() {
  if (!confirm("確定要將當前目錄中的所有客戶檔案一次性全部辨識並匯總至清單嗎？")) return;
  showLoading(true, "正在批次辨識目錄中所有檔案...", "合併全部訂單");
  fetch('/api/process_all', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      showLoading(false);
      if (data.records) {
        currentOrders = data.records;
        currentSourceFileName = "當前目錄全部檔案合併";
        renderTable();
        loadHistoryCsvs();
      }
    })
    .catch(err => {
      showLoading(false);
      alert('批次辨識失敗：' + err);
    });
}

// 載入當前目錄檔案列表
function loadDirectoryFiles() {
  fetch('/api/list_files')
    .then(r => r.json())
    .then(files => {
      const container = document.getElementById('fileListContainer');
      if (files.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; text-align:center; padding:12px;">當前目錄下尚無客戶檔案</div>';
        return;
      }
      container.innerHTML = files.map(f => `
        <div class="file-chip">
          <span class="file-chip-name" title="${f}">📄 ${f}</span>
          <button class="btn-mini" onclick="recognizeSingleFile('${escapeHtml(f)}')">辨識此檔</button>
        </div>
      `).join('');
    });
}

// 載入當前目錄已產出的歷史 CSV
function loadHistoryCsvs() {
  fetch('/api/list_csvs')
    .then(r => r.json())
    .then(csvs => {
      const container = document.getElementById('historyList');
      if (csvs.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:8px;">尚無匯出紀錄</div>';
        return;
      }
      container.innerHTML = csvs.map(f => `
        <div class="history-item">
          <div>
            <div class="history-name" title="${f.name}">📊 ${f.name}</div>
            <div class="history-date">${f.size} · ${f.time}</div>
          </div>
          <a href="/download/${encodeURIComponent(f.name)}" class="btn btn-outline" style="padding:4px 8px; font-size:11px;" download>下載</a>
        </div>
      `).join('');
    });
}

// 清空目前表格
function clearTable() {
  if (currentOrders.length > 0 && !confirm("確定要清空目前畫面上的訂單清單嗎？")) return;
  currentOrders = [];
  currentSourceFileName = "";
  renderTable();
}

// 渲染表格
function renderTable() {
  const tbody = document.getElementById('ordersTbody');
  const countBadge = document.getElementById('orderCountBadge');
  const sourceTag = document.getElementById('currentSourceTag');

  if (currentOrders.length === 0) {
    countBadge.textContent = "目前無資料";
    sourceTag.style.display = "none";
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="text-align: center; padding: 80px 20px; color: var(--text-muted);">
          <div style="font-size: 40px; margin-bottom: 12px;">📥</div>
          <div style="font-size: 16px; font-weight: 700; color: #334155;">清單目前為空</div>
          <div style="font-size: 13px; margin-top: 6px; color: #64748b;">請將客戶的 PDF、訂單截圖或照片拖曳至左側上傳區，系統將自動進行單檔辨識</div>
          <div style="font-size: 12px; margin-top: 10px; color: #94a3b8;">（也可點擊左側目錄檔案旁的「辨識此檔」直接測試）</div>
        </td>
      </tr>
    `;
    return;
  }

  countBadge.textContent = `共 ${currentOrders.length} 筆訂單`;
  if (currentSourceFileName) {
    sourceTag.textContent = `來源：${currentSourceFileName}`;
    sourceTag.style.display = "inline-block";
  } else {
    sourceTag.style.display = "none";
  }

  tbody.innerHTML = currentOrders.map((r, i) => `
    <tr>
      <td class="col-num">${i + 1}</td>
      <td style="min-width: 250px;"><input type="text" value="${escapeHtml(r.收件人姓名 || '')}" placeholder="姓名/公司" onchange="updateRow(${i}, '收件人姓名', this.value)"></td>
      <td style="min-width: 140px;"><input type="text" value="${escapeHtml((r.收件人手機 || '').replace("'", ''))}" placeholder="09xxxxxxxx" onchange="updateRow(${i}, '收件人手機', this.value)"></td>
      <td style="min-width: 170px;"><input type="text" value="${escapeHtml((r.收件人電話 || '').replace("'", ''))}" placeholder="02xxxxxxx#分機" onchange="updateRow(${i}, '收件人電話', this.value)"></td>
      <td style="min-width: 440px;"><input type="text" value="${escapeHtml(r.收件人地址 || '')}" placeholder="完整配送地址" onchange="updateRow(${i}, '收件人地址', this.value)"></td>
      <td style="width: 65px; min-width: 65px;"><input type="number" min="1" style="text-align:center; font-weight:600;" value="${r.件數 || 1}" onchange="updateRow(${i}, '件數', parseInt(this.value)||1)"></td>
      <td style="min-width: 140px;"><input type="text" value="${escapeHtml(r.寄件人姓名 || '')}" placeholder="寄件人" onchange="updateRow(${i}, '寄件人姓名', this.value)"></td>
      <td style="min-width: 140px;"><input type="text" value="${escapeHtml((r.寄件人手機 || '').replace("'", ''))}" placeholder="寄件人電話" onchange="updateRow(${i}, '寄件人手機', this.value)"></td>
      <td style="min-width: 260px;"><input type="text" value="${escapeHtml(r.備註 || '')}" placeholder="備註/分機/禮盒" onchange="updateRow(${i}, '備註', this.value)"></td>
      <td style="min-width: 200px; color:var(--text-muted); font-size:12px;" title="${escapeHtml(r._來源檔案 || '')}">📄 ${escapeHtml(r._來源檔案 || '')}</td>
      <td class="col-del" onclick="deleteRow(${i})" title="刪除此筆訂單">✕</td>
    </tr>
  `).join('');
}

function updateRow(index, key, val) {
  if (key === '收件人手機' || key === '收件人電話' || key === '寄件人手機') {
    val = val ? ("'" + val.replace(/^'+/, '')) : '';
  }
  currentOrders[index][key] = val;
}

function deleteRow(index) {
  currentOrders.splice(index, 1);
  renderTable();
}

function addNewRow() {
  currentOrders.push({
    '收件人姓名': '',
    '收件人電話': '',
    '收件人手機': '',
    '收件人地址': '',
    '件數': 1,
    '寄件人姓名': '',
    '寄件人電話': '',
    '寄件人手機': '',
    '寄件人地址': '',
    '備註': '',
    '品名說明': document.getElementById('cfg-item-desc').value,
    '_來源檔案': '手動新增'
  });
  renderTable();
}

// 匯出黑貓 CSV
function exportCsv() {
  if (currentOrders.length === 0) {
    alert('目前無可匯出的訂單資料！請先拖曳檔案進行辨識。');
    return;
  }

  const payload = {
    records: currentOrders,
    source_name: currentSourceFileName,
    config: {
      '溫層': document.getElementById('cfg-temp').value,
      '尺寸': document.getElementById('cfg-size').value,
      '希望配達時間': document.getElementById('cfg-time').value,
      '品名說明': document.getElementById('cfg-item-desc').value,
      '品名代號': '2',
      '可刷卡': 'N',
      '手機支付': 'N'
    }
  };

  showLoading(true, "正在產出黑貓標準 CSV...", "符合 27 欄位規範與 UTF-8 BOM 編碼");
  fetch('/api/export_csv', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  .then(r => r.json())
  .then(res => {
    showLoading(false);
    if (res.filename) {
      alert(`🎉 成功匯出至黑貓標準出貨單！\n檔案名稱：${res.filename}\n已儲存至當前工作目錄。`);
      loadHistoryCsvs();
      window.location.href = `/download/${encodeURIComponent(res.filename)}`;
    }
  })
  .catch(err => {
    showLoading(false);
    alert('匯出失敗：' + err);
  });
}

function showLoading(show, title, subtext) {
  const overlay = document.getElementById('loading-overlay');
  if (show) {
    document.getElementById('loadingText').textContent = title || "正在處理中...";
    document.getElementById('loadingSubtext').textContent = subtext || "透過 Apple Vision 引擎進行高精度辨識";
    overlay.style.display = 'flex';
  } else {
    overlay.style.display = 'none';
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
</script>
</body>
</html>
"""

class YamatoRequestHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path
        cdir = get_current_dir()
        
        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return
            
        elif path == "/api/get_current_dir":
            self.send_json({"dir": str(cdir), "name": cdir.name})
            return
            
        elif path == "/api/list_files":
            valid_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.heic', '.webp']
            files = []
            if cdir.exists() and cdir.is_dir():
                files = [
                    f.name for f in cdir.iterdir()
                    if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith('.')
                ]
            self.send_json(sorted(files))
            return
            
        elif path == "/api/list_csvs":
            csvs = []
            if cdir.exists() and cdir.is_dir():
                for f in sorted(cdir.glob("黑貓出貨單_*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
                    stat = f.stat()
                    csvs.append({
                        "name": f.name,
                        "size": f"{stat.st_size / 1024:.1f} KB",
                        "time": datetime.fromtimestamp(stat.st_mtime).strftime("%Y/%m/%d %H:%M:%S")
                    })
            self.send_json(csvs)
            return
            
        elif path.startswith("/download/"):
            filename = urllib.parse.unquote(path.replace("/download/", ""))
            file_path = cdir / filename
            if file_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}")
                self.send_header("Content-Length", str(file_path.stat().st_size))
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "File Not Found")
                return
                
        self.send_error(404, "Not Found")

    def do_POST(self):
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path
        cdir = get_current_dir()
        
        if path == "/api/set_current_dir":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8"))
                target_dir = payload.get("dir", "").strip()
                p = Path(target_dir).expanduser()
                if p.exists() and p.is_dir():
                    set_current_dir(p)
                    self.send_json({"success": True, "dir": str(p), "name": p.name})
                else:
                    self.send_json({"success": False, "error": f"資料夾不存在：{target_dir}"}, status=400)
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=500)
            return
            
        elif path == "/api/reset_default_dir":
            set_current_dir(BASE_DIR)
            self.send_json({"success": True, "dir": str(BASE_DIR), "name": BASE_DIR.name})
            return

        elif path == "/api/browse_dir":
            # 叫起 Mac 原生 choose folder 對話框
            try:
                curr_str = str(cdir)
                script = f'''
                tell application "System Events"
                    activate
                end tell
                try
                    set chosen to choose folder with prompt "請選擇客戶出貨單檔案目錄：" default location (POSIX file "{curr_str}")
                    return POSIX path of chosen
                on error number -128
                    return "CANCELED"
                end try
                '''
                res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
                out = res.stdout.strip()
                if out and out != "CANCELED":
                    p = Path(out)
                    if p.exists() and p.is_dir():
                        set_current_dir(p)
                        self.send_json({"success": True, "dir": str(p), "name": p.name})
                        return
                self.send_json({"success": False, "canceled": True})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, status=500)
            return

        elif path == "/api/process_file":
            # 辨識指定單一檔案
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8"))
                filename = payload.get("filename", "")
                target_path = cdir / filename
                if not target_path.exists():
                    self.send_json({"error": "檔案不存在"}, status=404)
                    return
                records = yamato_converter.convert_files_to_records([target_path])
                self.send_json({"records": records})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return
            
        elif path == "/api/process_all":
            # 批次辨識當前目錄全部檔案
            try:
                records = yamato_converter.auto_process_directory(cdir)
                self.send_json({"records": records})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return
            
        elif path == "/api/export_csv":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8"))
                records = payload.get("records", [])
                config = payload.get("config", {})
                source_name = payload.get("source_name", "")
                
                today_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                if source_name and "目錄全部檔案" not in source_name:
                    stem = Path(source_name).stem
                    clean_stem = re.sub(r'[\s:]+', '_', stem)
                    filename = f"黑貓出貨單_{clean_stem}_{today_str}.csv"
                else:
                    filename = f"黑貓出貨單_{today_str}.csv"
                    
                out_path = cdir / filename
                yamato_converter.export_to_yamato_csv(records, out_path, default_config=config)
                self.send_json({"filename": filename, "count": len(records)})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return
            
        elif path == "/api/upload":
            # 接收拖曳上傳之檔案，存入當前目錄並進行單檔辨識
            try:
                content_type = self.headers.get('Content-Type', '')
                if 'multipart/form-data' not in content_type:
                    self.send_json({"success": False, "error": "非 multipart/form-data 請求"}, status=400)
                    return
                    
                m_bound = re.search(r'boundary=([^;\s]+)', content_type)
                if not m_bound:
                    self.send_json({"success": False, "error": "缺少 boundary 標記"}, status=400)
                    return
                    
                boundary = m_bound.group(1).strip('"\'').encode()
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)
                
                parts = body.split(b'--' + boundary)
                uploaded_paths = []
                uploaded_names = []
                
                for p in parts:
                    if b'filename=' in p or b'filename*=' in p:
                        header_end = p.find(b'\r\n\r\n')
                        if header_end == -1:
                            continue
                        header = p[:header_end].decode('utf-8', errors='ignore')
                        
                        fname = None
                        m_utf8 = re.search(r"filename\*=UTF-8''([^\s;\r\n]+)", header)
                        if m_utf8:
                            fname = urllib.parse.unquote(m_utf8.group(1))
                        else:
                            m_std = re.search(r'filename="?([^";\r\n]+)"?', header, re.I)
                            if m_std:
                                fname = m_std.group(1).strip('"\'')
                                
                        if not fname:
                            continue
                            
                        clean_fname = Path(fname).name
                        file_content = p[header_end + 4:]
                        if file_content.endswith(b'--\r\n'):
                            file_content = file_content[:-4]
                        elif file_content.endswith(b'\r\n'):
                            file_content = file_content[:-2]
                            
                        save_path = cdir / clean_fname
                        with open(save_path, 'wb') as f:
                            f.write(file_content)
                            
                        uploaded_paths.append(save_path)
                        uploaded_names.append(clean_fname)
                        
                if not uploaded_paths:
                    self.send_json({"success": False, "error": "未解析到有效檔案"}, status=400)
                    return
                    
                # 僅對剛上傳的檔案進行辨識
                records = yamato_converter.convert_files_to_records(uploaded_paths)
                
                # 自動為該檔案在當前目錄匯出一份獨立 CSV
                if len(uploaded_names) == 1:
                    stem = Path(uploaded_names[0]).stem
                    clean_stem = re.sub(r'[\s:]+', '_', stem)
                    csv_path = cdir / f"黑貓出貨單_{clean_stem}.csv"
                    yamato_converter.export_to_yamato_csv(records, csv_path)
                
                self.send_json({
                    "success": True,
                    "uploaded": uploaded_names,
                    "records": records,
                    "message": f"成功上傳並辨識 {len(uploaded_names)} 個檔案！"
                })
            except Exception as e:
                self.send_json({"success": False, "error": f"上傳辨識發生異常：{str(e)}"}, status=500)
            return
                
        self.send_error(404, "Not Found")

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, YamatoRequestHandler)
    print("=" * 60)
    print(f"🚀 黑貓宅急便出貨單轉換系統已啟動！")
    print(f"🌐 本機操作網址：http://localhost:{PORT}")
    print(f"📁 當前工作目錄：{get_current_dir()}")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n系統已正常關閉。")

if __name__ == "__main__":
    run_server()
