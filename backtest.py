"""
回測引擎 + 績效計算
=====================
給定 K 棒資料 + 策略訊號（0/1），模擬從初始資金開始的多空切換交易，
計算 KPI（ROI / 勝率 / 最大回撤 / 風險 / 夏普比率 / 手續費 …）。

支援：
- 全倉買進（簡化）
- 固定每筆手續費
- 停損 / 停利（單位 %，0 = 不啟用）
- 訊號出場（策略訊號變 0）

單位設計（與台股現實一致）：
- 初始資金預設 NT$ 1,000,000
- 每筆固定手續費 NT$ 50

作者：李孟盈
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional


# ============ 預設常數 ============

DEFAULT_INITIAL_CAPITAL = 1_000_000   # NT$ 1,000,000
DEFAULT_COMMISSION      = 50          # 每筆 NT$ 50
TRADING_BARS_PER_YEAR_60M = 252 * 5   # 60m K：每天 5 根 × 一年約 252 交易日
TRADING_BARS_PER_YEAR_30M = 252 * 9   # 30m K：每天 9 根


# ============ 資料結構 ============

@dataclass
class Trade:
    """一筆完整買進到賣出的交易紀錄。"""
    entry_time:   pd.Timestamp
    entry_price:  float
    exit_time:    pd.Timestamp
    exit_price:   float
    shares:       int
    pnl:          float            # 含手續費的淨損益（NT$）
    return_pct:   float            # 此筆的報酬率（%）
    commission:   float            # 進+出總手續費
    exit_reason:  str              # 'signal' / 'stop_loss' / 'take_profit'


@dataclass
class BacktestResult:
    """單一策略的回測結果。"""
    strategy_name:   str
    trades:          List[Trade]
    equity_curve:    pd.Series        # index = datetime, value = 帳戶總資產
    position_curve:  pd.Series        # 0/1，方便視覺化
    kpi:             dict             # 指標表


# ============ 主回測函式 ============

def run_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    commission: float = DEFAULT_COMMISSION,
    stop_loss_pct: float = 0.0,       # 0 = 不啟用，例如 5.0 代表 -5% 停損
    take_profit_pct: float = 0.0,     # 0 = 不啟用，例如 10.0 代表 +10% 停利
    strategy_name: str = '',
    interval: str = '60m',
) -> BacktestResult:
    """
    跑一個策略的回測。

    參數
    -----
    df : 必須含 datetime / close 欄
    signal : 與 df 同長度的 0/1 持倉訊號
    initial_capital : 初始現金
    commission : 每筆固定手續費（買 1 次 + 賣 1 次 → 共扣 2 倍）
    stop_loss_pct : 停損 %（持倉時若報酬 < -stop_loss_pct 則強制平倉）
    take_profit_pct : 停利 %（持倉時若報酬 > take_profit_pct 則強制平倉）
    interval : '30m' / '60m'，影響年化計算

    回傳
    -----
    BacktestResult，含 trades、equity_curve、kpi
    """
    if df.empty or signal.empty:
        return _empty_result(strategy_name)

    df = df.reset_index(drop=True)
    signal = signal.reset_index(drop=True)

    cash = initial_capital
    shares = 0
    entry_price = 0.0
    entry_time = None
    entry_commission = 0.0

    trades: List[Trade] = []
    equity = np.zeros(len(df), dtype=float)
    position = np.zeros(len(df), dtype=int)

    closes = df['close'].values
    times  = df['datetime'].values

    for i in range(len(df)):
        price = float(closes[i])
        sig = int(signal.iloc[i])
        equity_before_action = cash + shares * price

        # === 持倉中：先檢查停損 / 停利，再檢查訊號出場 ===
        if shares > 0:
            ret_pct = (price - entry_price) / entry_price * 100

            forced_exit_reason: Optional[str] = None
            if stop_loss_pct > 0 and ret_pct <= -stop_loss_pct:
                forced_exit_reason = 'stop_loss'
            elif take_profit_pct > 0 and ret_pct >= take_profit_pct:
                forced_exit_reason = 'take_profit'

            should_exit = forced_exit_reason is not None or sig == 0
            if should_exit:
                # 賣出
                proceeds = shares * price - commission
                cash += proceeds
                pnl = (price - entry_price) * shares - (entry_commission + commission)
                cost_basis = entry_price * shares + entry_commission
                trade = Trade(
                    entry_time   = pd.Timestamp(entry_time),
                    entry_price  = entry_price,
                    exit_time    = pd.Timestamp(times[i]),
                    exit_price   = price,
                    shares       = shares,
                    pnl          = pnl,
                    return_pct   = pnl / cost_basis * 100 if cost_basis else 0.0,
                    commission   = entry_commission + commission,
                    exit_reason  = forced_exit_reason or 'signal',
                )
                trades.append(trade)
                shares = 0
                entry_price = 0.0
                entry_commission = 0.0
                entry_time = None

        # === 空手中：檢查訊號進場 ===
        if shares == 0 and sig == 1 and cash > commission:
            # 全倉買進（用剩餘 cash 算最大張數）
            buyable_cash = cash - commission
            shares_bought = int(buyable_cash // price)
            if shares_bought > 0:
                cash -= shares_bought * price + commission
                shares = shares_bought
                entry_price = price
                entry_time = times[i]
                entry_commission = commission

        equity[i] = cash + shares * price
        position[i] = 1 if shares > 0 else 0

    # 結束時若還持倉，按最後價強制平倉（簡化）
    if shares > 0:
        i = len(df) - 1
        price = float(closes[i])
        proceeds = shares * price - commission
        cash += proceeds
        pnl = (price - entry_price) * shares - (entry_commission + commission)
        cost_basis = entry_price * shares + entry_commission
        trades.append(Trade(
            entry_time   = pd.Timestamp(entry_time),
            entry_price  = entry_price,
            exit_time    = pd.Timestamp(times[i]),
            exit_price   = price,
            shares       = shares,
            pnl          = pnl,
            return_pct   = pnl / cost_basis * 100 if cost_basis else 0.0,
            commission   = entry_commission + commission,
            exit_reason  = 'force_close_eod',
        ))
        equity[i] = cash
        shares = 0

    equity_series = pd.Series(equity, index=df['datetime'], name='equity')
    position_series = pd.Series(position, index=df['datetime'], name='position')

    kpi = _calc_kpi(trades, equity_series, initial_capital, interval)

    return BacktestResult(
        strategy_name  = strategy_name,
        trades         = trades,
        equity_curve   = equity_series,
        position_curve = position_series,
        kpi            = kpi,
    )


# ============ KPI 計算 ============

def _calc_kpi(trades: List[Trade], equity: pd.Series,
              initial_capital: float, interval: str) -> dict:
    """
    計算所有 KPI。回傳 dict（key 是中文標籤、value 是格式化過的字串）。
    """
    if equity.empty:
        return {}

    final_equity = float(equity.iloc[-1])
    total_pnl = final_equity - initial_capital
    roi = total_pnl / initial_capital * 100 if initial_capital else 0.0

    # 交易層面
    n_trades = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / n_trades * 100 if n_trades else 0.0
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0.0
    avg_loss = np.mean([t.pnl for t in losses]) if losses else 0.0
    total_commission = sum(t.commission for t in trades)

    # 風險：用每根 K 棒的權益報酬率計算
    eq_returns = equity.pct_change().dropna()
    bars_per_year = TRADING_BARS_PER_YEAR_60M if interval == '60m' else TRADING_BARS_PER_YEAR_30M
    if len(eq_returns) > 1:
        annual_vol = eq_returns.std() * np.sqrt(bars_per_year) * 100   # %
        annual_return = eq_returns.mean() * bars_per_year * 100        # %
        sharpe = annual_return / annual_vol if annual_vol else 0.0
    else:
        annual_vol = 0.0
        sharpe = 0.0

    # 最大回撤
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = float(drawdown.min()) * 100 if not drawdown.empty else 0.0

    # 出場原因統計
    exit_reasons = pd.Series([t.exit_reason for t in trades]).value_counts().to_dict()
    exit_summary = ' / '.join(f'{k}:{v}' for k, v in exit_reasons.items()) if exit_reasons else '—'

    return {
        '初始資金':       f'NT$ {initial_capital:,.0f}',
        '最終資產':       f'NT$ {final_equity:,.0f}',
        '總損益 (盈虧)':  f'NT$ {total_pnl:+,.0f}',
        'ROI (報酬率)':   f'{roi:+.2f} %',
        '交易次數':       n_trades,
        '勝率':           f'{win_rate:.1f} %',
        '平均賺':         f'NT$ {avg_win:+,.0f}',
        '平均賠':         f'NT$ {avg_loss:+,.0f}',
        '最大回撤 (MDD)': f'{max_dd:.2f} %',
        '風險 (年化波動)': f'{annual_vol:.2f} %',
        '夏普比率':       f'{sharpe:.2f}',
        '總手續費':       f'NT$ {total_commission:,.0f}',
        '出場原因':       exit_summary,
    }


def _empty_result(name: str) -> BacktestResult:
    return BacktestResult(
        strategy_name  = name,
        trades         = [],
        equity_curve   = pd.Series(dtype=float),
        position_curve = pd.Series(dtype=int),
        kpi            = {},
    )


# ============ 多策略並列回測（給 UI 用） ============

def run_multi_strategy(
    df: pd.DataFrame,
    strategy_funcs: dict,            # {name: fn(df)->signal}
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    commission: float = DEFAULT_COMMISSION,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    interval: str = '60m',
) -> List[BacktestResult]:
    """並列跑多個策略，回傳每個策略的回測結果列表。"""
    results = []
    for name, fn in strategy_funcs.items():
        sig = fn(df)
        r = run_backtest(
            df              = df,
            signal          = sig,
            initial_capital = initial_capital,
            commission      = commission,
            stop_loss_pct   = stop_loss_pct,
            take_profit_pct = take_profit_pct,
            strategy_name   = name,
            interval        = interval,
        )
        results.append(r)
    return results


def kpi_table(results: List[BacktestResult]) -> pd.DataFrame:
    """把多個策略的 KPI 攤成一個 DataFrame，欄=策略、列=指標。"""
    if not results:
        return pd.DataFrame()
    data = {r.strategy_name: r.kpi for r in results if r.kpi}
    return pd.DataFrame(data)


# ---- 命令列直接執行：對 1802.TW 跑全部策略 ----
if __name__ == '__main__':
    from scraper import fetch_stock_data
    from strategies import STRATEGIES

    print('=== 對 1802.TW 60m 跑 6 個策略回測 ===')
    print(f'初始資金 NT$ {DEFAULT_INITIAL_CAPITAL:,} / 手續費 NT$ {DEFAULT_COMMISSION} / 停損 5% / 停利 10%\n')

    result = fetch_stock_data('1802.TW', '60m')
    if result.error_code:
        print(f'抓資料失敗：{result.error_msg}')
    else:
        df = result.df
        results = run_multi_strategy(
            df, STRATEGIES,
            stop_loss_pct=5.0,
            take_profit_pct=10.0,
            interval='60m',
        )
        table = kpi_table(results)
        print(table.to_string())
