"""
股價資料抓取模組
==================
使用 yfinance 從 Yahoo Finance 抓取台股的 30 分鐘 / 60 分鐘 K 棒資料。
抓到的資料會自動存成 CSV，供未來機器學習與回測使用。

Yahoo Finance 對 intraday 資料的限制：
- 30 分鐘 (30m)：最多回溯 60 天
- 60 分鐘 (60m)：最多回溯 730 天 (~2 年)
- 這是 Yahoo 平台規定，不是程式問題。

作者：李孟盈
"""

import yfinance as yf
import pandas as pd
import requests
from pathlib import Path
from datetime import datetime
from typing import NamedTuple, Optional


# 各 interval 對應的最大可抓取期間（Yahoo 平台限制）
INTERVAL_MAX_PERIOD = {
    '30m': '60d',     # 30 分鐘最多 60 天
    '60m': '730d',    # 60 分鐘最多 730 天
    '1h':  '730d',
    '1d':  'max',     # 日線可抓全歷史
}


# 錯誤類別（讓 UI 可以顯示對應的友善訊息）
ERR_NETWORK     = 'NETWORK'        # 網路不通 / 連線逾時
ERR_RATE_LIMIT  = 'RATE_LIMIT'     # Yahoo 限流（HTTP 429）
ERR_INVALID     = 'INVALID_SYMBOL' # 代碼不存在 / 無資料
ERR_PARTIAL     = 'PARTIAL_DATA'   # 抓到資料但欄位不齊
ERR_OTHER       = 'OTHER'          # 其他未分類錯誤


class FetchResult(NamedTuple):
    """抓取結果。error_code 為 None 代表成功；否則參考上方常數。"""
    df: pd.DataFrame
    error_code: Optional[str]
    error_msg: Optional[str]


def _classify_exception(exc: Exception) -> tuple[str, str]:
    """把 yfinance / requests 拋出的 exception 分類成 (error_code, error_msg)。"""
    msg = str(exc).lower()
    if isinstance(exc, requests.exceptions.Timeout):
        return ERR_NETWORK, '連線逾時，請檢查網路或稍後再試'
    if isinstance(exc, requests.exceptions.ConnectionError):
        return ERR_NETWORK, '網路無法連線到 Yahoo Finance，請檢查網路連線'
    if '429' in msg or 'too many requests' in msg or 'rate limit' in msg:
        return ERR_RATE_LIMIT, 'Yahoo 限流（請求過於頻繁），請稍候 30 秒後再試'
    return ERR_OTHER, f'未預期的錯誤：{exc}'


def fetch_stock_data(symbol: str, interval: str = '30m') -> FetchResult:
    """
    從 Yahoo Finance 抓取股價資料。

    參數:
        symbol (str): 股票代碼，台股請加 ".TW"，例如 "1802.TW"
        interval (str): 時間週期，可選 "30m"、"60m"、"1d" 等

    回傳:
        FetchResult(df, error_code, error_msg)
        - 成功：df 為 DataFrame，error_code/error_msg 為 None
        - 失敗：df 為空 DataFrame，error_code 為 ERR_* 常數之一
    """
    period = INTERVAL_MAX_PERIOD.get(interval, '60d')

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=False)
    except Exception as e:
        code, msg = _classify_exception(e)
        print(f"[爬蟲錯誤] {symbol} {interval}: [{code}] {msg}")
        return FetchResult(pd.DataFrame(), code, msg)

    # 抓到空：通常代表代碼不存在；也可能是當天 Yahoo 暫時性問題
    if df.empty:
        return FetchResult(
            pd.DataFrame(),
            ERR_INVALID,
            f'找不到 {symbol} 的 {interval} 資料，請確認代碼正確（台股需加 .TW）',
        )

    # 將 index (Datetime / Date) 轉為欄位
    df = df.reset_index()

    # 統一欄名為小寫
    rename_map = {}
    for col in df.columns:
        low = col.lower()
        if low in ('datetime', 'date'):
            rename_map[col] = 'datetime'
        else:
            rename_map[col] = low.replace(' ', '_')
    df = df.rename(columns=rename_map)

    # 移除時區資訊以利後續處理（保留本地時間）
    if pd.api.types.is_datetime64_any_dtype(df['datetime']):
        try:
            df['datetime'] = df['datetime'].dt.tz_localize(None)
        except (TypeError, AttributeError):
            pass

    # 只保留 ML/回測常用欄位
    keep_cols = ['datetime', 'open', 'high', 'low', 'close', 'volume']
    available = [c for c in keep_cols if c in df.columns]

    # 欄位不齊：缺 OHLC 之一就視為部分資料
    required = {'datetime', 'open', 'high', 'low', 'close'}
    missing = required - set(available)
    if missing:
        return FetchResult(
            pd.DataFrame(),
            ERR_PARTIAL,
            f'資料欄位不齊，缺少：{", ".join(sorted(missing))}',
        )

    df = df[available]

    # 移除 OHLC 任一為空的列
    df = df.dropna(subset=['open', 'high', 'low', 'close']).reset_index(drop=True)

    if df.empty:
        return FetchResult(
            pd.DataFrame(),
            ERR_PARTIAL,
            '資料全部為空值（NaN），可能為非交易時段或停牌',
        )

    return FetchResult(df, None, None)


def save_data(df: pd.DataFrame, symbol: str, interval: str,
              data_dir: str = 'data') -> Path:
    """
    將抓到的資料存成 CSV，未來可給機器學習 / 回測程式直接讀取。

    檔名格式：{symbol}_{interval}_{抓取日期}.csv
    同時更新 latest 版本：{symbol}_{interval}_latest.csv

    參數:
        df: 要儲存的 DataFrame
        symbol: 股票代碼
        interval: 時間週期
        data_dir: 儲存資料夾（預設 "data"）

    回傳:
        Path: 已儲存檔案的路徑
    """
    if df.empty:
        return None

    Path(data_dir).mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.replace('.', '_')
    today = datetime.now().strftime('%Y%m%d')

    # 帶日期的歷史檔
    dated_path = Path(data_dir) / f"{safe_symbol}_{interval}_{today}.csv"
    df.to_csv(dated_path, index=False, encoding='utf-8-sig')

    # 最新版（覆寫）
    latest_path = Path(data_dir) / f"{safe_symbol}_{interval}_latest.csv"
    df.to_csv(latest_path, index=False, encoding='utf-8-sig')

    return latest_path


def export_to_excel(df: pd.DataFrame, symbol: str, interval: str,
                    output_dir: str = 'output') -> Optional[Path]:
    """
    把資料另存成 Excel (.xlsx) 到 output 資料夾，給回測 / 報告用。
    與 save_data() 同時呼叫即可（前者存 CSV 給程式讀、這個存 XLSX 給人看）。

    回傳 Path；若 df 為空則回 None。
    """
    if df.empty:
        return None
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.replace('.', '_')
    today = datetime.now().strftime('%Y%m%d')
    path = Path(output_dir) / f"{safe_symbol}_{interval}_{today}.xlsx"
    df.to_excel(path, index=False, sheet_name=f'{interval}_OHLCV')
    return path


def load_cached_data(symbol: str, interval: str,
                     data_dir: str = 'data') -> pd.DataFrame:
    """
    讀取先前已存的 CSV 資料。
    讓 ML / 回測程式可直接呼叫，不需要每次重新爬。

    回傳:
        DataFrame，若檔案不存在則回傳空 DataFrame。
    """
    safe_symbol = symbol.replace('.', '_')
    latest_path = Path(data_dir) / f"{safe_symbol}_{interval}_latest.csv"

    if not latest_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(latest_path, parse_dates=['datetime'])
    return df


# ---- 命令列直接執行：抓 1802.TW ----
if __name__ == '__main__':
    print('=== 台玻 (1802.TW) 股價資料抓取測試 ===\n')

    for interval in ['30m', '60m']:
        print(f'[FETCH] {interval} ...')
        result = fetch_stock_data('1802.TW', interval)
        if result.error_code:
            print(f'  [FAIL] [{result.error_code}] {result.error_msg}\n')
            continue
        df = result.df
        csv_path = save_data(df, '1802.TW', interval)
        xlsx_path = export_to_excel(df, '1802.TW', interval)
        print(f'  [OK] {len(df)} rows')
        print(f'  range: {df["datetime"].min()} ~ {df["datetime"].max()}')
        print(f'  CSV : {csv_path}')
        print(f'  XLSX: {xlsx_path}\n')
