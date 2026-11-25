import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="Opportunity Hunter | صائد الفرص", page_icon="🎯", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; max-width: 1400px;}
.metric-card {background: #111827; padding: 14px 16px; border-radius: 12px; border: 1px solid #273449;}
.small-note {color: #9ca3af; font-size: 0.85rem;}
</style>
""", unsafe_allow_html=True)

st.title("🎯 Opportunity Hunter | صائد الفرص")
st.caption("ماسح أولي لاكتشاف الشركات الأمريكية القوية بعد هبوط أسعارها — أداة بحث وليست توصية شراء.")

DEFAULT_TICKERS = """NVDA,MSFT,GOOGL,AMZN,META,AVGO,AMD,ORCL,CRM,ADBE,
NFLX,COST,LLY,JPM,V,MA,BRK-B,UNH,HD,ABBV,
PANW,CRWD,PLTR,SHOP,UBER,ABNB,TSLA,INTC,QCOM,TXN,
MU,AMAT,LRCX,KLAC,AMGN,ISRG,GE,CAT,KO,PEP,
WMT,TGT,LOW,DIS,CSCO,IBM,ACN, NOW, SNPS, CDNS""".replace(" ", "")

with st.sidebar:
    st.header("إعدادات الفحص")
    tickers_text = st.text_area("رموز الأسهم الأمريكية (Ticker)", DEFAULT_TICKERS, height=220,
                                help="ابدأ بالقائمة المبدئية، ويمكنك إضافة أو حذف رموز مفصولة بفواصل.")
    max_results = st.slider("عدد أفضل الفرص المعروضة", 3, 20, 5)
    min_drop = st.slider("أقل هبوط من قمة 52 أسبوعًا (%)", 5, 70, 20)
    include_sharia = st.toggle("تفعيل فلتر الشريعة", value=False)
    st.caption("فلتر الشريعة غير مفعّل تلقائيًا. يحتاج مزود بيانات متخصصًا ومراجعة مستقلة.")
    run = st.button("🔎 افحص الأسهم الآن", type="primary", use_container_width=True)

st.info("**مصادر البيانات في النسخة الأولى:** Yahoo Finance عبر مكتبة yfinance. قد تتأخر البيانات أو تنقص بعض القوائم المالية. التغطية تعتمد على الرموز المدخلة وليست مسحًا شاملًا لكل الأسهم الأمريكية.")

def safe_num(x):
    try:
        if pd.isna(x): return None
        return float(x)
    except Exception:
        return None

def find_row(df, names):
    if df is None or df.empty: return None
    for n in names:
        for idx in df.index:
            if str(idx).strip().lower() == n.lower():
                vals = pd.to_numeric(df.loc[idx], errors="coerce").dropna()
                if len(vals): return vals.sort_index(ascending=False)
    return None

def score_stock(ticker, min_drop_pct):
    t = yf.Ticker(ticker)
    hist = t.history(period="1y", auto_adjust=True)
    if hist.empty or len(hist) < 30:
        return {"Ticker": ticker, "الحالة": "بيانات سعر غير كافية", "الدرجة": None}
    close = hist["Close"].dropna()
    price = safe_num(close.iloc[-1])
    high52 = safe_num(close.max())
    low52 = safe_num(close.min())
    drop = ((high52-price)/high52*100) if high52 else None
    avg_vol = safe_num(hist["Volume"].tail(20).mean())
    avg_dollar_vol = (avg_vol * price) if avg_vol and price else None

    info = {}
    try: info = t.get_info() or {}
    except Exception: pass

    financials = t.financials
    cashflow = t.cashflow
    balance = t.balance_sheet

    rev = find_row(financials, ["Total Revenue", "Operating Revenue"])
    net = find_row(financials, ["Net Income", "Net Income Common Stockholders"])
    fcf = find_row(cashflow, ["Free Cash Flow"])
    if fcf is None:
        ocf = find_row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        capex = find_row(cashflow, ["Capital Expenditure"])
        if ocf is not None and capex is not None:
            fcf = ocf.add(capex, fill_value=0)

    revenue_growth = None
    net_growth = None
    rev_up = False
    net_up = False
    if rev is not None and len(rev) >= 3:
        vals = list(rev.iloc[:3])
        revenue_growth = (vals[0]/vals[1]-1)*100 if vals[1] else None
        rev_up = vals[0] > vals[1] > vals[2]
    if net is not None and len(net) >= 3:
        vals = list(net.iloc[:3])
        net_growth = (vals[0]/vals[1]-1)*100 if vals[1] else None
        net_up = vals[0] > vals[1] > vals[2] and vals[0] > 0 and vals[1] > 0 and vals[2] > 0

    fcf_latest = safe_num(fcf.iloc[0]) if fcf is not None and len(fcf) else None
    debt = None
    equity = None
    if balance is not None and not balance.empty:
        debtrow = find_row(balance, ["Total Debt", "Long Term Debt And Capital Lease Obligation"])
        eqrow = find_row(balance, ["Stockholders Equity", "Total Stockholder Equity"])
        debt = safe_num(debtrow.iloc[0]) if debtrow is not None and len(debtrow) else None
        equity = safe_num(eqrow.iloc[0]) if eqrow is not None and len(eqrow) else None
    debt_equity = (debt/equity) if debt is not None and equity and equity > 0 else None

    # Conservative screening score; missing data is not treated as a pass.
    parts = {}
    parts["growth"] = 25 if rev_up and net_up else (12 if rev_up and net is not None else 0)
    parts["valuation"] = 0
    fair_value = None
    shares = safe_num(info.get("sharesOutstanding"))
    market_cap = safe_num(info.get("marketCap"))
    # Simple conservative 5-year FCF DCF; only shown when positive FCF and share count exist.
    if fcf_latest and fcf_latest > 0 and shares and shares > 0:
        growth = min(max((safe_num(info.get("revenueGrowth")) or 0.05), 0.00), 0.12)
        discount = 0.10
        terminal = 0.025
        pv = sum(fcf_latest*((1+growth)**yr)/((1+discount)**yr) for yr in range(1,6))
        terminal_value = fcf_latest*((1+growth)**5)*(1+terminal)/(discount-terminal)
        pv_terminal = terminal_value/((1+discount)**5)
        cash = safe_num(info.get("totalCash")) or 0
        total_debt = debt or 0
        fair_value = (pv + pv_terminal + cash - total_debt)/shares
        margin = ((fair_value-price)/fair_value*100) if fair_value > 0 else None
        parts["valuation"] = 20 if margin is not None and margin >= 30 else (12 if margin is not None and margin >= 15 else (5 if margin is not None and margin > 0 else 0))
    parts["balance"] = 15 if debt_equity is not None and debt_equity < 0.5 else (9 if debt_equity is not None and debt_equity < 1.5 else (3 if debt_equity is not None else 0))
    parts["fcf"] = 10 if fcf_latest is not None and fcf_latest > 0 else 0
    parts["insider"] = 0  # Not reliably available from this free source; never invent insider-buying data.
    parts["drawdown"] = 10 if drop is not None and drop >= min_drop_pct else (5 if drop is not None and drop >= min_drop_pct*0.7 else 0)
    parts["liquidity"] = 10 if avg_dollar_vol is not None and avg_dollar_vol >= 20_000_000 else (5 if avg_dollar_vol is not None and avg_dollar_vol >= 5_000_000 else 0)
    total = sum(parts.values())
    available_weight = 25+20+15+10+10+10  # insider category is explicitly unscored
    normalized = round(total/available_weight*100, 1)

    atr = None
    try:
        tr = pd.concat([(hist["High"]-hist["Low"]), (hist["High"]-hist["Close"].shift()).abs(),
                        (hist["Low"]-hist["Close"].shift()).abs()], axis=1).max(axis=1)
        atr = safe_num(tr.tail(14).mean())
    except Exception: pass
    stop = price - 1.5*atr if atr else None
    risk = (price-stop) if stop else None
    tp1 = price + 2*risk if risk else None
    tp2 = price + 3*risk if risk else None

    return {
        "Ticker": ticker, "الشركة": info.get("shortName", ticker), "السعر": price,
        "الهبوط من قمة 52أسبوع %": round(drop,1) if drop is not None else None,
        "نمو الإيرادات آخر سنة %": round(revenue_growth,1) if revenue_growth is not None else None,
        "صافي الأرباح يزيد 3 سنوات": "نعم" if net_up else ("لا" if net is not None and len(net)>=3 else "بيانات ناقصة"),
        "التدفق النقدي الحر": fcf_latest, "Debt/Equity": round(debt_equity,2) if debt_equity is not None else None,
        "القيمة العادلة التقديرية": round(fair_value,2) if fair_value else None,
        "وقف الخسارة الفني": round(stop,2) if stop else None,
        "الهدف 1": round(tp1,2) if tp1 else None, "الهدف 2": round(tp2,2) if tp2 else None,
        "الدرجة /100": normalized, "الدرجة الخام": total,
        "ملاحظة": "بيانات غير مكتملة" if rev is None or net is None else "فحص أولي"
    }

if run:
    tickers = list(dict.fromkeys(x.strip().upper() for x in tickers_text.replace("\n", ",").split(",") if x.strip()))
    if not tickers:
        st.error("أدخل رمز سهم واحدًا على الأقل.")
    else:
        rows=[]
        progress=st.progress(0, text="جارٍ تحميل بيانات الأسهم...")
        status=st.empty()
        for i, ticker in enumerate(tickers):
            status.write(f"يتم فحص {ticker} ({i+1}/{len(tickers)})")
            try:
                rows.append(score_stock(ticker, min_drop))
            except Exception as e:
                rows.append({"Ticker":ticker, "الحالة":"تعذر جلب البيانات", "الدرجة /100":None})
            progress.progress((i+1)/len(tickers))
        progress.empty(); status.empty()
        df=pd.DataFrame(rows)
        if "الهبوط من قمة 52أسبوع %" in df:
            df["مطابق لشرط الهبوط"] = df["الهبوط من قمة 52أسبوع %"].fillna(-1) >= min_drop
        if "الدرجة /100" in df:
            df=df.sort_values("الدرجة /100", ascending=False, na_position="last")
        st.subheader("نتائج الفحص")
        st.caption(f"وقت الفحص: {datetime.now().strftime('%Y-%m-%d %H:%M')} — الرموز المفحوصة: {len(tickers)}")
        st.dataframe(df.head(max_results), use_container_width=True, hide_index=True)
        st.download_button("⬇️ تحميل النتائج CSV", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="opportunity_hunter_results.csv", mime="text/csv")
        st.subheader("تفاصيل التقييم")
        st.write("النقاط الموزونة: نمو الإيرادات والأرباح 25، القيمة العادلة 20، المركز المالي 15، التدفق النقدي 10، الهبوط 10، السيولة 10. بند Insider Buying ظاهر كغير متاح في المصدر المجاني ولا يُمنح نقاطًا.")
        st.warning("القيمة العادلة هنا تقدير DCF مبسط وحساس للافتراضات، وليست تقييمًا مهنيًا. لا تدخل صفقة اعتمادًا على الدرجة وحدها.")
else:
    st.subheader("كيف يعمل؟")
    c1,c2,c3=st.columns(3)
    c1.metric("الأسواق", "الولايات المتحدة")
    c2.metric("نموذج التقييم", "100 نقطة")
    c3.metric("قائمة الفحص", "قابلة للتعديل")
    st.markdown("""
    - يرصد الهبوط من أعلى سعر خلال سنة.
    - يراجع نمو الإيرادات وصافي الأرباح لثلاث سنوات متاحة.
    - يفحص التدفق النقدي الحر والمديونية والسيولة.
    - يحسب قيمة عادلة تقديرية بطريقة DCF عند توافر البيانات.
    - يقترح مستويات فنية أولية من ATR، لا أوامر تداول.
    """)
    st.info("اضغط «افحص الأسهم الآن» من القائمة الجانبية لبدء أول فحص.")

st.divider()
st.caption("تنبيه: بيانات Yahoo Finance قد تكون متأخرة أو غير مكتملة، والنسخة الأولى لا تغطي تلقائيًا كل الأسهم الأمريكية. لا توجد ضمانات للربح. راجع أحدث التقارير الرسمية قبل الاستثمار.")
