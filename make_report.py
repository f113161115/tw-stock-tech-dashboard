"""
靜態 HTML 報告生成器
=====================
把 K 線圖、折線圖、6 策略回測結果、KPI 表格，全部包成一份「可雙擊打開」的 HTML。

特色：
- 內嵌 plotly.js（離線也能開、不用網路）
- 圖表保留互動（hover、縮放、切換）
- 樣式維持「宣紙白 + 鸢尾蓝」主題
- 完全 self-contained，可放任何空間（GitHub Pages、學校 server、Email…）

用法：
    1. import 模式（streamlit 按鈕用）：
       from make_report import build_html_report
       html_str = build_html_report(symbol, df_30, df_60, results, meta)

    2. 命令列模式：
       python make_report.py 1802.TW
       python make_report.py 2330.TW --interval 30m --stop-loss 5 --take-profit 10

作者：李孟盈
"""

from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go

from scraper import fetch_stock_data
from strategies import STRATEGIES
from backtest import (
    BacktestResult, run_multi_strategy, kpi_table,
    DEFAULT_INITIAL_CAPITAL, DEFAULT_COMMISSION_RATE, DEFAULT_COMMISSION_MIN,
    TAX_RATE_REGULAR, TAX_RATE_DAY_TRADE,
)


# ============ 樣式（宣紙白 + 鸢尾蓝） ============

CSS = """
* { box-sizing: border-box; }
body {
    font-family: 'Microsoft JhengHei', 'PingFang TC', sans-serif;
    background-color: #F9F2E0;
    color: #2C3E50;
    margin: 0;
    padding: 24px;
    line-height: 1.6;
}
.container { max-width: 1400px; margin: 0 auto; }
h1 {
    color: #1660AB;
    letter-spacing: 3px;
    font-weight: 700;
    border-bottom: 3px solid #1660AB;
    padding-bottom: 12px;
    margin-top: 0;
}
h2 {
    color: #0F4A85;
    border-left: 5px solid #1660AB;
    padding-left: 12px;
    margin-top: 36px;
}
h3 { color: #0F4A85; }
.meta-bar {
    background: #FFFFFF;
    padding: 12px 20px;
    border-radius: 8px;
    margin-bottom: 24px;
    color: #7A8899;
    font-size: 0.9rem;
    box-shadow: 0 2px 8px rgba(22, 96, 171, 0.06);
}

/* === Metric 卡片 === */
.metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}
.metric-card {
    background: #FFFFFF;
    padding: 16px 20px;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(22, 96, 171, 0.06);
}
.metric-label { color: #7A8899; font-size: 0.85rem; }
.metric-value { color: #1660AB; font-size: 1.6rem; font-weight: 600; margin-top: 4px; }
.metric-delta-up   { color: #C0392B; font-size: 0.95rem; }
.metric-delta-down { color: #1660AB; font-size: 0.95rem; }

/* === 圖表外框 === */
.chart-wrap {
    background: #FFFFFF;
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 18px;
    box-shadow: 0 2px 12px rgba(22, 96, 171, 0.08);
}
.dual-charts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}

/* === KPI 表格 === */
.kpi-section {
    display: grid;
    grid-template-columns: 3fr 2fr;
    gap: 16px;
    margin-top: 12px;
}
table.kpi-table {
    width: 100%;
    border-collapse: collapse;
    background: #FFFFFF;
    border-radius: 8px;
    overflow: hidden;
    font-size: 0.9rem;
}
table.kpi-table thead { background: #1660AB; color: #F9F2E0; }
table.kpi-table th, table.kpi-table td {
    padding: 8px 12px;
    text-align: right;
    border-bottom: 1px solid rgba(22, 96, 171, 0.08);
}
table.kpi-table th:first-child, table.kpi-table td:first-child {
    text-align: left;
    color: #1660AB;
    font-weight: 600;
}
table.kpi-table tbody tr:hover { background: #FDFAF0; }

/* === 設定資訊 === */
.settings-box {
    background: #FFFFFF;
    padding: 12px 16px;
    border-radius: 8px;
    border-left: 4px solid #1660AB;
    margin-bottom: 12px;
    font-size: 0.9rem;
}
.settings-box span { margin-right: 16px; color: #2C3E50; }
.settings-box span b { color: #1660AB; }

footer {
    text-align: center;
    color: #7A8899;
    font-size: 0.85rem;
    padding: 24px 0;
    margin-top: 40px;
    border-top: 1px solid rgba(22, 96, 171, 0.15);
    letter-spacing: 1px;
}

@media (max-width: 900px) {
    .metrics { grid-template-columns: repeat(2, 1fr); }
    .dual-charts, .kpi-section { grid-template-columns: 1fr; }
}
"""


# ============ 圖表生成函式（給報告專用） ============

def _line_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    """折線圖，標題用英文+symbol（避免後續 PNG export 亂碼，HTML 可顯示中文）。"""
    fig = go.Figure(go.Scatter(
        x=df['datetime'], y=df['close'], mode='lines', name='Close',
        line=dict(color='#1660AB', width=2.5),
        fill='tozeroy', fillcolor='rgba(22, 96, 171, 0.08)',
    ))
    y_min, y_max = df['close'].min(), df['close'].max()
    pad = (y_max - y_min) * 0.1 if y_max > y_min else 1
    fig.update_layout(
        title=dict(text=f'{symbol} Close Price (60m)', font=dict(color='#1660AB', size=15)),
        xaxis_title='Time', yaxis_title='Price (NTD)',
        plot_bgcolor='#FDFAF0', paper_bgcolor='#FFFFFF',
        height=380, margin=dict(l=40, r=20, t=50, b=40),
        font=dict(color='#2C3E50'), hovermode='x unified',
    )
    fig.update_xaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)',
                     range=[y_min - pad, y_max + pad])
    return fig


def _candle_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    fig = go.Figure(go.Candlestick(
        x=df['datetime'], open=df['open'], high=df['high'],
        low=df['low'], close=df['close'],
        increasing_line_color='#C0392B', decreasing_line_color='#1660AB',
        increasing_fillcolor='#C0392B', decreasing_fillcolor='#1660AB',
        name='K-line',
    ))
    fig.update_layout(
        title=dict(text=f'{symbol} Candlestick (30m)', font=dict(color='#1660AB', size=15)),
        xaxis_title='Time', yaxis_title='Price (NTD)',
        plot_bgcolor='#FDFAF0', paper_bgcolor='#FFFFFF',
        height=380, margin=dict(l=40, r=20, t=50, b=40),
        xaxis_rangeslider_visible=False, font=dict(color='#2C3E50'),
    )
    fig.update_xaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    return fig


def _bt_chart(df_bt: pd.DataFrame, results: List[BacktestResult],
              symbol: str, interval: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_bt['datetime'], open=df_bt['open'], high=df_bt['high'],
        low=df_bt['low'], close=df_bt['close'],
        increasing_line_color='#C0392B', decreasing_line_color='#1660AB',
        increasing_fillcolor='#C0392B', decreasing_fillcolor='#1660AB',
        name='Price', showlegend=True,
    ))
    palette = ['#E67E22', '#27AE60', '#8E44AD', '#16A085', '#D35400', '#2980B9']
    for i, r in enumerate(results):
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatter(
            x=[t.entry_time for t in r.trades],
            y=[t.entry_price for t in r.trades],
            mode='markers', marker=dict(symbol='triangle-up', size=10, color=color),
            name=f'{r.strategy_name} BUY',
        ))
        fig.add_trace(go.Scatter(
            x=[t.exit_time for t in r.trades],
            y=[t.exit_price for t in r.trades],
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color=color, line=dict(width=1, color='#000')),
            name=f'{r.strategy_name} SELL',
        ))
    fig.update_layout(
        title=dict(text=f'{symbol} Backtest ({interval}) — Entry/Exit Markers',
                   font=dict(color='#1660AB', size=15)),
        xaxis_title='Time', yaxis_title='Price (NTD)',
        plot_bgcolor='#FDFAF0', paper_bgcolor='#FFFFFF',
        height=520, margin=dict(l=40, r=20, t=60, b=40),
        xaxis_rangeslider_visible=False, font=dict(color='#2C3E50'),
        legend=dict(orientation='h', y=-0.15),
    )
    fig.update_xaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    return fig


def _equity_chart(results: List[BacktestResult]) -> go.Figure:
    fig = go.Figure()
    palette = ['#E67E22', '#27AE60', '#8E44AD', '#16A085', '#D35400', '#2980B9']
    for i, r in enumerate(results):
        if r.equity_curve.empty:
            continue
        fig.add_trace(go.Scatter(
            x=r.equity_curve.index, y=r.equity_curve.values,
            mode='lines', name=r.strategy_name,
            line=dict(width=2, color=palette[i % len(palette)]),
            hovertemplate='%{x}<br>NT$ %{y:,.0f}<extra></extra>',
        ))
    fig.update_layout(
        title=dict(text='Equity Curves', font=dict(color='#1660AB', size=14)),
        xaxis_title='Time', yaxis_title='Equity (NTD)',
        plot_bgcolor='#FDFAF0', paper_bgcolor='#FFFFFF',
        height=320, margin=dict(l=40, r=20, t=40, b=40),
        font=dict(color='#2C3E50'),
        legend=dict(orientation='h', y=-0.2),
    )
    fig.update_xaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    return fig


# ============ 主函式：把一切組成 HTML 字串 ============

def build_html_report(
    symbol: str,
    df_30: pd.DataFrame,
    df_60: pd.DataFrame,
    results: List[BacktestResult],
    meta: dict,
) -> str:
    """
    產出完整 HTML 字串。meta 至少含：
        symbol, interval, capital, commission, stop_loss_pct, take_profit_pct
    """
    generated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # ---- Metric 卡片（用 30m 最末兩筆）----
    metric_html = ''
    if not df_30.empty and len(df_30) >= 2:
        last_close = float(df_30['close'].iloc[-1])
        prev_close = float(df_30['close'].iloc[-2])
        delta = last_close - prev_close
        pct = (delta / prev_close * 100) if prev_close else 0.0
        last_time = df_30['datetime'].iloc[-1]
        delta_class = 'metric-delta-up' if delta >= 0 else 'metric-delta-down'
        delta_sign = '+' if delta >= 0 else ''
        metric_html = f'''
        <section class="metrics">
            <div class="metric-card"><div class="metric-label">現價</div>
                <div class="metric-value">{last_close:.2f}</div></div>
            <div class="metric-card"><div class="metric-label">漲跌</div>
                <div class="metric-value">{delta:+.2f}</div>
                <div class="{delta_class}">{delta_sign}{delta:.2f}</div></div>
            <div class="metric-card"><div class="metric-label">漲跌幅</div>
                <div class="metric-value">{pct:+.2f}%</div>
                <div class="{delta_class}">{delta_sign}{pct:.2f}%</div></div>
            <div class="metric-card"><div class="metric-label">最後更新</div>
                <div class="metric-value">{last_time.strftime('%m/%d %H:%M')}</div></div>
        </section>
        '''

    # ---- 雙圖（折線 + K 線）----
    dual_html = ''
    if not df_60.empty:
        line_html = _line_chart(df_60, symbol).to_html(full_html=False, include_plotlyjs=False, div_id='line')
        dual_html += f'<div class="chart-wrap">{line_html}</div>'
    if not df_30.empty:
        candle_html = _candle_chart(df_30, symbol).to_html(full_html=False, include_plotlyjs=False, div_id='candle')
        dual_html += f'<div class="chart-wrap">{candle_html}</div>'
    dual_section = f'<section class="dual-charts">{dual_html}</section>' if dual_html else ''

    # ---- 回測區（圖 + KPI 表）----
    bt_section = ''
    if results:
        df_bt = meta['df']
        bt_chart_html = _bt_chart(df_bt, results, symbol, meta['interval']).to_html(
            full_html=False, include_plotlyjs=False, div_id='bt')
        eq_chart_html = _equity_chart(results).to_html(
            full_html=False, include_plotlyjs=False, div_id='eq')
        kpi_df = kpi_table(results)
        kpi_html = kpi_df.to_html(classes='kpi-table', border=0, escape=False)

        bt_section = f'''
        <h2>📊 策略回測結果</h2>
        <div class="settings-box">
            <span>股票：<b>{meta['symbol']}</b></span>
            <span>週期：<b>{meta['interval']}</b></span>
            <span>初始資金：<b>NT$ {meta['capital']:,.0f}</b></span>
            <span>手續費/筆：<b>NT$ {meta['commission']:,.0f}</b></span>
            <span>停損：<b>{meta['stop_loss_pct']}%</b></span>
            <span>停利：<b>{meta['take_profit_pct']}%</b></span>
        </div>

        <div class="kpi-section">
            <div>
                <div class="chart-wrap">{bt_chart_html}</div>
                <div class="chart-wrap">{eq_chart_html}</div>
            </div>
            <div class="chart-wrap">
                <h3>📋 KPI 績效表</h3>
                {kpi_html}
            </div>
        </div>
        '''

    # ---- 組裝完整 HTML（plotlyjs 內嵌只用一份） ----
    plotlyjs_holder = go.Figure().to_html(
        full_html=False,
        include_plotlyjs='inline',
        div_id='_plotly_holder',
    )
    # 我們只要它載入的 plotly.js script，不要那個空白圖。簡單做法：取出 <script> 那段，丟掉空 div。
    # plotly 的 inline 會包成 <script type="text/javascript">...</script><div id=...></div>
    # 這裡用較粗暴的字串切割，但實務上有效。
    if '<div id="_plotly_holder"' in plotlyjs_holder:
        plotlyjs_holder = plotlyjs_holder.split('<div id="_plotly_holder"')[0]

    html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{symbol} 技術分析報告 — {generated}</title>
<style>{CSS}</style>
{plotlyjs_holder}
</head>
<body>
<div class="container">
    <h1>📊 台股技術分析報告</h1>
    <div class="meta-bar">
        股票代碼 <b>{symbol}</b>　·
        生成時間 <b>{generated}</b>　·
        資料來源 Yahoo Finance
    </div>

    {metric_html}

    <h2>📈 即時走勢</h2>
    {dual_section}

    {bt_section}

    <footer>
        © 114 年度日碩 · 程式交易實作 · 4/27 下午作業<br>
        本報告由 Streamlit App 於 {generated} 凍結生成 · 圖表互動由 plotly.js 提供
    </footer>
</div>
</body>
</html>
'''
    return html


# ============ 命令列入口（連 streamlit 都不用啟） ============

def main():
    parser = argparse.ArgumentParser(description='生成靜態 HTML 技術分析報告')
    parser.add_argument('symbol', type=str, help='股票代碼，例如 1802.TW')
    parser.add_argument('--interval', type=str, default='60m', choices=['30m', '60m'],
                        help='回測週期（預設 60m）')
    parser.add_argument('--capital', type=float, default=DEFAULT_INITIAL_CAPITAL,
                        help=f'初始資金（預設 NT${DEFAULT_INITIAL_CAPITAL:,}）')
    parser.add_argument('--commission-rate', type=float, default=DEFAULT_COMMISSION_RATE * 100,
                        help='手續費率 %% (預設 0.1425，台股法定)')
    parser.add_argument('--commission-min', type=float, default=DEFAULT_COMMISSION_MIN,
                        help=f'手續費下限 NT$（預設 {DEFAULT_COMMISSION_MIN}）')
    parser.add_argument('--trade-type', type=str, default='regular',
                        choices=['regular', 'day_trade'],
                        help='交易類型: regular=一般股票(0.3%%稅), day_trade=當沖(0.15%%稅)')
    parser.add_argument('--stop-loss', type=float, default=5.0,
                        help='停損 %% (0=不啟用，預設 5)')
    parser.add_argument('--take-profit', type=float, default=10.0,
                        help='停利 %% (0=不啟用，預設 10)')
    parser.add_argument('--output-dir', type=str, default='output',
                        help='HTML 輸出資料夾（預設 output/）')
    args = parser.parse_args()

    symbol = args.symbol.upper().strip()
    print(f'[1/4] Fetching {symbol} 30m & 60m ...')
    r30 = fetch_stock_data(symbol, '30m')
    r60 = fetch_stock_data(symbol, '60m')
    if r30.error_code and r60.error_code:
        print(f'  [FAIL] {r30.error_msg}')
        return 1
    df_30 = r30.df
    df_60 = r60.df

    df_bt = df_60 if args.interval == '60m' else df_30
    if df_bt.empty:
        print(f'  [FAIL] 沒有 {args.interval} 資料可回測')
        return 1

    tax_rate = TAX_RATE_DAY_TRADE if args.trade_type == 'day_trade' else TAX_RATE_REGULAR
    print(f'[2/4] Running 6 strategies on {args.interval} ({len(df_bt)} bars) ...')
    results = run_multi_strategy(
        df              = df_bt,
        strategy_funcs  = STRATEGIES,
        initial_capital = args.capital,
        commission_rate = args.commission_rate / 100.0,
        commission_min  = args.commission_min,
        tax_rate        = tax_rate,
        stop_loss_pct   = args.stop_loss,
        take_profit_pct = args.take_profit,
        interval        = args.interval,
    )

    meta = {
        'symbol':          symbol,
        'interval':        args.interval,
        'capital':         args.capital,
        'commission_rate': args.commission_rate,
        'commission_min':  args.commission_min,
        'trade_type':      args.trade_type,
        'tax_rate':        tax_rate * 100,
        'stop_loss_pct':   args.stop_loss,
        'take_profit_pct': args.take_profit,
        'df':              df_bt,
    }

    print('[3/4] Building HTML ...')
    html = build_html_report(symbol, df_30, df_60, results, meta)

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.replace('.', '_')
    today = datetime.now().strftime('%Y%m%d')
    out_path = Path(args.output_dir) / f'{safe_symbol}_report_{today}.html'
    out_path.write_text(html, encoding='utf-8')

    size_kb = out_path.stat().st_size / 1024
    print(f'[4/4] [OK] {out_path}  ({size_kb:.0f} KB)')
    print(f'       Double-click to open, or upload anywhere.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
