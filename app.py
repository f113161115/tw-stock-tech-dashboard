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
from datetime import timedelta, datetime
from io import BytesIO
from typing import Optional

from scraper import (
    fetch_stock_data, save_data, export_to_excel, fetch_stock_name,
    ERR_NETWORK, ERR_RATE_LIMIT, ERR_INVALID, ERR_PARTIAL, ERR_OTHER,
)
from strategies import STRATEGIES
from backtest import (
    run_multi_strategy, kpi_table, BacktestResult,
    DEFAULT_INITIAL_CAPITAL, DEFAULT_COMMISSION_RATE, DEFAULT_COMMISSION_MIN,
    TAX_RATE_REGULAR, TAX_RATE_DAY_TRADE,
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


# ============ 資料範圍提示區（用今天日期當基準舉例） ============
def render_data_range_banner():
    """主畫面上方顯眼說明：目前可回測範圍、今天日期、Yahoo 限制。"""
    today = datetime.now().date()
    df_30 = st.session_state.get('data_30m', pd.DataFrame())
    df_60 = st.session_state.get('data_60m', pd.DataFrame())

    if df_30.empty and df_60.empty:
        st.info(f'📅 今天是 **{today}**，請先在側邊欄抓取資料。')
        return

    info_30 = (
        f"{df_30['datetime'].min().date()} ~ {df_30['datetime'].max().date()}　"
        f"(共 {(df_30['datetime'].max().date() - df_30['datetime'].min().date()).days} 天，"
        f"{len(df_30):,} 筆)"
        if not df_30.empty else '— 尚未抓取 —'
    )
    info_60 = (
        f"{df_60['datetime'].min().date()} ~ {df_60['datetime'].max().date()}　"
        f"(共 {(df_60['datetime'].max().date() - df_60['datetime'].min().date()).days} 天，"
        f"{len(df_60):,} 筆)"
        if not df_60.empty else '— 尚未抓取 —'
    )

    # 用今天日期推算「Yahoo 規則允許的最大可回溯」
    max_30_start = today - timedelta(days=60)
    max_60_start = today - timedelta(days=730)

    st.info(
        f"📅 **今天**：{today}　·　"
        f"請在 **側邊欄 ➡** 設定要回測的日期範圍（已自動帶入最大可選範圍、必填）\n\n"
        f"**目前資料可回測範圍（Yahoo 限制）：**\n"
        f"- ⏱ **30 分鐘 K**：{info_30}　│ 上限 60 天，最早 {max_30_start}\n"
        f"- 📈 **60 分鐘 K**：{info_60}　│ 上限 730 天（~2 年），最早 {max_60_start}\n\n"
        f"💡 想回測「今年到現在」就把起始日改 {today.replace(month=1, day=1)}；"
        f"想回測「過去 1 個月」就改 {today - timedelta(days=30)}。"
    )


# render_data_range_banner() 在「取得 df_30/df_60」之後才呼叫（見下方）


# ============ 台股代碼 → 公司名 對照表（給 UI 顯示用） ============
STOCK_NAMES = {
    '0050.TW': '元大台灣50',     '0056.TW': '元大高股息',
    '00878.TW': '國泰永續高股息', '00919.TW': '群益台灣精選高息',
    '1101.TW': '台泥',           '1102.TW': '亞泥',
    '1216.TW': '統一',           '1301.TW': '台塑',
    '1303.TW': '南亞',           '1326.TW': '台化',
    '1402.TW': '遠東新',         '1718.TW': '中纖',
    '1802.TW': '台玻',           '2002.TW': '中鋼',
    '2105.TW': '正新',           '2207.TW': '和泰車',
    '2303.TW': '聯電',           '2317.TW': '鴻海',
    '2330.TW': '台積電',         '2382.TW': '廣達',
    '2412.TW': '中華電',         '2454.TW': '聯發科',
    '2603.TW': '長榮',           '2609.TW': '陽明',
    '2615.TW': '萬海',           '2880.TW': '華南金',
    '2881.TW': '富邦金',         '2882.TW': '國泰金',
    '2884.TW': '玉山金',         '2886.TW': '兆豐金',
    '2891.TW': '中信金',         '2892.TW': '第一金',
    '3008.TW': '大立光',         '3034.TW': '聯詠',
    '3231.TW': '緯創',           '3711.TW': '日月光投控',
    '4904.TW': '遠傳',           '5871.TW': '中租-KY',
    '6505.TW': '台塑化',         '6669.TW': '緯穎',
}

@st.cache_data(show_spinner=False)
def get_stock_name(symbol: str) -> str:
    """中文 hardcode 優先、找不到 fallback 到 Yahoo Finance（英文 longName）。"""
    sym = symbol.upper().strip()
    if sym in STOCK_NAMES:
        return STOCK_NAMES[sym]      # 例：「台玻」（中文）
    return fetch_stock_name(sym)     # 例：「Taiwan Glass Industry Corporation」（英文）


def get_stock_display(symbol: str) -> str:
    """回傳「1802.TW 台玻」這種顯示文字；找不到就只顯示代碼。"""
    name = get_stock_name(symbol)
    return f'{symbol} {name}' if name else symbol


# ============ Session State 初始化 ============
if 'data_30m' not in st.session_state:
    st.session_state.data_30m = pd.DataFrame()
if 'data_60m' not in st.session_state:
    st.session_state.data_60m = pd.DataFrame()
if 'symbol' not in st.session_state:
    st.session_state.symbol = '1802.TW'
if 'loaded' not in st.session_state:
    st.session_state.loaded = False
if 'bt_results' not in st.session_state:
    st.session_state.bt_results = []          # List[BacktestResult]
if 'bt_meta' not in st.session_state:
    st.session_state.bt_meta = {}             # 跑回測時用的設定（給檔名等）


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
    # ---- 第 1 區：股票代碼輸入（最上方） ----
    st.markdown('### 🔍 股票代碼 *（必填）')
    sb_new_symbol = st.text_input(
        '輸入代碼（台股加 .TW）',
        value=st.session_state.get('symbol', '1802.TW'),
        help='例如 1802.TW、2330.TW、0050.TW',
        key='sb_symbol_input',
    )
    if st.button('🔄 抓取此代碼', use_container_width=True, type='primary',
                 key='sb_refresh_btn'):
        if load_stock(sb_new_symbol):
            st.rerun()

    st.markdown('---')
    # ---- 第 2 區：快速挑 ----
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
            抓到的資料會自動存到 `data/` 資料夾（CSV）
            與 `output/` 資料夾（Excel），
            供回測與報告使用。
            """
        )

    st.markdown('---')
    st.markdown('### 📊 策略回測')

    bt_interval = st.radio(
        '回測週期',
        options=['60m', '30m'],
        horizontal=True,
        help='60m 資料較長（~2 年）；30m 較細但只 60 天',
        key='bt_interval',
    )

    # 根據週期動態給日期範圍
    _df_for_range = st.session_state.data_60m if bt_interval == '60m' else st.session_state.data_30m
    if not _df_for_range.empty:
        _avail_min = _df_for_range['datetime'].min().date()
        _avail_max = _df_for_range['datetime'].max().date()

        # 顯眼提示「可選範圍 + 預設帶入最大」
        st.caption(
            f'📌 **可選範圍**：{_avail_min} ~ {_avail_max}　'
            f'(共 {(_avail_max - _avail_min).days} 天)　·　已預設帶入最大區間'
        )

        col_bs, col_be = st.columns(2)
        with col_bs:
            bt_start_date = st.date_input(
                '回測起始日 *（必填）',
                value=_avail_min,
                min_value=_avail_min,
                max_value=_avail_max,
                key='bt_start_date',
                help=f'可選範圍：{_avail_min} ~ {_avail_max}',
            )
        with col_be:
            bt_end_date = st.date_input(
                '回測結束日 *（必填）',
                value=_avail_max,
                min_value=_avail_min,
                max_value=_avail_max,
                key='bt_end_date',
                help=f'可選範圍：{_avail_min} ~ {_avail_max}',
            )

        # 雙保險：超出範圍/邏輯錯誤的警告
        if bt_start_date < _avail_min or bt_end_date > _avail_max:
            st.error(
                f'⚠ 你選的日期超出可用範圍！\n\n'
                f'可選：{_avail_min} ~ {_avail_max}'
            )
        elif bt_start_date > bt_end_date:
            st.error(f'⚠ 起始日（{bt_start_date}）不可晚於結束日（{bt_end_date}）')
        else:
            st.caption(
                f'⏱ **目前回測期間**：{bt_start_date} ~ {bt_end_date}　'
                f'(共 **{(bt_end_date - bt_start_date).days}** 天)'
            )
    else:
        bt_start_date = None
        bt_end_date = None
        st.warning(f'⚠ 尚未抓取 {bt_interval} 資料，無法設定回測期間。請先在側邊欄上方挑一檔股票。')

    selected_strategy_names = st.multiselect(
        '策略 *（必填，可多選比較）',
        options=list(STRATEGIES.keys()),
        default=['① 均線突破 (MA20)', '② RSI + 趨勢濾網 (MA60)'],
        help='至少選 1 個策略才能執行回測',
        key='bt_strategies',
    )
    if not selected_strategy_names:
        st.warning('⚠ 請至少選擇 1 個策略')

    col_sl, col_tp = st.columns(2)
    with col_sl:
        bt_stop_loss = st.number_input(
            '停損 %',
            min_value=0.0, max_value=50.0, value=5.0, step=0.5,
            help='0 = 不啟用。例如 5 代表虧損 5% 強制平倉',
            key='bt_sl',
        )
    with col_tp:
        bt_take_profit = st.number_input(
            '停利 %',
            min_value=0.0, max_value=200.0, value=10.0, step=1.0,
            help='0 = 不啟用。例如 10 代表獲利 10% 落袋',
            key='bt_tp',
        )

    bt_capital = st.number_input(
        '初始資金 (NT$)',
        min_value=10000, max_value=100_000_000, value=DEFAULT_INITIAL_CAPITAL,
        step=100000, format='%d',
        key='bt_capital',
    )

    st.markdown('**💰 交易成本（台股實際規則）**')

    with st.expander('📖 常見券商手續費（自行抄到下方）', expanded=False):
        st.markdown(
            """
            > 📅 **資料時效：2026 年底**　·　實際以各券商最新公告為準

            | 券商 / 方案 | 折扣 | 費率 |
            |---|---|---|
            | 法定原價 | ─ | **0.1425%** |
            | 元大 / 一般電子單 | 6 折 | **0.0855%** |
            | 多家券商 VIP | 5 折 | **0.0713%** |
            | 多家券商熟客 | 4 折 | **0.0570%** |
            | **國泰證券 電子單** ⭐ | **2.8 折** | **0.0399%** |
            | **永豐證券 電子單** ⭐ | **2 折** | **0.0285%** |
            | 部分券商最低 | 1.68 折 | **0.0239%** |

            > 計算方式：`法定 0.1425% × 折扣` ；下限多為 NT\\$ 20
            > 把對應費率抄到下方欄位即可。
            """
        )

    col_cr, col_cm = st.columns(2)
    with col_cr:
        bt_comm_rate = st.number_input(
            '手續費率 (%) ─ 自行填寫',
            min_value=0.0, max_value=1.0,
            value=DEFAULT_COMMISSION_RATE * 100, step=0.0025, format='%.4f',
            help='券商手續費率（買進+賣出皆收）。預設 0.1425% = 法定原價；國泰 2.8 折請填 0.0399',
            key='bt_comm_rate',
        )
    with col_cm:
        bt_comm_min = st.number_input(
            '手續費下限 (元)',
            min_value=1, max_value=200, value=int(DEFAULT_COMMISSION_MIN), step=1,
            help='單筆手續費若不足下限，以下限收取。台股各券商多為 NT$20',
            key='bt_comm_min',
        )
    bt_trade_type = st.radio(
        '交易類型（影響證交稅）',
        options=['一般股票 (0.3%)', '現股當沖 (0.15%)'],
        index=0, horizontal=True,
        help='你的策略（趨勢/反轉持倉數天到數週）屬於「一般股票」。當沖必須同日買賣',
        key='bt_trade_type',
    )
    bt_tax_rate = TAX_RATE_DAY_TRADE if '當沖' in bt_trade_type else TAX_RATE_REGULAR

    run_backtest_btn = st.button(
        '▶ 執行回測',
        use_container_width=True,
        type='primary',
        disabled=(len(selected_strategy_names) == 0),
        key='bt_run',
    )


# ============ 首次進入自動抓 1802.TW ============
if not st.session_state.loaded:
    load_stock('1802.TW')


# ============ 取得目前資料 ============
df_30 = st.session_state.data_30m
df_60 = st.session_state.data_60m
symbol = st.session_state.symbol


# ============ 主畫面最上方：目前選擇 + 股票代碼輸入 + Step 引導 ============
def render_top_bar():
    """主畫面最上方：股票代碼輸入 + 目前選擇 + Step 進度。"""
    # 「目前選擇」橫條 — 中文優先、自動回退到 Yahoo Finance 抓的英文名
    name_only = get_stock_name(symbol)
    if name_only:
        st.markdown(
            f'<div style="background:#1660AB;color:#F9F2E0;padding:14px 22px;'
            f'border-radius:10px;margin-bottom:14px;font-size:1.05rem;'
            f'letter-spacing:1px;box-shadow:0 2px 10px rgba(22,96,171,0.2);">'
            f'📊 <b>目前選擇：</b><span style="font-size:1.25rem;letter-spacing:2px;">'
            f'{symbol}</span>　·　<b>{name_only}</b></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="background:#1660AB;color:#F9F2E0;padding:14px 22px;'
            f'border-radius:10px;margin-bottom:14px;font-size:1.05rem;'
            f'letter-spacing:1px;box-shadow:0 2px 10px rgba(22,96,171,0.2);">'
            f'📊 <b>目前選擇：</b><span style="font-size:1.25rem;letter-spacing:2px;">'
            f'{symbol}</span>　<i style="opacity:0.7;font-size:0.9rem;">'
            f'（Yahoo Finance 也查不到此代碼的公司名）</i></div>',
            unsafe_allow_html=True,
        )

    # 股票代碼輸入欄（主畫面版）
    col_in, col_btn = st.columns([4, 1])
    with col_in:
        new_sym_top = st.text_input(
            '🔄 換一檔股票（台股請加 .TW）*（必填）',
            value=symbol,
            help='例：1802.TW 台玻、2330.TW 台積電、0050.TW 元大台灣50',
            key='top_symbol_input',
        )
    with col_btn:
        st.write('')
        st.write('')
        refresh_top = st.button('🔄 重新抓取', use_container_width=True, type='primary',
                                key='top_refresh_btn')
    if refresh_top:
        if load_stock(new_sym_top):
            st.success(f'✓ 已切換到 {get_stock_display(new_sym_top)}')
            st.rerun()

    # Step 進度引導
    has_data = not (df_30.empty and df_60.empty)
    has_results = bool(st.session_state.bt_results)
    s1 = '✅' if has_data else '⬜'
    s2 = '✅' if has_results else ('▶' if has_data else '⬜')
    s3 = '✅' if has_results else '⬜'
    st.caption(
        f'**操作流程**：&nbsp;&nbsp;'
        f'{s1} **Step 1** 選股票（最上面 / 側邊欄）&nbsp;&nbsp;→&nbsp;&nbsp;'
        f'{s2} **Step 2** 側邊欄設定回測（期間/策略/停損/手續費）→ 按「執行回測」&nbsp;&nbsp;→&nbsp;&nbsp;'
        f'{s3} **Step 3** 看結果（可點左上 « 收起側邊欄看大圖）'
    )


render_top_bar()


# ============ 在主畫面顯示資料範圍提示 ============
render_data_range_banner()


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
    m4.metric('最後更新', last_time.strftime('%Y/%m/%d %H:%M'))
    st.caption(f'📌 對照基準：30 分鐘 K 棒最末兩筆（{symbol}）')


render_price_metric(df_30)


# ============ 看盤區：上 K 線、下 OHLC 表（垂直堆疊） ============

# ---- 上方：K 線圖（30m，看盤主圖） ----
st.subheader('🕯️ K 線圖（30 分鐘）')
if df_30.empty:
    st.warning('沒有 30 分鐘資料可顯示')
else:
    _min30, _max30 = df_30['datetime'].min().date(), df_30['datetime'].max().date()
    _def30 = max(_min30, _max30 - timedelta(days=50))
    candle_start = st.date_input(
        '挑選起始日期（往後顯示 50 天）',
        value=_def30, min_value=_min30, max_value=_max30,
        key='candle_start_date',
    )
    df_candle = filter_50_days(df_30, candle_start)
    if df_candle.empty:
        st.info('此區間沒有資料')
    else:
        fig_k = make_candle_chart(
            df_candle,
            f'{symbol} K 線（{candle_start} ~ {candle_start + timedelta(days=50)}）',
        )
        st.plotly_chart(fig_k, use_container_width=True)
        st.caption(f'共 {len(df_candle)} 筆 K 棒')

# ---- 下方：OHLC 表格（30m，含成交量），用 expander 包起來省空間 ----
with st.expander('📋 OHLC 資料表（30 分鐘，點擊展開／收合）', expanded=False):
    if df_30.empty:
        st.warning('沒有 30 分鐘資料可顯示')
    else:
        df_ohlc = filter_50_days(df_30, candle_start)
        if df_ohlc.empty:
            st.info('此區間沒有資料')
        else:
            tbl = pd.DataFrame({
                '日期':   df_ohlc['datetime'].dt.date,
                '時間':   df_ohlc['datetime'].dt.strftime('%H:%M'),
                '開盤價': df_ohlc['open'].round(2),
                '最高價': df_ohlc['high'].round(2),
                '最低價': df_ohlc['low'].round(2),
                '收盤價': df_ohlc['close'].round(2),
                '成交量': df_ohlc['volume'].astype('int64'),
            }).iloc[::-1].reset_index(drop=True)  # 倒序：最新在上
            st.dataframe(tbl, use_container_width=True, height=400, hide_index=True)
            st.caption(f'共 {len(tbl)} 筆 K 棒（最新在最上方）')

        # 下載 30m CSV
        st.download_button(
            '⬇ 下載 30 分鐘資料（CSV，完整 ~60 天）',
            df_30.to_csv(index=False).encode('utf-8-sig'),
            file_name=f'{symbol.replace(".", "_")}_30m.csv',
            mime='text/csv',
            use_container_width=True,
            key='dl_30m_main',
        )

# ---- 60m 資料下載（保留，給回測用） ----
if not df_60.empty:
    with st.expander('📈 60 分鐘資料下載（給回測用）', expanded=False):
        st.caption(f'共 {len(df_60):,} 筆 K 棒，範圍 {df_60["datetime"].min().date()} ~ {df_60["datetime"].max().date()}')
        st.download_button(
            '⬇ 下載 60 分鐘資料（CSV，完整 ~730 天）',
            df_60.to_csv(index=False).encode('utf-8-sig'),
            file_name=f'{symbol.replace(".", "_")}_60m.csv',
            mime='text/csv',
            use_container_width=True,
            key='dl_60m_main',
        )


# ============ 執行回測（按鈕在側邊欄） ============
if run_backtest_btn:
    df_full = df_60 if bt_interval == '60m' else df_30
    if df_full.empty:
        st.error(f'❌ 沒有 {bt_interval} 資料，無法回測')
    elif bt_start_date is None or bt_end_date is None:
        st.error('❌ 請先設定回測期間')
    elif bt_start_date > bt_end_date:
        st.error('❌ 回測起始日不可晚於結束日')
    else:
        # 用使用者選的日期切片
        mask = (df_full['datetime'].dt.date >= bt_start_date) & \
               (df_full['datetime'].dt.date <= bt_end_date)
        df_bt = df_full.loc[mask].reset_index(drop=True)

        if df_bt.empty:
            st.error(f'❌ 此期間沒有 {bt_interval} 資料')
        else:
            chosen = {n: STRATEGIES[n] for n in selected_strategy_names}
            with st.spinner(f'回測 {len(chosen)} 個策略中（{len(df_bt):,} 筆 K 棒）...'):
                bt_results = run_multi_strategy(
                    df              = df_bt,
                    strategy_funcs  = chosen,
                    initial_capital = float(bt_capital),
                    commission_rate = bt_comm_rate / 100.0,    # UI 是 %、引擎用比例
                    commission_min  = float(bt_comm_min),
                    tax_rate        = bt_tax_rate,
                    stop_loss_pct   = float(bt_stop_loss),
                    take_profit_pct = float(bt_take_profit),
                    interval        = bt_interval,
                )
            st.session_state.bt_results = bt_results
            st.session_state.bt_meta = {
                'symbol':           symbol,
                'interval':         bt_interval,
                'capital':          bt_capital,
                'commission_rate':  bt_comm_rate,             # %
                'commission_min':   bt_comm_min,              # NT$
                'trade_type':       bt_trade_type,
                'tax_rate':         bt_tax_rate * 100,        # %
                'stop_loss_pct':    bt_stop_loss,
                'take_profit_pct':  bt_take_profit,
                'bt_start_date':    bt_start_date.isoformat(),
                'bt_end_date':      bt_end_date.isoformat(),
                'bt_days':          (bt_end_date - bt_start_date).days,
                'bt_bars':          len(df_bt),
                'generated_at':     datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
                'df':               df_bt,
            }
            st.success(
                f'✓ 回測完成（{symbol} · {bt_interval} · '
                f'{bt_start_date}~{bt_end_date} · {(bt_end_date-bt_start_date).days} 天 · '
                f'{len(bt_results)} 策略）'
            )


# ============ 回測結果區（左：圖、右：KPI 表格） ============
def make_backtest_chart(df_bt: pd.DataFrame, results: list, meta: dict) -> go.Figure:
    """K 線圖 + 各策略買賣標記。中文化（雲端 PNG export 若無中文字體可能會亂碼，本機 Windows OK）。"""
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df_bt['datetime'],
        open=df_bt['open'], high=df_bt['high'],
        low=df_bt['low'], close=df_bt['close'],
        increasing_line_color='#C0392B', decreasing_line_color='#1660AB',
        increasing_fillcolor='#C0392B', decreasing_fillcolor='#1660AB',
        name='K 線價格',
        showlegend=True,
    ))

    palette = ['#E67E22', '#27AE60', '#8E44AD', '#16A085', '#D35400', '#2980B9', '#7F8C8D']
    for i, r in enumerate(results):
        color = palette[i % len(palette)]
        entry_x = [t.entry_time for t in r.trades]
        entry_y = [t.entry_price for t in r.trades]
        exit_x  = [t.exit_time for t in r.trades]
        exit_y  = [t.exit_price for t in r.trades]
        fig.add_trace(go.Scatter(
            x=entry_x, y=entry_y, mode='markers',
            marker=dict(symbol='triangle-up', size=10, color=color),
            name=f'{r.strategy_name} 買進',
            hovertemplate='進場 %{x}<br>價格 %{y:.2f}<extra></extra>',
        ))
        fig.add_trace(go.Scatter(
            x=exit_x, y=exit_y, mode='markers',
            marker=dict(symbol='triangle-down', size=10, color=color, line=dict(width=1, color='#000')),
            name=f'{r.strategy_name} 賣出',
            hovertemplate='出場 %{x}<br>價格 %{y:.2f}<extra></extra>',
        ))

    fig.update_layout(
        title=dict(
            text=f'{meta["symbol"]} 回測買賣訊號（{meta["interval"]}）　·　停損 {meta["stop_loss_pct"]}%　停利 {meta["take_profit_pct"]}%',
            font=dict(color='#1660AB', size=16),
        ),
        xaxis_title='時間',
        yaxis_title='股價（元）',
        plot_bgcolor='#FDFAF0',
        paper_bgcolor='#FFFFFF',
        height=500,
        margin=dict(l=40, r=20, t=60, b=40),
        xaxis_rangeslider_visible=False,
        font=dict(family='Microsoft JhengHei, PingFang TC, sans-serif', color='#2C3E50'),
        legend=dict(orientation='h', y=-0.15),
    )
    fig.update_xaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)', linecolor='#4A8BC9')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)', linecolor='#4A8BC9')
    return fig


def make_equity_chart(results: list) -> go.Figure:
    """各策略權益曲線疊圖。"""
    fig = go.Figure()
    palette = ['#E67E22', '#27AE60', '#8E44AD', '#16A085', '#D35400', '#2980B9', '#7F8C8D']
    for i, r in enumerate(results):
        if r.equity_curve.empty:
            continue
        fig.add_trace(go.Scatter(
            x=r.equity_curve.index, y=r.equity_curve.values,
            mode='lines', name=r.strategy_name,
            line=dict(width=2, color=palette[i % len(palette)]),
            hovertemplate='%{x}<br>權益 NT$ %{y:,.0f}<extra></extra>',
        ))
    fig.update_layout(
        title=dict(text='各策略權益曲線', font=dict(color='#1660AB', size=14)),
        xaxis_title='時間', yaxis_title='帳戶權益（元）',
        plot_bgcolor='#FDFAF0', paper_bgcolor='#FFFFFF',
        height=300, margin=dict(l=40, r=20, t=40, b=40),
        font=dict(family='Microsoft JhengHei, PingFang TC, sans-serif', color='#2C3E50'),
        legend=dict(orientation='h', y=-0.2),
    )
    fig.update_xaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    fig.update_yaxes(showgrid=True, gridcolor='rgba(22, 96, 171, 0.08)')
    return fig


def build_excel_bytes(results: list, meta: dict) -> bytes:
    """把 KPI + 各策略的交易明細 + 原始 OHLCV 包成一個 Excel 檔。"""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        # Sheet 1: KPI 摘要
        kpi_df = kpi_table(results)
        kpi_df.to_excel(writer, sheet_name='KPI_Summary')

        # Sheet 2: 設定
        meta_show = {k: v for k, v in meta.items() if k != 'df'}
        pd.DataFrame.from_dict(meta_show, orient='index', columns=['value']).to_excel(
            writer, sheet_name='Settings'
        )

        # Sheet 3+: 各策略交易明細
        for r in results:
            if not r.trades:
                continue
            trades_df = pd.DataFrame([{
                '進場時間': t.entry_time, '進場價': t.entry_price,
                '出場時間': t.exit_time, '出場價': t.exit_price,
                '股數': t.shares,
                '損益(NT$)': round(t.pnl, 2),
                '報酬%': round(t.return_pct, 2),
                '進場手續費': round(t.entry_commission, 2),
                '出場手續費': round(t.exit_commission, 2),
                '證交稅':     round(t.tax, 2),
                '總成本':     round(t.total_cost, 2),
                '出場原因': t.exit_reason,
            } for t in r.trades])
            # Excel 工作表名長度 ≤ 31 字
            sheet = ('TR_' + r.strategy_name)[:31]
            trades_df.to_excel(writer, sheet_name=sheet, index=False)

        # Sheet 末: 原始 OHLCV
        meta['df'].to_excel(writer, sheet_name='OHLCV', index=False)
    return buf.getvalue()


bt_results = st.session_state.bt_results
bt_meta = st.session_state.bt_meta

def find_best_strategy(results: list) -> Optional[dict]:
    """依夏普比率挑「最佳主動策略」，排除 Buy & Hold。"""
    candidates = []
    for r in results:
        if not r.kpi or 'Buy & Hold' in r.strategy_name:
            continue
        try:
            sharpe = float(r.kpi.get('夏普比率', '0'))
            roi    = float(str(r.kpi.get('ROI (報酬率)', '0')).replace('%', '').replace('+', '').strip())
            candidates.append((sharpe, roi, r))
        except (ValueError, TypeError):
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    sharpe, roi, best = candidates[0]
    return {
        'name':    best.strategy_name,
        'sharpe':  sharpe,
        'roi':     roi,
        'win_rate': best.kpi.get('勝率', '?'),
        'mdd':     best.kpi.get('最大回撤 (MDD)', '?'),
    }


def find_buy_and_hold(results: list) -> Optional[dict]:
    """從結果中挑出 Buy & Hold 當對照基準。"""
    for r in results:
        if 'Buy & Hold' in r.strategy_name and r.kpi:
            try:
                roi = float(str(r.kpi.get('ROI (報酬率)', '0')).replace('%', '').replace('+', '').strip())
            except (ValueError, TypeError):
                roi = 0.0
            return {'name': r.strategy_name, 'roi': roi}
    return None


if bt_results:
    st.markdown('---')
    st.subheader('📊 策略回測結果')

    # ⭐ 最佳策略推薦條 + Buy & Hold 對照
    best = find_best_strategy(bt_results)
    bh = find_buy_and_hold(bt_results)
    if best:
        beat_bh_msg = ''
        if bh:
            diff = best['roi'] - bh['roi']
            if diff > 0:
                beat_bh_msg = (
                    f'　·　🎯 **勝過 Buy & Hold** {diff:+.2f}%'
                    f'（基準 {bh["roi"]:+.2f}%）'
                )
            else:
                beat_bh_msg = (
                    f'　·　⚠ **不如 Buy & Hold**（{diff:+.2f}%，基準 {bh["roi"]:+.2f}%）'
                )
        st.success(
            f'⭐ **推薦策略**：**{best["name"]}**　·　'
            f'夏普 **{best["sharpe"]:.2f}**　·　'
            f'ROI **{best["roi"]:+.2f}%**　·　'
            f'勝率 **{best["win_rate"]}**　·　'
            f'MDD **{best["mdd"]}**'
            f'{beat_bh_msg}'
        )

    bt_left, bt_right = st.columns([3, 2])

    # ---- 左：K 線 + 買賣訊號 + 權益曲線 ----
    with bt_left:
        chart_fig = make_backtest_chart(bt_meta['df'], bt_results, bt_meta)
        st.plotly_chart(chart_fig, use_container_width=True)

        equity_fig = make_equity_chart(bt_results)
        st.plotly_chart(equity_fig, use_container_width=True)

        # PNG 下載（K 線圖）
        try:
            png_bytes = chart_fig.to_image(format='png', width=1400, height=700, scale=2)
            st.download_button(
                '⬇ 下載 K 線回測圖 (PNG)',
                png_bytes,
                file_name=f'{bt_meta["symbol"].replace(".", "_")}_backtest_{bt_meta["interval"]}.png',
                mime='image/png',
                use_container_width=True,
                key='dl_bt_png',
            )
        except Exception as e:
            st.info(f'PNG 匯出需要 kaleido 套件（若未安裝請在 requirements.txt 加 kaleido）。錯誤：{e}')

    # ---- 右下角：KPI 表格 + Excel 下載 ----
    with bt_right:
        st.markdown('#### 📋 KPI 績效表')
        kpi_df = kpi_table(bt_results)
        st.dataframe(kpi_df, use_container_width=True, height=520)

        # Excel 下載
        try:
            xlsx_bytes = build_excel_bytes(bt_results, bt_meta)
            st.download_button(
                '⬇ 下載完整回測報告 (Excel)',
                xlsx_bytes,
                file_name=f'{bt_meta["symbol"].replace(".", "_")}_backtest_{bt_meta["interval"]}.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True,
                key='dl_bt_xlsx',
            )
        except Exception as e:
            st.error(f'Excel 匯出失敗（需 openpyxl）：{e}')

        st.caption(
            f'📊 **資料**：{bt_meta["symbol"]} · {bt_meta["interval"]} · '
            f'{bt_meta.get("bt_bars", "?")} 筆 K 棒\n\n'
            f'⏱ **回測期間**：{bt_meta.get("bt_start_date", "?")} ~ {bt_meta.get("bt_end_date", "?")} '
            f'（共 {bt_meta.get("bt_days", "?")} 天）\n\n'
            f'💰 **資金**：NT$ {bt_meta["capital"]:,.0f}\n\n'
            f'💸 **手續費**：{bt_meta.get("commission_rate", "?")}% '
            f'（不足 NT$ {bt_meta.get("commission_min", "?")} 進位）\n\n'
            f'🏛 **證交稅**：{bt_meta.get("tax_rate", "?")}%（{bt_meta.get("trade_type", "?")}）\n\n'
            f'🛡 **停損**：{bt_meta["stop_loss_pct"]}%　·　🎯 **停利**：{bt_meta["take_profit_pct"]}%\n\n'
            f'🕐 **報告生成**：{bt_meta.get("generated_at", "?")}'
        )


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
