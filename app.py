"""
台股技術分析儀表板（Streamlit Web App）
=========================================
- 左上角：股價折線圖（可挑選起始日期，往後顯示 50 天）
- 右上角：K 線圖（可挑選起始日期，往後顯示 50 天）
- 下方：股票代碼輸入欄位（預設 1802.TW 台玻，可改其他代碼）

執行方式：
    streamlit run app.py

作者：李孟盈
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import timedelta

from scraper import (
    fetch_stock_data, save_data,
    ERR_NETWORK, ERR_RATE_LIMIT, ERR_INVALID, ERR_PARTIAL, ERR_OTHER,
)


# ============ 頁面基本設定 ============
st.set_page_config(
    page_title='台股技術分析儀表板',
    page_icon='📊',
    layout='wide'
)

st.markdown(
    """
    <style>
    /* === 宣紙白 + 鸢尾蓝 配色 === */
    .stApp {
        background-color: #F9F2E0;
    }
    .main .block-container {
        padding-top: 2rem;
        max-width: 1400px;
    }
    h1 {
        color: #1660AB !important;
        letter-spacing: 3px;
        font-weight: 700;
        border-bottom: 3px solid #1660AB;
        padding-bottom: 12px;
    }
    h2, h3 {
        color: #0F4A85 !important;
        letter-spacing: 1px;
    }
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #7A8899 !important;
    }
    /* 輸入框 */
    .stTextInput input, .stDateInput input {
        border: 1.5px solid #4A8BC9 !important;
        border-radius: 8px !important;
        background-color: #FFFFFF !important;
        color: #2C3E50 !important;
    }
    .stTextInput input:focus, .stDateInput input:focus {
        border-color: #1660AB !important;
        box-shadow: 0 0 0 3px rgba(22, 96, 171, 0.15) !important;
    }
    /* 主要按鈕 */
    .stButton > button {
        background-color: #1660AB !important;
        color: #F9F2E0 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        letter-spacing: 2px !important;
        transition: all 0.25s ease !important;
    }
    .stButton > button:hover {
        background-color: #0F4A85 !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(22, 96, 171, 0.3) !important;
    }
    /* 下載按鈕 */
    .stDownloadButton > button {
        background-color: #FFFFFF !important;
        color: #1660AB !important;
        border: 1.5px solid #1660AB !important;
        border-radius: 8px !important;
    }
    .stDownloadButton > button:hover {
        background-color: #1660AB !important;
        color: #F9F2E0 !important;
    }
    /* expander 與 alert */
    .streamlit-expanderHeader {
        background-color: #FFFFFF !important;
        color: #1660AB !important;
        border-radius: 8px !important;
    }
    /* 圖表外框 */
    [data-testid="stPlotlyChart"] {
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 8px;
        box-shadow: 0 2px 12px rgba(22, 96, 171, 0.08);
    }
    /* 一般文字 */
    .stMarkdown, p, label {
        color: #2C3E50 !important;
    }
    /* 分隔線 */
    hr {
        border-color: #1660AB !important;
        opacity: 0.3 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title('📊 台股技術分析儀表板')
st.caption('資料來源：Yahoo Finance（透過 yfinance API）  ·  支援 30 分鐘 / 60 分鐘 K 棒')


# ============ Session State 初始化 ============
if 'data_30m' not in st.session_state:
    st.session_state.data_30m = pd.DataFrame()
if 'data_60m' not in st.session_state:
    st.session_state.data_60m = pd.DataFrame()
if 'symbol' not in st.session_state:
    st.session_state.symbol = '1802.TW'
if 'loaded' not in st.session_state:
    st.session_state.loaded = False


# ============ 抓資料的函式 ============

# 各錯誤類別在 UI 上要怎麼呈現
_ERROR_DISPLAY = {
    ERR_INVALID:    ('error',   '❌ 找不到這檔股票'),
    ERR_NETWORK:    ('error',   '🌐 網路連線異常'),
    ERR_RATE_LIMIT: ('warning', '⏳ Yahoo 限流中'),
    ERR_PARTIAL:    ('warning', '⚠ 資料不完整'),
    ERR_OTHER:      ('error',   '⚠ 發生其他錯誤'),
}


def _show_fetch_error(symbol: str, interval: str, code: str, msg: str) -> None:
    """依錯誤類別把訊息顯示到 UI。"""
    level, headline = _ERROR_DISPLAY.get(code, ('error', '⚠ 未知錯誤'))
    text = f'**{headline}**（{symbol} · {interval}）\n\n{msg}'
    if level == 'warning':
        st.warning(text)
    else:
        st.error(text)


def load_stock(symbol: str) -> bool:
    """抓取指定股票的 30m 和 60m 資料，存到 session state。"""
    symbol = symbol.strip().upper()
    if not symbol:
        st.error('⚠ 請輸入股票代碼')
        return False

    # 兩條 progress bar：30m / 60m 各一條（每條：未開始 → 抓取中 → 完成）
    progress_box = st.container()
    with progress_box:
        st.caption(f'正在抓取 {symbol} ...')
        bar_30 = st.progress(0, text='30 分鐘 K 棒：等待中')
        bar_60 = st.progress(0, text='60 分鐘 K 棒：等待中')

    bar_30.progress(40, text='30 分鐘 K 棒：連線 Yahoo Finance...')
    result_30 = fetch_stock_data(symbol, '30m')
    if result_30.error_code:
        bar_30.progress(100, text=f'30 分鐘 K 棒：✗ {result_30.error_code}')
    else:
        bar_30.progress(100, text=f'30 分鐘 K 棒：✓ 完成（{len(result_30.df):,} 筆）')

    bar_60.progress(40, text='60 分鐘 K 棒：連線 Yahoo Finance...')
    result_60 = fetch_stock_data(symbol, '60m')
    if result_60.error_code:
        bar_60.progress(100, text=f'60 分鐘 K 棒：✗ {result_60.error_code}')
    else:
        bar_60.progress(100, text=f'60 分鐘 K 棒：✓ 完成（{len(result_60.df):,} 筆）')

    df_30, df_60 = result_30.df, result_60.df

    # 兩種週期都失敗才視為整體失敗（單一週期失敗可降級顯示另一種）
    if df_30.empty and df_60.empty:
        # 優先顯示「無效代碼」這類比較明確的錯誤
        for r, label in [(result_30, '30m'), (result_60, '60m')]:
            if r.error_code:
                _show_fetch_error(symbol, label, r.error_code, r.error_msg)
                break
        return False

    # 部分週期失敗：以 warning 提示，但不中斷流程
    if result_30.error_code:
        _show_fetch_error(symbol, '30m', result_30.error_code, result_30.error_msg)
    if result_60.error_code:
        _show_fetch_error(symbol, '60m', result_60.error_code, result_60.error_msg)

    st.session_state.data_30m = df_30
    st.session_state.data_60m = df_60
    st.session_state.symbol = symbol
    st.session_state.loaded = True

    # 自動存檔（給未來 ML / 回測使用）
    if not df_30.empty:
        save_data(df_30, symbol, '30m')
    if not df_60.empty:
        save_data(df_60, symbol, '60m')

    return True


# ============ 側邊欄：快速挑 + 資料來源說明 ============
QUICK_PICKS = [
    ('1802.TW', '台玻'),
    ('2330.TW', '台積電'),
    ('2317.TW', '鴻海'),
    ('2454.TW', '聯發科'),
    ('2412.TW', '中華電'),
    ('2882.TW', '國泰金'),
]

with st.sidebar:
    st.markdown('### 🚀 快速挑')
    st.caption('點一下即抓取')
    for code, name in QUICK_PICKS:
        if st.button(f'{code}　{name}', key=f'pick_{code}', use_container_width=True):
            if load_stock(code):
                st.rerun()

    st.markdown('---')
    with st.expander('📖 資料來源 & Yahoo 限制'):
        st.markdown(
            """
            **資料來源**：Yahoo Finance（透過 `yfinance` 套件）

            **Yahoo 對盤中（intraday）K 棒的歷史限制：**
            - 30 分鐘：最多回溯 **60 天**
            - 60 分鐘：最多回溯 **730 天**（約 2 年）
            - 1 日：可抓全歷史

            這是 Yahoo 平台規則，不是程式問題。
            抓到的資料會自動存到 `data/` 資料夾，
            未來給機器學習與回測使用。
            """
        )


# ============ 首次進入自動抓 1802.TW ============
if not st.session_state.loaded:
    load_stock('1802.TW')


# ============ 取得目前資料 ============
df_30 = st.session_state.data_30m
df_60 = st.session_state.data_60m
symbol = st.session_state.symbol


# ============ 圖表繪製函式 ============
def filter_50_days(df: pd.DataFrame, start_date) -> pd.DataFrame:
    """從 start_date 往後取 50 天的資料。"""
    if df.empty:
        return df
    end_date = start_date + timedelta(days=50)
    mask = (df['datetime'].dt.date >= start_date) & (df['datetime'].dt.date <= end_date)
    return df.loc[mask].reset_index(drop=True)


def make_line_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """建立收盤價折線圖（宣紙白 + 鸢尾蓝配色）。"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['datetime'],
        y=df['close'],
        mode='lines',
        name='收盤價',
        line=dict(color='#1660AB', width=2.5),
        fill='tozeroy',
        fillcolor='rgba(22, 96, 171, 0.08)',
        hovertemplate='時間：%{x}<br>收盤：%{y:.2f}<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(color='#1660AB', size=16)),
        xaxis_title='時間',
        yaxis_title='股價（元）',
        plot_bgcolor='#FDFAF0',          # 比宣紙白再亮一點
        paper_bgcolor='#FFFFFF',
        height=420,
        margin=dict(l=40, r=20, t=50, b=40),
        hovermode='x unified',
        font=dict(color='#2C3E50'),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor='rgba(22, 96, 171, 0.08)',
        linecolor='#4A8BC9',
        zeroline=False,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor='rgba(22, 96, 171, 0.08)',
        linecolor='#4A8BC9',
        zeroline=False,
        autorange=True,                  # 因為加了 fill='tozeroy' 要重新算範圍
    )
    # 修正：因為加了 fill 會把 0 也納入，所以重設 y 軸範圍只看資料區間
    y_min = df['close'].min()
    y_max = df['close'].max()
    y_pad = (y_max - y_min) * 0.1 if y_max > y_min else 1
    fig.update_yaxes(range=[y_min - y_pad, y_max + y_pad])
    return fig


def make_candle_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """建立 K 線圖（紅漲 鸢尾蓝跌，配合宣紙白主題）。"""
    fig = go.Figure(data=[go.Candlestick(
        x=df['datetime'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        increasing_line_color='#C0392B',     # 紅 K（台股慣例：紅 = 上漲）
        increasing_fillcolor='#C0392B',
        decreasing_line_color='#1660AB',     # 鸢尾蓝（跌）
        decreasing_fillcolor='#1660AB',
        line=dict(width=1),
        name='K 線'
    )])
    fig.update_layout(
        title=dict(text=title, font=dict(color='#1660AB', size=16)),
        xaxis_title='時間',
        yaxis_title='股價（元）',
        plot_bgcolor='#FDFAF0',
        paper_bgcolor='#FFFFFF',
        height=420,
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis_rangeslider_visible=False,
        font=dict(color='#2C3E50'),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor='rgba(22, 96, 171, 0.08)',
        linecolor='#4A8BC9',
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor='rgba(22, 96, 171, 0.08)',
        linecolor='#4A8BC9',
    )
    return fig


# ============ 現價與漲跌幅 metric（用 30m 最末兩筆比較） ============
def render_price_metric(df: pd.DataFrame) -> None:
    """顯示現價、漲跌、漲跌幅 % 三個 metric。資料不足兩筆時跳過。"""
    if df.empty or len(df) < 2:
        return
    last_close = float(df['close'].iloc[-1])
    prev_close = float(df['close'].iloc[-2])
    delta = last_close - prev_close
    pct = (delta / prev_close * 100) if prev_close else 0.0
    last_time = df['datetime'].iloc[-1]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric('現價', f'{last_close:.2f}')
    m2.metric('漲跌', f'{delta:+.2f}', delta=f'{delta:+.2f}')
    m3.metric('漲跌幅', f'{pct:+.2f}%', delta=f'{pct:+.2f}%')
    m4.metric('最後更新', last_time.strftime('%m/%d %H:%M'))
    st.caption(f'📌 對照基準：30 分鐘 K 棒最末兩筆（{symbol}）')


render_price_metric(df_30)


# ============ 上方兩張圖：左折線、右 K 線 ============
col_left, col_right = st.columns(2)

# ---- 左上：折線圖（用 60 分鐘資料，因為歷史較長） ----
with col_left:
    st.subheader('📈 股價折線圖（60 分鐘）')

    if df_60.empty:
        st.warning('沒有 60 分鐘資料可顯示')
    else:
        min_date = df_60['datetime'].min().date()
        max_date = df_60['datetime'].max().date()
        # 預設起始日：往前 50 天
        default_start = max(min_date, max_date - timedelta(days=50))

        line_start = st.date_input(
            '挑選起始日期（往後顯示 50 天）',
            value=default_start,
            min_value=min_date,
            max_value=max_date,
            key='line_start_date'
        )

        df_line = filter_50_days(df_60, line_start)
        if df_line.empty:
            st.info('此區間沒有資料')
        else:
            fig = make_line_chart(
                df_line,
                f'{symbol} 收盤價走勢（{line_start} ~ {line_start + timedelta(days=50)}）'
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f'共 {len(df_line)} 筆 K 棒')

        # 下載 60m CSV（完整資料，不只當前篩選範圍）
        st.download_button(
            '⬇ 下載 60 分鐘資料（CSV，完整 ~730 天）',
            df_60.to_csv(index=False).encode('utf-8-sig'),
            file_name=f'{symbol.replace(".", "_")}_60m.csv',
            mime='text/csv',
            use_container_width=True,
            key='dl_60m_main',
        )


# ---- 右上：K 線圖（用 30 分鐘資料，較細） ----
with col_right:
    st.subheader('🕯️ K 線圖（30 分鐘）')

    if df_30.empty:
        st.warning('沒有 30 分鐘資料可顯示')
    else:
        min_date = df_30['datetime'].min().date()
        max_date = df_30['datetime'].max().date()
        default_start = max(min_date, max_date - timedelta(days=50))

        candle_start = st.date_input(
            '挑選起始日期（往後顯示 50 天）',
            value=default_start,
            min_value=min_date,
            max_value=max_date,
            key='candle_start_date'
        )

        df_candle = filter_50_days(df_30, candle_start)
        if df_candle.empty:
            st.info('此區間沒有資料')
        else:
            fig = make_candle_chart(
                df_candle,
                f'{symbol} K 線（{candle_start} ~ {candle_start + timedelta(days=50)}）'
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f'共 {len(df_candle)} 筆 K 棒')

        # 下載 30m CSV（完整資料，不只當前篩選範圍）
        st.download_button(
            '⬇ 下載 30 分鐘資料（CSV，完整 ~60 天）',
            df_30.to_csv(index=False).encode('utf-8-sig'),
            file_name=f'{symbol.replace(".", "_")}_30m.csv',
            mime='text/csv',
            use_container_width=True,
            key='dl_30m_main',
        )


# ============ 下方：股票代碼輸入欄 ============
st.markdown('---')
st.subheader('🔍 股票代碼')

col_input, col_btn = st.columns([4, 1])
with col_input:
    new_symbol = st.text_input(
        '輸入股票代碼（台股請加 .TW，例如 1802.TW 台玻、2330.TW 台積電、2317.TW 鴻海）',
        value=symbol,
        key='symbol_input'
    )
with col_btn:
    st.write('')
    st.write('')
    refresh = st.button('🔄 重新抓取', use_container_width=True, type='primary')

if refresh:
    if load_stock(new_symbol):
        st.success(f'✓ 已更新為 {new_symbol.upper().strip()}')
        st.rerun()


# ============ 資料摘要 ============
with st.expander('📋 資料摘要（自動存檔到 data/ 資料夾，未來可給機器學習與回測使用）'):
    info_col1, info_col2 = st.columns(2)
    with info_col1:
        st.markdown('**30 分鐘資料**')
        if not df_30.empty:
            st.write(f'筆數：{len(df_30):,}')
            st.write(f'起：{df_30["datetime"].min()}')
            st.write(f'迄：{df_30["datetime"].max()}')
        else:
            st.write('無資料')

    with info_col2:
        st.markdown('**60 分鐘資料**')
        if not df_60.empty:
            st.write(f'筆數：{len(df_60):,}')
            st.write(f'起：{df_60["datetime"].min()}')
            st.write(f'迄：{df_60["datetime"].max()}')
        else:
            st.write('無資料')

st.markdown(
    '<div style="text-align:center;color:#7A8899;font-size:0.85rem;padding:20px 0;'
    'letter-spacing:1px;border-top:1px solid rgba(22, 96, 171, 0.15);margin-top:20px;">'
    '© 114 年度日碩 · 程式交易實作 · 4/27 下午作業</div>',
    unsafe_allow_html=True
)
