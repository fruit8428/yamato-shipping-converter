#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黑貓宅急便出貨單自動轉換系統 - Web 視覺化操作介面
支援 Google Gemini 3.6 Flash 雲端多模態 AI 辨識 與 macOS 原生 Vision OCR 雙引擎
可於本機直接執行，亦可無縫部署至 Vercel Serverless
"""

import os
import sys
import re
import io
import csv
import json
import mimetypes
import urllib.parse
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime

# 確保引用本目錄模組
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import gemini_converter

# 若在 macOS 本機，嘗試引入原生 OCR 引擎
try:
    import yamato_converter
    HAS_LOCAL_OCR = True
except Exception:
    HAS_LOCAL_OCR = False

CONFIG_FILE = BASE_DIR / "config.json"
CURRENT_DIR = BASE_DIR
PORT = 8765
IS_CLOUD = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

def get_current_dir() -> Path:
    """取得當前工作目錄"""
    global CURRENT_DIR
    if not IS_CLOUD and CONFIG_FILE.exists():
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
    if not IS_CLOUD:
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
.brand-title h1 { font-size: 22px; font-weight: 700; color: var(--primary-dark); display: flex; align-items: center; gap: 10px; }
.brand-title p { font-size: 13px; color: var(--text-muted); }
.engine-badge { font-size: 11.5px; font-weight: 600; background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 3px 10px; border-radius: 999px; }

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
.card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; padding: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 16px; }

/* API Key Card */
.api-card { border-left: 4px solid #10b981; }
.api-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.api-title { font-size: 13px; font-weight: 700; color: var(--text-main); display: flex; align-items: center; gap: 6px; }
.api-status { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 999px; }
.api-status.ready { background: #d1fae5; color: #065f46; }
.api-status.missing { background: #fef3c7; color: #92400e; }
.api-input-wrap { display: flex; gap: 6px; }
.api-input { flex: 1; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--border); font-size: 12px; font-family: monospace; }
.api-input:focus { border-color: #10b981; outline: none; }

/* Directory switch card */
.dir-card { border-left: 4px solid var(--primary); }
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
#loading-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 100; align-items: center; justify-content: center; flex-direction: column; color: white; backdrop-filter: blur(3px); }
.spinner { width: 50px; height: 50px; border: 5px solid rgba(255,255,255,0.3); border-top-color: #ffffff; border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 16px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div id="loading-overlay">
  <div class="spinner"></div>
  <div style="font-size: 18px; font-weight: 700;" id="loadingText">正在處理中...</div>
  <div style="font-size: 13px; opacity: 0.85; margin-top: 6px;" id="loadingSubtext">透過 Google Gemini 3.6 Flash 進行多模態高精度辨識</div>
</div>

<div class="container">
  <header>
    <div class="brand">
      <div class="brand-logo">🐱</div>
      <div class="brand-title">
        <h1>
          黑貓宅急便出貨單自動轉換系統
          <span class="engine-badge" id="engineBadge">✨ Google Gemini 3.6 Flash API</span>
        </h1>
        <p>都匯水果專用版 ｜ 支援 PDF、JPG、PNG、LINE 截圖辨識並一鍵匯出黑貓 27 欄標準 CSV</p>
      </div>
    </div>
    <div class="action-bar">
      <button class="btn btn-outline" id="btnRefreshDir" onclick="refreshDirectoryData()">🔄 重新整理</button>
      <button class="btn btn-outline" id="btnBatchAll" onclick="recognizeAllFiles()" title="將當前目錄中所有客戶檔案一次合併辨識">📦 批次辨識全部檔案</button>
      <button class="btn btn-export" onclick="exportCsv()">📥 匯出黑貓標準 CSV</button>
    </div>
  </header>

  <div class="grid-layout">
    <!-- Left Sidebar -->
    <div class="sidebar">
      <!-- Gemini API Key Card -->
      <div class="card api-card">
        <div class="api-header">
          <div class="api-title">
            <span>🔑</span> Google Gemini API 金鑰
          </div>
          <span class="api-status" id="apiStatusBadge">檢查中...</span>
        </div>
        <div class="api-input-wrap">
          <input type="password" id="geminiApiKeyInput" class="api-input" placeholder="AIzaSy..." oninput="handleApiKeyChange()">
          <button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="toggleApiKeyVisibility()" id="btnToggleKey">顯示</button>
        </div>
        <div style="margin-top: 8px;">
          <label style="font-size: 11px; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 4px;">AI 視覺模型核心</label>
          <select id="geminiModelSelect" onchange="handleModelChange()" style="width: 100%; font-size: 12px; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--border); background: white;">
            <option value="gemini-3.6-flash" selected>Gemini 3.6 Flash (預設・最新旗艦)</option>
            <option value="gemini-2.5-flash">Gemini 2.5 Flash (高穩定推薦)</option>
            <option value="gemini-2.0-flash">Gemini 2.0 Flash (高速輕量)</option>
          </select>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px; line-height: 1.4;">
          若遇 Google 伺服器 503 尖峰將自動重試並平滑切換備援模型。<a href="https://aistudio.google.com/app/apikey" target="_blank" style="color: #0284c7; text-decoration: underline;">免費取得金鑰</a>
        </div>
      </div>

      <!-- Directory Switch Card (for local) / Cloud Status Card (for Vercel) -->
      <div class="card dir-card" id="dirCard">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;">
          <div style="font-size:13px; font-weight:700; color:var(--text-main); display:flex; align-items:center; gap:6px;">
            <span id="dirIcon">📂</span> <span id="dirCardTitle">工作檔案目錄</span>
          </div>
          <span class="dir-badge" id="dirBadge">載入中...</span>
        </div>
        <div id="dirControlsLocal">
          <div style="display:flex; gap:6px; margin-bottom:8px;">
            <input type="text" id="dirInput" class="dir-input" placeholder="/路徑/至/資料夾" title="可手動貼上或輸入目錄路徑">
            <button class="btn btn-outline" style="padding:6px 12px; font-size:12px; white-space:nowrap;" onclick="applyManualDir()">套用</button>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-primary" style="flex:1; padding:7px 10px; font-size:12px; justify-content:center;" onclick="browseFolder()">🖥️ 瀏覽選擇資料夾...</button>
            <button class="btn btn-outline" style="padding:7px 10px; font-size:12px;" onclick="resetDefaultDir()" title="切換回系統預設出貨目錄">預設</button>
          </div>
        </div>
        <div id="dirControlsCloud" style="display:none; font-size:12px; color:var(--text-muted); line-height:1.5;">
          ☁️ <b>雲端免安裝模式</b>：支援任何裝置，拖曳或選擇 PDF/圖片即可秒速辨識，完成後直接下載標準 CSV。
        </div>
      </div>

      <div class="card">
        <!-- Drop Zone -->
        <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
          <div class="drop-icon">📥</div>
          <div class="drop-title">點擊或拖曳檔案至此辨識</div>
          <div class="drop-subtitle">支援 PDF、JPG、PNG、HEIC、WEBP</div>
          <div style="font-size: 11px; color: var(--primary); margin-top: 6px; font-weight:600;">放開後自動進行單檔高精度辨識</div>
          <input type="file" id="fileInput" multiple accept=".pdf,.jpg,.jpeg,.png,.heic,.webp" style="display:none;" onchange="handleFileSelect(event)">
        </div>

        <div class="settings-group" id="fileListGroup">
          <h3>目錄中檔案清單</h3>
          <div class="file-list" id="fileListContainer">
            <div style="color:var(--text-muted); font-size:12px; text-align:center; padding:12px;">載入中...</div>
          </div>
        </div>

        <div class="settings-group">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <h3 style="margin: 0;">黑貓出貨預設參數</h3>
            <span id="cfgSaveBadge" style="font-size: 11px; color: #10b981; font-weight: 700; display: none;">✓ 已儲存</span>
          </div>
          <div class="field-row">
            <label>溫層規格 (詳參數表)</label>
            <select id="cfg-temp" onchange="handleConfigChange()">
              <option value="2" selected>2 - 冷藏 (水果生鮮)</option>
              <option value="1">1 - 常溫</option>
              <option value="3">3 - 冷凍</option>
            </select>
          </div>
          <div class="field-row">
            <label>包裹尺寸 (詳參數表)</label>
            <select id="cfg-size" onchange="handleConfigChange()">
              <option value="2" selected>2 - 90 公分以下 (標準果盒)</option>
              <option value="1">1 - 60 公分以下</option>
              <option value="3">3 - 120 公分以下</option>
              <option value="4">4 - 150 公分以下 (限常溫)</option>
            </select>
          </div>
          <div class="field-row">
            <label>希望配達時段</label>
            <select id="cfg-time" onchange="handleConfigChange()">
              <option value="1" selected>1 - 不指定</option>
              <option value="2">2 - 13點前</option>
              <option value="3">3 - 14~18點</option>
            </select>
          </div>
          <div class="field-row">
            <label>品名說明</label>
            <input type="text" id="cfg-item-desc" value="生鮮水果禮盒" oninput="handleConfigChange()">
          </div>
          <button class="btn btn-outline" style="width: 100%; font-size: 12px; justify-content: center; margin-top: 6px; padding: 7px 10px; font-weight: 700; color: var(--primary); border-color: var(--primary);" onclick="applyConfigToAllOrders()" title="將上方所選溫層、尺寸、時段與品名一次套用至畫面中所有訂單">
            ⚡ 套用至目前清單全部訂單
          </button>
        </div>
      </div>

      <!-- History / Exported CSVs (Local only) -->
      <div class="card history-card" id="historyCard">
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
                <th style="min-width: 105px;">溫層規格</th>
                <th style="min-width: 130px;">包裹尺寸</th>
                <th style="min-width: 110px;">配達時段</th>
                <th style="min-width: 140px;">品名說明</th>
                <th class="th-sender">寄件人姓名</th>
                <th class="th-sender-mobile">寄件人手機</th>
                <th class="th-remark">備註說明</th>
                <th class="th-src">來源檔案</th>
                <th class="col-del">操作</th>
              </tr>
            </thead>
            <tbody id="ordersTbody">
              <tr>
                <td colspan="15" style="text-align: center; padding: 80px 20px; color: var(--text-muted);">
                  <div style="font-size: 40px; margin-bottom: 12px;">📥</div>
                  <div style="font-size: 16px; font-weight: 700; color: #334155;">清單目前為空</div>
                  <div style="font-size: 13px; margin-top: 6px; color: #64748b;">請將客戶的 PDF、訂單截圖或照片拖曳至左側上傳區，系統將自動進行多模態 AI 辨識</div>
                  <div style="font-size: 12px; margin-top: 10px; color: #94a3b8;">（支援表格排版自動萃取、LINE 截圖地址解析與寄件人資訊比對）</div>
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
let isCloudEnv = false;
let serverHasEnvKey = false;

// 初始化
function initApp() {
  loadSavedApiKey();
  loadSavedConfig();
  loadCurrentDir();
  renderTable();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

function getApiKey() {
  return (localStorage.getItem('yamato_gemini_api_key') || '').trim();
}

function getSelectedModel() {
  return localStorage.getItem('yamato_gemini_model') || 'gemini-3.6-flash';
}

function handleModelChange() {
  const sel = document.getElementById('geminiModelSelect');
  if (!sel) return;
  const m = sel.value;
  localStorage.setItem('yamato_gemini_model', m);
  const badge = document.getElementById('engineBadge');
  if (badge) {
    if (m === 'gemini-3.6-flash') badge.textContent = "✨ Google Gemini 3.6 Flash API";
    else if (m === 'gemini-2.5-flash') badge.textContent = "✨ Google Gemini 2.5 Flash API";
    else badge.textContent = `✨ ${m}`;
  }
}

function loadSavedApiKey() {
  const saved = getApiKey();
  if (saved) {
    document.getElementById('geminiApiKeyInput').value = saved;
  }
  const savedModel = getSelectedModel();
  if (savedModel && document.getElementById('geminiModelSelect')) {
    document.getElementById('geminiModelSelect').value = savedModel;
    handleModelChange();
  }
  updateApiStatusUI();
}

function getConfig() {
  return {
    '溫層': document.getElementById('cfg-temp').value,
    '尺寸': document.getElementById('cfg-size').value,
    '希望配達時間': document.getElementById('cfg-time').value,
    '品名說明': (document.getElementById('cfg-item-desc').value || '').trim() || '生鮮水果禮盒',
    '品名代號': '2',
    '可刷卡': 'N',
    '手機支付': 'N'
  };
}

function handleConfigChange() {
  const cfg = getConfig();
  localStorage.setItem('yamato_default_config', JSON.stringify(cfg));
  const badge = document.getElementById('cfgSaveBadge');
  if (badge) {
    badge.style.display = 'inline';
    clearTimeout(window._cfgTimeout);
    window._cfgTimeout = setTimeout(() => { badge.style.display = 'none'; }, 2000);
  }
}

function loadSavedConfig() {
  try {
    const saved = localStorage.getItem('yamato_default_config');
    if (saved) {
      const cfg = JSON.parse(saved);
      if (cfg['溫層'] && document.getElementById('cfg-temp')) document.getElementById('cfg-temp').value = cfg['溫層'];
      if (cfg['尺寸'] && document.getElementById('cfg-size')) document.getElementById('cfg-size').value = cfg['尺寸'];
      if (cfg['希望配達時間'] && document.getElementById('cfg-time')) document.getElementById('cfg-time').value = cfg['希望配達時間'];
      if (cfg['品名說明'] && document.getElementById('cfg-item-desc')) document.getElementById('cfg-item-desc').value = cfg['品名說明'];
    }
  } catch(e) {}
}

function applyConfigToAllOrders() {
  const cfg = getConfig();
  handleConfigChange();
  if (currentOrders.length === 0) {
    alert('已儲存設定！後續辨識之出貨單將預設使用此組參數：\n溫層: ' + cfg['溫層'] + '、尺寸: ' + cfg['尺寸'] + '、配達時段: ' + cfg['希望配達時間'] + '、品名: ' + cfg['品名說明']);
    return;
  }
  for (let r of currentOrders) {
    r['溫層(詳參數表)'] = cfg['溫層'];
    r['溫層'] = cfg['溫層'];
    r['尺寸(詳參數表)'] = cfg['尺寸'];
    r['尺寸'] = cfg['尺寸'];
    r['希望配達時間(詳參數表)'] = cfg['希望配達時間'];
    r['希望配達時間'] = cfg['希望配達時間'];
    r['品名說明'] = cfg['品名說明'];
  }
  renderTable();
  alert(`✅ 已成功將出貨參數套用至目前全部 ${currentOrders.length} 筆訂單！\n溫層：${cfg['溫層']}\n包裹尺寸：${cfg['尺寸']}\n配達時段：${cfg['希望配達時間']}\n品名說明：${cfg['品名說明']}`);
}

function handleApiKeyChange() {
  const val = document.getElementById('geminiApiKeyInput').value.trim();
  if (val) {
    localStorage.setItem('yamato_gemini_api_key', val);
  } else {
    localStorage.removeItem('yamato_gemini_api_key');
  }
  updateApiStatusUI();
}

function toggleApiKeyVisibility() {
  const inp = document.getElementById('geminiApiKeyInput');
  const btn = document.getElementById('btnToggleKey');
  if (inp.type === 'password') {
    inp.type = 'text';
    btn.textContent = '隱藏';
  } else {
    inp.type = 'password';
    btn.textContent = '顯示';
  }
}

function updateApiStatusUI() {
  const badge = document.getElementById('apiStatusBadge');
  const key = getApiKey();
  if (serverHasEnvKey) {
    badge.textContent = "🟢 雲端金鑰已配置";
    badge.className = "api-status ready";
    badge.title = "已從伺服器環境變數 GEMINI_API_KEY 取得金鑰";
  } else if (key) {
    badge.textContent = "🟢 本地金鑰已就緒";
    badge.className = "api-status ready";
    badge.title = "已從瀏覽器儲存區讀取金鑰";
  } else {
    badge.textContent = "🟡 請設定金鑰";
    badge.className = "api-status missing";
    badge.title = "尚未設定 Google Gemini API 金鑰";
  }
}

// 取得當前工作目錄與環境資訊
function loadCurrentDir() {
  fetch('/api/get_current_dir')
    .then(r => r.json())
    .then(data => {
      isCloudEnv = Boolean(data.is_cloud);
      serverHasEnvKey = Boolean(data.has_env_key);
      updateApiStatusUI();

      if (isCloudEnv) {
        document.getElementById('dirCardTitle').textContent = "雲端服務狀態";
        document.getElementById('dirIcon').textContent = "☁️";
        document.getElementById('dirBadge').textContent = "Vercel 線上運行";
        document.getElementById('dirControlsLocal').style.display = "none";
        document.getElementById('dirControlsCloud').style.display = "block";
        document.getElementById('fileListGroup').style.display = "none";
        document.getElementById('historyCard').style.display = "none";
        document.getElementById('btnRefreshDir').style.display = "none";
        document.getElementById('btnBatchAll').style.display = "none";
      } else {
        if (data.dir) {
          document.getElementById('dirInput').value = data.dir;
          document.getElementById('dirBadge').textContent = data.name || "現行目錄";
          document.getElementById('dirBadge').title = data.dir;
          loadDirectoryFiles();
          loadHistoryCsvs();
        }
      }
    })
    .catch(() => {
      // 離線或純前端情況
      updateApiStatusUI();
    });
}

// 瀏覽選擇目錄 (叫起 Mac 原生資料夾選擇視窗)
function browseFolder() {
  showLoading(true, "請在跳出的視窗中選擇資料夾...", "若未跳出，請檢查畫面提示");
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
      }
    })
    .catch(err => {
      showLoading(false);
      alert('切換目錄失敗：' + err);
    });
}

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
      alert(`✅ 已成功切換至目錄：\\n${data.dir}`);
    } else {
      alert('❌ 切換失敗：' + (data.error || '路徑無效'));
    }
  })
  .catch(err => {
    showLoading(false);
    alert('切換失敗：' + err);
  });
}

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
    uploadAndRecognizeFiles(files);
  }
});

function handleFileSelect(e) {
  if (e.target.files && e.target.files.length > 0) {
    uploadAndRecognizeFiles(e.target.files);
  }
}

// 拖曳檔案後：呼叫後端進行高精度辨識
function uploadAndRecognizeFiles(files) {
  const apiKey = getApiKey();
  const formData = new FormData();
  for (let f of files) {
    formData.append('files', f);
  }

  showLoading(true, "正在使用 Google Gemini 3.6 Flash 辨識...", "多模態視覺模型深度解析收件地址與訂單數量");
  
  const headers = {};
  if (apiKey) {
    headers['X-Gemini-API-Key'] = apiKey;
  }
  headers['X-Gemini-Model'] = getSelectedModel();
  headers['X-Yamato-Config'] = encodeURIComponent(JSON.stringify(getConfig()));

  fetch('/api/upload', { 
    method: 'POST', 
    headers: headers,
    body: formData 
  })
    .then(r => r.json())
    .then(res => {
      showLoading(false);
      if (res.success && res.records) {
        currentOrders = res.records;
        currentSourceFileName = (res.uploaded && res.uploaded.length > 0) ? res.uploaded.join(', ') : "";
        renderTable();
        if (!isCloudEnv) {
          loadDirectoryFiles();
          loadHistoryCsvs();
        }
      } else {
        alert('⚠️ 辨識提示：' + (res.error || '無法解析檔案內容'));
        if (!isCloudEnv) loadDirectoryFiles();
      }
    })
    .catch(err => {
      showLoading(false);
      alert('❌ 上傳辨識失敗：' + err);
    });
}

// 辨識當前目錄中指定的個別檔案
function recognizeSingleFile(filename) {
  const apiKey = getApiKey();
  showLoading(true, `正在辨識檔案：${filename}...`, "透過 Gemini 辨識");
  
  const headers = { 
    'Content-Type': 'application/json',
    'X-Gemini-Model': getSelectedModel(),
    'X-Yamato-Config': encodeURIComponent(JSON.stringify(getConfig()))
  };
  if (apiKey) headers['X-Gemini-API-Key'] = apiKey;

  fetch('/api/process_file', {
    method: 'POST',
    headers: headers,
    body: JSON.stringify({ filename: filename })
  })
  .then(r => r.json())
  .then(data => {
    showLoading(false);
    if (data.records) {
      currentOrders = data.records;
      currentSourceFileName = filename;
      renderTable();
    } else if (data.error) {
      alert('辨識失敗：' + data.error);
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
  const apiKey = getApiKey();
  showLoading(true, "正在批次辨識目錄中所有檔案...", "多模態解析所有文件");
  
  const headers = {
    'X-Gemini-Model': getSelectedModel(),
    'X-Yamato-Config': encodeURIComponent(JSON.stringify(getConfig()))
  };
  if (apiKey) headers['X-Gemini-API-Key'] = apiKey;

  fetch('/api/process_all', { method: 'POST', headers: headers })
    .then(r => r.json())
    .then(data => {
      showLoading(false);
      if (data.records) {
        currentOrders = data.records;
        currentSourceFileName = "當前目錄全部檔案合併";
        renderTable();
        loadHistoryCsvs();
      } else if (data.error) {
        alert('批次辨識失敗：' + data.error);
      }
    })
    .catch(err => {
      showLoading(false);
      alert('批次辨識失敗：' + err);
    });
}

function loadDirectoryFiles() {
  if (isCloudEnv) return;
  fetch('/api/list_files')
    .then(r => r.json())
    .then(files => {
      const container = document.getElementById('fileListContainer');
      if (!files || files.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted); font-size:12px; text-align:center; padding:12px;">當前目錄下尚無客戶檔案</div>';
        return;
      }
      container.innerHTML = files.map(f => `
        <div class="file-chip">
          <span class="file-chip-name" title="${f}">📄 ${f}</span>
          <button class="btn-mini" onclick="recognizeSingleFile('${escapeHtml(f)}')">辨識此檔</button>
        </div>
      `).join('');
    })
    .catch(() => {});
}

function loadHistoryCsvs() {
  if (isCloudEnv) return;
  fetch('/api/list_csvs')
    .then(r => r.json())
    .then(csvs => {
      const container = document.getElementById('historyList');
      if (!csvs || csvs.length === 0) {
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
    })
    .catch(() => {});
}

function clearTable() {
  if (currentOrders.length > 0 && !confirm("確定要清空目前畫面上的訂單清單嗎？")) return;
  currentOrders = [];
  currentSourceFileName = "";
  renderTable();
}

function renderTable() {
  const tbody = document.getElementById('ordersTbody');
  const countBadge = document.getElementById('orderCountBadge');
  const sourceTag = document.getElementById('currentSourceTag');

  if (currentOrders.length === 0) {
    countBadge.textContent = "目前無資料";
    sourceTag.style.display = "none";
    tbody.innerHTML = `
      <tr>
        <td colspan="15" style="text-align: center; padding: 80px 20px; color: var(--text-muted);">
          <div style="font-size: 40px; margin-bottom: 12px;">📥</div>
          <div style="font-size: 16px; font-weight: 700; color: #334155;">清單目前為空</div>
          <div style="font-size: 13px; margin-top: 6px; color: #64748b;">請將客戶的 PDF、訂單截圖或照片拖曳至左側上傳區，系統將自動進行多模態 AI 辨識</div>
          <div style="font-size: 12px; margin-top: 10px; color: #94a3b8;">（支援表格排版自動萃取、LINE 截圖地址解析與寄件人資訊比對）</div>
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

  const sysCfg = getConfig();

  tbody.innerHTML = currentOrders.map((r, i) => {
    const curTemp = String(r['溫層(詳參數表)'] || r['溫層'] || sysCfg['溫層'] || '2');
    const curSize = String(r['尺寸(詳參數表)'] || r['尺寸'] || sysCfg['尺寸'] || '2');
    const curTime = String(r['希望配達時間(詳參數表)'] || r['希望配達時間'] || sysCfg['希望配達時間'] || '1');
    const curDesc = r['品名說明'] || sysCfg['品名說明'] || '生鮮水果禮盒';

    return `
    <tr>
      <td class="col-num">${i + 1}</td>
      <td style="min-width: 250px;"><input type="text" value="${escapeHtml(r.收件人姓名 || '')}" placeholder="姓名/公司" onchange="updateRow(${i}, '收件人姓名', this.value)"></td>
      <td style="min-width: 140px;"><input type="text" value="${escapeHtml((r.收件人手機 || '').replace("'", ''))}" placeholder="09xxxxxxxx" onchange="updateRow(${i}, '收件人手機', this.value)"></td>
      <td style="min-width: 170px;"><input type="text" value="${escapeHtml((r.收件人電話 || '').replace("'", ''))}" placeholder="02xxxxxxx#分機" onchange="updateRow(${i}, '收件人電話', this.value)"></td>
      <td style="min-width: 440px;"><input type="text" value="${escapeHtml(r.收件人地址 || '')}" placeholder="完整配送地址" onchange="updateRow(${i}, '收件人地址', this.value)"></td>
      <td style="width: 65px; min-width: 65px;"><input type="number" min="1" style="text-align:center; font-weight:600;" value="${r.件數 || 1}" onchange="updateRow(${i}, '件數', parseInt(this.value)||1)"></td>
      <td style="min-width: 105px;">
        <select onchange="updateRow(${i}, '溫層(詳參數表)', this.value)" style="padding: 4px 6px; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px;">
          <option value="2" ${curTemp === '2' ? 'selected' : ''}>2-冷藏</option>
          <option value="1" ${curTemp === '1' ? 'selected' : ''}>1-常溫</option>
          <option value="3" ${curTemp === '3' ? 'selected' : ''}>3-冷凍</option>
        </select>
      </td>
      <td style="min-width: 130px;">
        <select onchange="updateRow(${i}, '尺寸(詳參數表)', this.value)" style="padding: 4px 6px; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px;">
          <option value="2" ${curSize === '2' ? 'selected' : ''}>2-90cm以下</option>
          <option value="1" ${curSize === '1' ? 'selected' : ''}>1-60cm以下</option>
          <option value="3" ${curSize === '3' ? 'selected' : ''}>3-120cm以下</option>
          <option value="4" ${curSize === '4' ? 'selected' : ''}>4-150cm以下</option>
        </select>
      </td>
      <td style="min-width: 110px;">
        <select onchange="updateRow(${i}, '希望配達時間(詳參數表)', this.value)" style="padding: 4px 6px; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px;">
          <option value="1" ${curTime === '1' ? 'selected' : ''}>1-不指定</option>
          <option value="2" ${curTime === '2' ? 'selected' : ''}>2-13點前</option>
          <option value="3" ${curTime === '3' ? 'selected' : ''}>3-14~18點</option>
        </select>
      </td>
      <td style="min-width: 140px;">
        <input type="text" value="${escapeHtml(curDesc)}" placeholder="品名說明" onchange="updateRow(${i}, '品名說明', this.value)">
      </td>
      <td style="min-width: 140px;"><input type="text" value="${escapeHtml(r.寄件人姓名 || '')}" placeholder="寄件人" onchange="updateRow(${i}, '寄件人姓名', this.value)"></td>
      <td style="min-width: 140px;"><input type="text" value="${escapeHtml((r.寄件人手機 || '').replace("'", ''))}" placeholder="寄件人電話" onchange="updateRow(${i}, '寄件人手機', this.value)"></td>
      <td style="min-width: 260px;"><input type="text" value="${escapeHtml(r.備註 || '')}" placeholder="備註/分機/禮盒" onchange="updateRow(${i}, '備註', this.value)"></td>
      <td style="min-width: 200px; color:var(--text-muted); font-size:12px;" title="${escapeHtml(r._來源檔案 || '')}">📄 ${escapeHtml(r._來源檔案 || '')}</td>
      <td class="col-del" onclick="deleteRow(${i})" title="刪除此筆訂單">✕</td>
    </tr>
    `;
  }).join('');
}

function updateRow(index, key, val) {
  if (key === '收件人手機' || key === '收件人電話' || key === '寄件人手機') {
    val = val ? ("'" + String(val).replace(/^'+/, '')) : '';
  }
  currentOrders[index][key] = val;
  if (key === '溫層(詳參數表)') currentOrders[index]['溫層'] = val;
  if (key === '溫層') currentOrders[index]['溫層(詳參數表)'] = val;
  if (key === '尺寸(詳參數表)') currentOrders[index]['尺寸'] = val;
  if (key === '尺寸') currentOrders[index]['尺寸(詳參數表)'] = val;
  if (key === '希望配達時間(詳參數表)') currentOrders[index]['希望配達時間'] = val;
  if (key === '希望配達時間') currentOrders[index]['希望配達時間(詳參數表)'] = val;
}

function deleteRow(index) {
  currentOrders.splice(index, 1);
  renderTable();
}

function addNewRow() {
  const cfg = getConfig();
  currentOrders.push({
    '收件人姓名': '',
    '收件人電話': '',
    '收件人手機': '',
    '收件人地址': '',
    '件數': 1,
    '溫層(詳參數表)': cfg['溫層'],
    '溫層': cfg['溫層'],
    '尺寸(詳參數表)': cfg['尺寸'],
    '尺寸': cfg['尺寸'],
    '希望配達時間(詳參數表)': cfg['希望配達時間'],
    '希望配達時間': cfg['希望配達時間'],
    '寄件人姓名': '',
    '寄件人電話': '',
    '寄件人手機': '',
    '寄件人地址': '',
    '備註': '',
    '品名說明': cfg['品名說明'],
    '_來源檔案': '手動新增'
  });
  renderTable();
}

// 匯出黑貓標準 CSV
function exportCsv() {
  if (currentOrders.length === 0) {
    alert('目前無可匯出的訂單資料！請先拖曳檔案進行辨識。');
    return;
  }

  const payload = {
    records: currentOrders,
    source_name: currentSourceFileName,
    config: getConfig()
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
    if (res.filename && res.csv_content) {
      // 在瀏覽器端直接觸發 UTF-8 BOM CSV 下載
      triggerDirectDownload(res.filename, res.csv_content);
      alert(`🎉 成功匯出至黑貓標準出貨單！\\n檔案名稱：${res.filename}\\n共 ${res.count} 筆訂單。已啟動自動下載！`);
      if (!isCloudEnv) loadHistoryCsvs();
    } else {
      alert('匯出異常：' + (res.error || '未取得 CSV 資料'));
    }
  })
  .catch(err => {
    showLoading(false);
    alert('匯出失敗：' + err);
  });
}

function triggerDirectDownload(filename, csvText) {
  // 加入 UTF-8 BOM 防止 Excel 亂碼
  const blob = new Blob(["\\ufeff" + csvText], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function showLoading(show, title, subtext) {
  const overlay = document.getElementById('loading-overlay');
  if (show) {
    document.getElementById('loadingText').textContent = title || "正在處理中...";
    document.getElementById('loadingSubtext').textContent = subtext || "透過 Google Gemini 3.6 Flash 進行多模態辨識";
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

    def get_api_key(self):
        """取得請求中的 Gemini API Key 或環境變數"""
        key = self.headers.get("X-Gemini-API-Key", "").strip()
        if not key:
            key = os.environ.get("GEMINI_API_KEY", "").strip()
        return key

    def get_model(self):
        """取得請求中指定的模型或預設模型"""
        return self.headers.get("X-Gemini-Model", "").strip() or "gemini-3.6-flash"

    def get_config(self):
        """取得請求中傳入之黑貓預設參數或預設值"""
        cfg_hdr = self.headers.get("X-Yamato-Config", "").strip()
        if cfg_hdr:
            try:
                raw_json = urllib.parse.unquote(cfg_hdr)
                cfg = json.loads(raw_json)
                if isinstance(cfg, dict):
                    return cfg
            except Exception as e:
                print("解析 X-Yamato-Config 失敗:", e)
        return {
            '溫層': '2',
            '尺寸': '2',
            '希望配達時間': '1',
            '品名說明': '生鮮水果禮盒',
            '品名代號': '2',
            '可刷卡': 'N',
            '手機支付': 'N'
        }

    def get_route_path(self):
        """解析真實路由路徑，支援本機直連與 Vercel Rewrite"""
        url_parts = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url_parts.query)
        route = qs.get("__route__", [""])[0]
        if not route:
            route = self.headers.get("x-matched-path", "")
        if not route:
            route = url_parts.path
        if route.startswith("//"):
            route = "/" + route.lstrip("/")
        if len(route) > 1 and route.endswith('/'):
            route = route[:-1]
        return route

    def do_GET(self):
        path = self.get_route_path()
        cdir = get_current_dir()
        
        if path in ["", "/", "/index.html", "/api", "/api/index"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return
            
        elif path == "/api/get_current_dir":
            has_env_key = bool(os.environ.get("GEMINI_API_KEY"))
            self.send_json({
                "dir": str(cdir) if not IS_CLOUD else "雲端環境 (Vercel)",
                "name": cdir.name if not IS_CLOUD else "Vercel Cloud",
                "is_cloud": IS_CLOUD,
                "has_env_key": has_env_key
            })
            return
            
        elif path == "/api/list_files":
            valid_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.heic', '.webp']
            files = []
            if not IS_CLOUD and cdir.exists() and cdir.is_dir():
                files = [
                    f.name for f in cdir.iterdir()
                    if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith('.')
                ]
            self.send_json(sorted(files))
            return
            
        elif path == "/api/list_csvs":
            csvs = []
            if not IS_CLOUD and cdir.exists() and cdir.is_dir():
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
            if not IS_CLOUD and file_path.exists():
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
        path = self.get_route_path()
        cdir = get_current_dir()
        api_key = self.get_api_key()
        model = self.get_model()
        user_cfg = self.get_config()
        
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
            if IS_CLOUD:
                self.send_json({"success": False, "error": "雲端模式不支援本機資料夾選擇"})
                return
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
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8"))
                filename = payload.get("filename", "")
                target_path = cdir / filename
                if not target_path.exists():
                    self.send_json({"error": "檔案不存在"}, status=404)
                    return
                
                # 優先使用 Gemini 3.6 Flash
                if api_key:
                    with open(target_path, "rb") as f:
                        file_bytes = f.read()
                    mime_type = gemini_converter.get_mime_type(target_path.name, file_bytes)
                    gemini_data = gemini_converter.call_gemini_api(
                        file_bytes=file_bytes,
                        mime_type=mime_type,
                        filename=target_path.name,
                        api_key=api_key,
                        model=model
                    )
                    records = gemini_converter.convert_gemini_response_to_yamato_records(
                        gemini_data, 
                        filename=target_path.name,
                        default_config=user_cfg
                    )
                elif HAS_LOCAL_OCR:
                    records = yamato_converter.convert_files_to_records([target_path])
                else:
                    self.send_json({"error": "請先設定 Google Gemini API Key（可在左側設定欄輸入或於環境變數設定）"}, status=400)
                    return

                self.send_json({"records": records})
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return
            
        elif path == "/api/process_all":
            try:
                if IS_CLOUD:
                    self.send_json({"error": "雲端模式請直接拖曳檔案上傳辨識"}, status=400)
                    return
                if HAS_LOCAL_OCR and not api_key:
                    records = yamato_converter.auto_process_directory(cdir)
                else:
                    valid_exts = ['.pdf', '.jpg', '.jpeg', '.png', '.heic', '.webp']
                    files = [
                        f for f in cdir.iterdir() 
                        if f.is_file() and f.suffix.lower() in valid_exts and not f.name.startswith('.')
                    ]
                    records = []
                    for f in files:
                        with open(f, "rb") as fp:
                            fb = fp.read()
                        mt = gemini_converter.get_mime_type(f.name, fb)
                        gdata = gemini_converter.call_gemini_api(fb, mt, filename=f.name, api_key=api_key, model=model)
                        recs = gemini_converter.convert_gemini_response_to_yamato_records(gdata, filename=f.name, default_config=user_cfg)
                        records.extend(recs)
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
                if source_name and "全部" not in source_name and "," not in source_name:
                    stem = Path(source_name).stem
                    clean_stem = re.sub(r'[\s:]+', '_', stem)
                    filename = f"黑貓出貨單_{clean_stem}_{today_str}.csv"
                else:
                    filename = f"黑貓出貨單_{today_str}.csv"
                    
                # 產出標準 CSV 文字
                csv_text = gemini_converter.export_records_to_csv_text(records, default_config=config or user_cfg)
                
                # 若非雲端環境，同時儲存至本機目錄
                if not IS_CLOUD:
                    try:
                        out_path = cdir / filename
                        with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
                            f.write(csv_text)
                    except Exception as e:
                        print("本機儲存 CSV 失敗:", e)

                self.send_json({
                    "filename": filename, 
                    "count": len(records),
                    "csv_content": csv_text
                })
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
            return
            
        elif path == "/api/upload":
            # 接收上傳之檔案並使用 Gemini 3.6 Flash 或原生 OCR 進行辨識
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
                uploaded_files = [] # list of (clean_fname, file_bytes)
                
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
                            
                        uploaded_files.append((clean_fname, file_content))
                        
                if not uploaded_files:
                    self.send_json({"success": False, "error": "未解析到有效檔案"}, status=400)
                    return
                    
                all_records = []
                uploaded_names = [f[0] for f in uploaded_files]

                # 辨識處理
                if api_key:
                    # 使用 Google Gemini 3.6 Flash API
                    for clean_fname, file_bytes in uploaded_files:
                        mime_type = gemini_converter.get_mime_type(clean_fname, file_bytes)
                        gdata = gemini_converter.call_gemini_api(
                            file_bytes=file_bytes,
                            mime_type=mime_type,
                            filename=clean_fname,
                            api_key=api_key,
                            model=model
                        )
                        recs = gemini_converter.convert_gemini_response_to_yamato_records(
                            gdata,
                            filename=clean_fname,
                            default_config=user_cfg
                        )
                        all_records.extend(recs)
                elif not IS_CLOUD and HAS_LOCAL_OCR:
                    # 本機環境且無 API Key：自動降級至 macOS 原生 Vision OCR
                    saved_paths = []
                    for clean_fname, file_bytes in uploaded_files:
                        save_path = cdir / clean_fname
                        with open(save_path, 'wb') as f:
                            f.write(file_bytes)
                        saved_paths.append(save_path)
                    all_records = yamato_converter.convert_files_to_records(saved_paths)
                else:
                    self.send_json({
                        "success": False, 
                        "error": "請先輸入 Google Gemini API Key（可在左側輸入，或在 Vercel 環境變數中設定 GEMINI_API_KEY）。"
                    }, status=400)
                    return
                
                # 若非雲端環境且只有單一檔案，儲存一份獨立 CSV 到工作目錄
                if not IS_CLOUD and len(uploaded_names) == 1:
                    try:
                        stem = Path(uploaded_names[0]).stem
                        clean_stem = re.sub(r'[\s:]+', '_', stem)
                        csv_path = cdir / f"黑貓出貨單_{clean_stem}.csv"
                        gemini_converter.export_records_to_csv_file(all_records, str(csv_path), default_config=user_cfg)
                    except Exception as e:
                        print("寫入單檔 CSV 失敗:", e)
                
                self.send_json({
                    "success": True,
                    "uploaded": uploaded_names,
                    "records": all_records,
                    "message": f"成功辨識 {len(uploaded_names)} 個檔案，共解析出 {len(all_records)} 筆訂單！"
                })
            except Exception as e:
                self.send_json({"success": False, "error": f"辨識發生異常：{str(e)}"}, status=500)
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
    print(f"✨ 辨識引擎支援：Google Gemini 3.6 Flash API" + (" / macOS 原生 Vision" if HAS_LOCAL_OCR else ""))
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n系統已正常關閉。")

if __name__ == "__main__":
    run_server()
