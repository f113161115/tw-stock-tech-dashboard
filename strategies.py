"""
交易策略模組
==============
6 個策略，每個都接受 OHLCV DataFrame、回傳 0/1 持倉訊號 (Series)。
- 1 = 持倉
- 0 = 空手

訊號的進出場由訊號邊緣決定（0→1=進場、1→0=出場），由 backtest.py 處理。

策略列表：
    1. 均線突破 (MA Breakout)         — 趨勢順勢
    2. RSI + 趨勢濾網                  — 反轉 + 趨勢過濾（有狀態）
    3. MACD 黃金交叉                   — 動能轉強
    4. 布林通道突破 (Bollinger Break)  — 突破上軌跟進
    5. KD 黃金交叉                     — 隨機指標
    6. 動量回歸 (Mean Reversion)       — Z-score 反向（有狀態）

作者：李孟盈
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Callable, Dict


# ============ 技術指標小工具 ============

def _ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    diff = close.diff()
    gain = diff.where(diff > 0, 0.0).rolling(n).mean()
    loss = (-diff.where(diff < 0, 0.0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = _ema(close, fast) - _ema(close, slow)
    signal_line = _ema(macd_line, signal)
    return macd_line, signal_line


def _bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    return mid + k * std, mid, mid - k * std


def _kd(df: pd.DataFrame, n: int = 9):
    low_n = df['low'].rolling(n).min()
    high_n = df['high'].rolling(n).max()
    rsv = (df['close'] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    return k, d


def _zscore(close: pd.Series, n: int = 20) -> pd.Series:
    mean = close.rolling(n).mean()
    std = close.rolling(n).std()
    return (close - mean) / std.replace(0, np.nan)


# ============ 策略 1：均線趨勢突破 (MA Breakout) ============

def strategy_ma_breakout(df: pd.DataFrame, ma_period: int = 20) -> pd.Series:
    """
    當 close 站上 MA20 → 持倉；跌破 → 出場。
    最簡單的趨勢順勢策略。
    """
    ma = _ma(df['close'], ma_period)
    return (df['close'] > ma).fillna(False).astype(int)


# ============ 策略 2：RSI + 趨勢濾網 (有狀態) ============

def strategy_rsi_with_trend(df: pd.DataFrame,
                            rsi_period: int = 14,
                            trend_ma: int = 60,
                            buy_th: float = 30,
                            sell_th: float = 70) -> pd.Series:
    """
    多頭趨勢中尋找 RSI 超賣機會：
    - 進場：close > MA60 且 RSI < 30
    - 出場：RSI > 70 或 close 跌破 MA60
    """
    rsi = _rsi(df['close'], rsi_period)
    ma_t = _ma(df['close'], trend_ma)
    close = df['close'].values
    rsi_v = rsi.values
    ma_v = ma_t.values

    pos = np.zeros(len(df), dtype=int)
    holding = False
    for i in range(len(df)):
        if np.isnan(rsi_v[i]) or np.isnan(ma_v[i]):
            continue
        if not holding:
            if close[i] > ma_v[i] and rsi_v[i] < buy_th:
                holding = True
        else:
            if rsi_v[i] > sell_th or close[i] < ma_v[i]:
                holding = False
        pos[i] = 1 if holding else 0
    return pd.Series(pos, index=df.index)


# ============ 策略 3：MACD 黃金交叉 ============

def strategy_macd_cross(df: pd.DataFrame) -> pd.Series:
    """
    MACD line > signal line → 持倉（動能向上）。
    """
    macd_line, signal_line = _macd(df['close'])
    return (macd_line > signal_line).fillna(False).astype(int)


# ============ 策略 4：布林通道突破 ============

def strategy_bollinger_break(df: pd.DataFrame,
                             n: int = 20, k: float = 2.0) -> pd.Series:
    """
    收盤站上布林上軌 → 持倉（強勢突破）；跌回中軌出場。
    用「持倉條件」單筆判斷：close > mid（站上中線）即視為持有。
    嚴格突破上軌可能訊號太少，這裡放寬為「站上中線 + 上方力道」：
        close > upper → 進場
        close < mid   → 出場（用兩段條件搭配狀態）
    """
    upper, mid, lower = _bollinger(df['close'], n, k)
    close = df['close'].values
    upper_v = upper.values
    mid_v = mid.values

    pos = np.zeros(len(df), dtype=int)
    holding = False
    for i in range(len(df)):
        if np.isnan(upper_v[i]) or np.isnan(mid_v[i]):
            continue
        if not holding:
            if close[i] > upper_v[i]:
                holding = True
        else:
            if close[i] < mid_v[i]:
                holding = False
        pos[i] = 1 if holding else 0
    return pd.Series(pos, index=df.index)


# ============ 策略 5：KD 黃金交叉 ============

def strategy_kd_cross(df: pd.DataFrame) -> pd.Series:
    """
    K > D → 持倉（隨機指標看多）；K < D → 出場。
    """
    k, d = _kd(df)
    return (k > d).fillna(False).astype(int)


# ============ 策略 6：動量回歸 (Mean Reversion) ============

def strategy_mean_reversion(df: pd.DataFrame,
                            n: int = 20,
                            entry_z: float = -1.5,
                            exit_z: float = 0.5) -> pd.Series:
    """
    用 z-score 衡量價格偏離程度：
    - 進場：zscore < -1.5（價格相對均線過度低估）
    - 出場：zscore > 0.5（價格回升至均線附近）
    對應「跌深就買、回到均值就賣」的逆勢思路。
    """
    z = _zscore(df['close'], n).values
    pos = np.zeros(len(df), dtype=int)
    holding = False
    for i in range(len(df)):
        if np.isnan(z[i]):
            continue
        if not holding:
            if z[i] < entry_z:
                holding = True
        else:
            if z[i] > exit_z:
                holding = False
        pos[i] = 1 if holding else 0
    return pd.Series(pos, index=df.index)


# ============ 策略註冊表（給 UI 用） ============

STRATEGIES: Dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    '① 均線突破 (MA20)':          strategy_ma_breakout,
    '② RSI + 趨勢濾網 (MA60)':   strategy_rsi_with_trend,
    '③ MACD 黃金交叉':           strategy_macd_cross,
    '④ 布林通道突破':             strategy_bollinger_break,
    '⑤ KD 黃金交叉':             strategy_kd_cross,
    '⑥ 動量回歸 (Mean Revert)':  strategy_mean_reversion,
}


# ---- 命令列直接執行：列出所有策略並 dry-run ----
if __name__ == '__main__':
    from scraper import fetch_stock_data

    print('=== 策略列表 ===')
    for name in STRATEGIES:
        print(f'  · {name}')

    print('\n=== 對 1802.TW 60m 跑訊號（dry run）===')
    result = fetch_stock_data('1802.TW', '60m')
    if result.error_code:
        print(f'抓資料失敗：{result.error_msg}')
    else:
        df = result.df
        for name, fn in STRATEGIES.items():
            sig = fn(df)
            n_in = int(sig.sum())
            n_total = len(sig)
            n_trades = int((sig.diff() == 1).sum())
            print(f'  {name:30s} 持倉 {n_in:>5}/{n_total} 筆 ({n_in/n_total*100:5.1f}%) | 進場 {n_trades:>3} 次')
