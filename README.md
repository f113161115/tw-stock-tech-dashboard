# 台股技術分析儀表板（4/27 下午作業）

抓取 Yahoo Finance 上 **台玻 (1802.TW)** 等台股的 30 分鐘 / 60 分鐘 K 棒資料，並以 Streamlit 製作互動式儀表板。

---

## 一、檔案結構

```
0427下午/
├── app.py            主程式（Streamlit 介面）
├── scraper.py        資料抓取模組（給未來 ML / 回測重複使用）
├── requirements.txt  套件清單
├── README.md         本檔
└── data/             自動存放抓到的 CSV（執行後產生）
```

---

## 二、安裝套件

第一次執行前，在資料夾裡開啟終端機（CMD / PowerShell），輸入：

```bash
pip install -r requirements.txt
```

主要套件：
- `streamlit` — 建立網頁介面
- `yfinance` — 從 Yahoo Finance 抓資料
- `pandas` — 處理表格資料
- `plotly` — 互動式 K 線圖與折線圖

---

## 三、執行方式

在 `0427下午` 資料夾裡開啟終端機，輸入：

```bash
streamlit run app.py
```

執行後會自動開啟瀏覽器（網址通常是 `http://localhost:8501`）。第一次開啟會自動抓取 **1802.TW（台玻）** 的資料。

---

## 四、介面說明

| 區塊 | 內容 |
|------|------|
| **左上** | 股價折線圖（60 分鐘資料）+ 起始日期挑選器，往後顯示 50 天 |
| **右上** | K 線圖（30 分鐘資料）+ 起始日期挑選器，往後顯示 50 天 |
| **下方** | 股票代碼輸入欄位 + 重新抓取按鈕 |
| **資料摘要** | 顯示抓到的資料筆數與時間範圍，並可下載 CSV |

可輸入其他台股代碼（記得加 `.TW`），例如：
- `2330.TW` 台積電
- `2317.TW` 鴻海
- `2454.TW` 聯發科
- `1101.TW` 台泥

---

## 五、Yahoo Finance 對 intraday 資料的限制

| 時間週期 | 最大可抓取範圍 |
|---------|---------------|
| 30 分鐘 | 約 60 天 |
| 60 分鐘 | 約 730 天（2 年） |
| 日線 | 全歷史 |

> 程式已自動使用各 interval 的最大範圍。

---

## 六、未來機器學習 / 回測使用

每次抓資料時，程式會自動把資料存到 `data/` 資料夾，檔名格式：

```
1802_TW_30m_latest.csv          ← 最新版（覆寫）
1802_TW_30m_20260427.csv        ← 帶日期的歷史版本
```

未來寫機器學習 / 回測程式時，可以這樣讀取：

```python
from scraper import load_cached_data

df = load_cached_data('1802.TW', '30m')
print(df.head())
```

或直接用 pandas：

```python
import pandas as pd
df = pd.read_csv('data/1802_TW_30m_latest.csv', parse_dates=['datetime'])
```

CSV 欄位（已標準化為小寫、無空格）：
- `datetime` — 時間戳
- `open`, `high`, `low`, `close` — OHLC 價格
- `volume` — 成交量
