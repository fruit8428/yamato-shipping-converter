#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vercel Serverless Function 入口
將所有 HTTP 請求代理轉發給 YamatoRequestHandler 處理
"""

import sys
from pathlib import Path

# 將專案根目錄加入模組搜尋路徑
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import YamatoRequestHandler

class handler(YamatoRequestHandler):
    """Vercel Python Serverless Function entry point"""
    pass
