# 交接文件 — 台股技術分析儀表板（v2.0）

> **本檔目的**：讓任何接手者（人或 AI）在 5 分鐘內了解專案現況、決策歷程、目前卡關點。
> **最後更新**：2026-04-27（4/27 下午課程作業日當天）

---

## 一句話描述

一個 Python + Streamlit 的「台股技術分析儀表板」，已完成資料抓取、雙圖呈現、6 個交易策略、回測引擎、KPI 表格、Excel/PNG/HTML 匯出；目前卡在「**要不要做純前端 HTML+JS 版本**」這個決策點。

---

## 1. 專案目的

- **短期**：完成 114 年度日碩「程式交易實作」4/27 下午作業
- **中長期**：作為機器學習與策略回測的資料基礎設施
- 作者：李孟盈（NKUST，f113161115@nkust.edu.tw）

---

## 2. 環境

- **OS**：Windows 11
- **Python**：Anaconda Python 3.13.9（無 venv，直接用 base 環境）
- **編輯器**：VS Code
- **專案路徑**：`d:\WIN11勿動\Desktop\0420期中上午作業\0427下午\`
- **不要動到的資料夾**：`d:\WIN11勿動\Desktop\0420期中上午作業\李孟盈\`（另一份作業：貸款計算器）

### 套件清單（`requirements.txt`）

```
streamlit>=1.30.0   ← Web UI 框架
yfinance>=0.2.40    ← Yahoo Finance 資料抓取
pandas>=2.0.0       ← 資料處理
plotly>=5.18.0      ← 互動圖表
numpy>=1.24.0       ← 數值運算
openpyxl>=3.1.0     ← Excel 輸出（.xlsx）
kaleido>=0.2.1      ← Plotly to PNG（本機未裝、雲端會自動裝）
requests>=2.31.0    ← HTTP（給錯誤分類用）
```

**已裝在 Anaconda base**：streamlit, yfinance, pandas, plotly, numpy, openpyxl, requests
**未裝在本機**：kaleido（需要才裝、有 try/except 包好不會崩）

---

## 3. 檔案結構

```
0427下午/
├── 🔧 後端模組（純函式、可獨立 import）
│   ├── scraper.py        — yfinance 抓資料 + CSV/Excel 輸出 + 5 種錯誤分類
│   ├── strategies.py     — 6 個交易策略（純函式：df → 0/1 訊號）
│   ├── backtest.py       — 回測引擎、KPI 計算、停損/停利
│   └── make_report.py    — 生成靜態 HTML 報告（命令列 + 函式雙模式）
│
├── 🎨 Streamlit UI
│   └── app.py            — 主程式（互動式儀表板）
│
├── 📦 設定檔
│   ├── requirements.txt
│   ├── .gitignore        — 排除 data/, output/, 載資料/
│   └── README.md
│
├── 📁 自動產生（不進 git）
│   ├── data/             — 抓到的 OHLCV CSV 備份（_latest + 帶日期）
│   └── output/           — Excel 報表（.xlsx）+ HTML 報告（.html）
│
└── 📚 文件
    └── HANDOFF.md        — 本檔
```

---

## 4. 已完成功能

### ✅ 資料層
- yfinance 抓 30m（60 天上限）+ 60m（730 天上限）
- 自動存 CSV 到 `data/` + Excel 到 `output/`
- 5 種錯誤分類：`ERR_NETWORK / ERR_RATE_LIMIT / ERR_INVALID / ERR_PARTIAL / ERR_OTHER`
- `fetch_stock_data()` 回傳 `FetchResult(df, error_code, error_msg)` NamedTuple

### ✅ 策略層（6 個）
所有策略皆 `(df) → 0/1 持倉訊號 Series` 介面：
1. **均線突破 (MA20)** — 趨勢順勢
2. **RSI + 趨勢濾網 (MA60)** — 反轉 + 趨勢過濾（有狀態）
3. **MACD 黃金交叉** — 動能轉強
4. **布林通道突破** — 突破上軌跟進
5. **KD 黃金交叉** — 隨機指標
6. **動量回歸 (Mean Reversion)** — Z-score 反向（有狀態）

### ✅ 回測層
- `run_backtest(df, signal, ...)` 與 `run_multi_strategy(df, strategies, ...)`
- 全倉買進、固定手續費、停損 % / 停利 %（0 = 不啟用）
- KPI（13 項）：初始資金、最終資產、總損益、ROI、交易次數、勝率、平均賺、平均賠、最大回撤、年化波動、夏普比率、總手續費、出場原因統計
- 預設 NT$1,000,000 + NT$50/筆（與台股現實一致）

### ✅ Streamlit UI（`app.py`）
- **配色**：宣紙白 + 鸢尾蓝（見第 7 節規範）
- **側邊欄**：
  - 6 檔台股快速挑（1802/2330/2317/2454/2412/2882）
  - 資料來源 & Yahoo 限制說明
  - 策略多選 + 回測週期 (30m/60m) + 停損 % + 停利 % + 初始資金 + 手續費
  - 「執行回測」按鈕
- **主畫面上半**：
  - 漲跌幅 metric（4 卡：現價 / 漲跌 / 漲跌幅 / 最後更新）
  - **左**：OHLC 表格（30m，含成交量，最新在最上方）← **2026-04-27 改版**
  - **右**：折線圖（60m，可挑日期、往後 50 天）
  - 各圖表下方有 CSV 下載
- **主畫面下半（回測結果區）**：
  - **左**：含買賣訊號的 K 線圖 + 各策略權益曲線
  - **右**：KPI 表格（多策略並列）+ Excel 下載 + PNG 下載
- **下方**：股票代碼輸入欄、資料摘要展開區

### ✅ 報告匯出
- **Excel** (`build_excel_bytes` in app.py)：多 sheet — KPI 摘要、設定、各策略交易明細、原始 OHLCV
- **PNG**（`fig.to_image`，需 kaleido）：K 線回測圖，圖標題用英文避免亂碼
- **HTML 報告**（`make_report.py`）：完整快照 HTML，含 plotly 互動圖、KPI 表、雙圖、漲跌幅
  - 命令列：`python make_report.py 1802.TW [--interval 60m] [--stop-loss 5] [--take-profit 10]`
  - 內嵌 plotlyjs（離線可開）、~6 MB

---

## 5. 怎麼跑

### Streamlit 互動模式（給自己玩、探索）
```bash
cd "d:\WIN11勿動\Desktop\0420期中上午作業\0427下午"
streamlit run app.py
# 自動開瀏覽器到 http://localhost:8501
```

### 命令列：產 HTML 報告（給別人看、不需要 Python）
```bash
python make_report.py 1802.TW
python make_report.py 2330.TW --interval 30m --stop-loss 3 --take-profit 8
# 輸出：output/1802_TW_report_20260427.html
# 雙擊用瀏覽器打開（離線可看）
```

### 命令列：純抓資料（不開 streamlit）
```bash
python scraper.py
# 預設抓 1802.TW 的 30m 與 60m，存到 data/ + output/
```

### 命令列：跑後端回測測試
```bash
python backtest.py
# 對 1802.TW 60m 跑 6 策略並印 KPI 表
```

---

## 6. GitHub 部署狀態

- **Repo**：https://github.com/f113161115/tw-stock-tech-dashboard（Public）
- **最後 push commit**：`0e67e50` — feat: 加入 6 個交易策略 + 回測引擎 + KPI 表格
- **本機尚未 push**：
  - `make_report.py`（已寫完、本機可用）
  - `app.py`（版面改動：左 OHLC 表 + 右折線、K 線移除）
  - `HANDOFF.md`（本檔）

### Streamlit Community Cloud 部署
- **狀態**：未部署（使用者一度誤以為「30 天試用」實則永久免費）
- **路徑**：https://share.streamlit.io → Connect to GitHub → 選 `f113161115/tw-stock-tech-dashboard` → Main file = `app.py`
- **限制**：免費版只支援 public repo（已是 public ✓）、1GB RAM、7 天無人訪問休眠

---

## 7. 配色 / 設計規範（必守）

| 用途 | 色碼 | 說明 |
|------|------|------|
| 整體背景 | `#F9F2E0` | 宣紙白 |
| 主標題、主要按鈕 | `#1660AB` | 鸢尾蓝（主色） |
| Hover 深色 | `#0F4A85` | 鸢尾蓝加深 |
| 邊框、軸線、次要按鈕 | `#4A8BC9` | 鸢尾蓝亮版 |
| 主要文字 | `#2C3E50` | 深藍灰 |
| 次要文字、caption | `#7A8899` | 中藍灰 |
| 卡片底色 | `#FFFFFF` | 純白 |
| 圖表內底色 | `#FDFAF0` | 比宣紙白再亮一點 |
| K 線漲 | `#C0392B` | 中國紅（台股慣例：紅=漲） |
| K 線跌 | `#1660AB` | 鸢尾蓝 |
| 策略色盤（6 色） | `#E67E22 / #27AE60 / #8E44AD / #16A085 / #D35400 / #2980B9` | 回測圖每個策略一色 |

風格：書卷氣的金融感、簡約、正式、有質感。

---

## 8. ⚠️ 目前卡關的決策點

### 「要不要做純前端 HTML+JS Dashboard」？

**背景**：使用者希望「不論有沒有架設 streamlit app，都要能透過 HTML 雙擊就用」。
目前 `make_report.py` 產的是「快照型 HTML」（不能改設定，但圖表可 hover/縮放）。
使用者進一步要求：「**HTML 也要能選策略、改停損 %**」（限定 1802.TW 一檔）。

**技術評估**：可行，但要把 6 個策略 + 回測引擎用 JavaScript 重寫一份（純前端跑）。

### 三個選項

| 選項 | 內容 | 工程量 |
|---|---|---|
| **X 動工** | 把 6 策略 + 回測翻譯成 JS、寫 HTML 模板、Python 組裝。完成後使用者拿到一個獨立 HTML、能改策略停損 | ~8.5 hr |
| **Y 不動工** | 維持「streamlit + 快照 HTML」，現狀已夠交作業 | 0 hr |
| **Z 折衷** | 不重寫策略，HTML 只加「6 策略勾選顯示哪些」面板，停損固定 | ~2 hr |

### 純前端 HTML+JS 的架構提案（如果走 X 路線）

```
0427下午/
├── make_dashboard.py      ← 新建。組裝 HTML 的工廠（Python）
├── static/
│   ├── dashboard.html.tpl ← HTML 模板含 placeholder
│   ├── strategies.js      ← 6 策略翻譯成 JS（1:1 對應 strategies.py）
│   ├── backtest.js        ← 回測引擎翻譯（1:1 對應 backtest.py）
│   └── styles.css         ← 共用樣式
└── output/
    └── 1802_TW_dashboard.html  ← 最終產出
```

**運作流程**：
1. `python make_dashboard.py 1802.TW` → 抓資料 → 把 OHLCV embed 進 HTML → 寫出最終檔
2. 使用者雙擊 HTML → 瀏覽器載入 plotly.js + strategies.js + backtest.js
3. 使用者改停損 % → JS onChange → 跑 strategies.js → 跑 backtest.js → 重畫圖表 + KPI
4. 全在瀏覽器、零後端

**做得到**：選策略、改停損 %、改停利 %、即時看 KPI 變化
**做不到**：換股票（要重新跑 `python make_dashboard.py 2330.TW` 才有 2330 版）、即時抓 yfinance

---

## 9. 設計決策記錄

- **OHLC 表格用 30m 資料**（取代原本的 K 線圖）— 使用者覺得 K 線圖不直觀，要看數字
- **回測週期**讓使用者選 30m/60m（之前固定 60m）
- **資金單位**用 NT$ 1,000,000 + NT$ 50 手續費（與台股現實一致；先前討論過用 USD 但偏離真實）
- **欄名**統一小寫 `datetime/open/high/low/close/volume`，方便餵 ML
- **scraper.py 獨立**：不依賴 streamlit，可被 backtest.py / make_report.py 等模組 import
- **策略訊號協定**：每個策略回傳 `pd.Series of 0/1`（1=持倉、0=空手），出場由訊號邊緣觸發
- **PNG 圖標題用英文**：plotly to_image (kaleido) 在 Linux 容器無中文字體會亂碼

---

## 10. 給接手者的話

如果你是 **AI 接手**：請先列出 `0427下午/` 所有檔案、讀完 `app.py` / `scraper.py` / `strategies.py` / `backtest.py` 的內容，然後問使用者「**第 8 節的卡關決策要走 X / Y / Z 哪一條？**」再動手。**不要擅自開始寫程式**。

如果你是 **使用者本人**接手：請看第 8 節決定方向，然後在 VS Code Claude Code 對話框輸入「我要走 X」之類的指示。

如果你是 **老師 / 助教**：
- 看 `README.md` 了解功能
- 雙擊 `output/1802_TW_report_20260427.html` 可看到一份完整的回測報告
- 想實際操作可以執行 `streamlit run app.py`（需 Python 環境）
- GitHub repo：https://github.com/f113161115/tw-stock-tech-dashboard
