import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Opportunity Hunter | صائد الفرص", page_icon="🎯", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; max-width: 1400px;}
.small-note {color: #9ca3af; font-size: 0.85rem;}
</style>
""", unsafe_allow_html=True)

st.title("🎯 Opportunity Hunter | صائد الفرص")
st.caption("ماسح أولي لاكتشاف الشركات الأمريكية القوية بعد هبوط أسعارها — أداة بحث وليست توصية شراء.")

DEFAULT_TICKERS = """NVDA,MSFT,GOOGL,AMZN,META,AVGO,AMD,ORCL,CRM,ADBE,
NFLX,COST,LLY,JPM,V,MA,BRK-B,UNH,HD,ABBV,
PANW,CRWD,PLTR,SHOP,UBER,ABNB,TSLA,INTC,QCOM,TXN,
MU,AMAT,LRCX,KLAC,AMGN,ISRG,GE,CAT,KO,PEP,
WMT,TGT,LOW,DIS,CSCO,IBM,ACN,NOW,SNPS,CDNS""".replace(" ", "")

with st.sidebar:
    st.header("إعدادات الفحص")
    tickers_text = st.text_area(
        "رموز الأسهم الأمريكية (Ticker)", DEFAULT_TICKERS, height=220,
        help="ابدأ بالقائمة المبدئية، ويمكنك إضافة أو حذف رموز مفصولة بفواصل."
    )
    max_results = st.slider("عدد أفضل الفرص المعروضة", 3, 20, 5)
    min_drop = st.slider("أقل هبوط من قمة 52 أسبوعًا (%)", 5, 70, 20)
    st.caption("شرط صافي الأرباح لخمس سنوات إلزامي ولا يمكن تعطيله.")
    run = st.button("🔎 افحص الأسهم الآن", type="primary", use_container_width=True)

st.info(
    "**مصادر البيانات في النسخة الحالية:** Yahoo Finance عبر مكتبة yfinance. "
    "قد تتأخر البيانات أو تنقص بعض القوائم المالية. التغطية تعتمد على الرموز المدخلة "
    "وليست مسحًا شاملًا لكل الأسهم الأمريكية."
)

def safe_num(x):
    try:
        if pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None

def find_row(df, names):
    """Return an annual financial row ordered newest-to-oldest."""
    if df is None or df.empty:
        return None
    for name in names:
        for idx in df.index:
            if str(idx).strip().lower() == name.lower():
                vals = pd.to_numeric(df.loc[idx], errors="coerce").dropna()
                if len(vals):
                    try:
                        vals = vals.sort_index(ascending=False)
                    except Exception:
                        pass
                    return vals
    return None

def score_stock(ticker, min_drop_pct):
    t = yf.Ticker(ticker)
    hist = t.history(period="1y", auto_adjust=True)
    if hist.empty or len(hist) < 30:
        return {
            "Ticker": ticker, "الحالة": "بيانات سعر غير كافية",
            "مؤهل للترشيح": "لا", "سبب الاستبعاد": "بيانات السعر غير كافية",
            "الدرجة /100": None
        }

    close = hist["Close"].dropna()
    price = safe_num(close.iloc[-1])
    high52 = safe_num(close.max())
    drop = ((high52 - price) / high52 * 100) if high52 else None
    avg_vol = safe_num(hist["Volume"].tail(20).mean())
    avg_dollar_vol = avg_vol * price if avg_vol and price else None

    try:
        info = t.get_info() or {}
    except Exception:
        info = {}

    try:
        financials = t.financials
    except Exception:
        financials = pd.DataFrame()
    try:
        cashflow = t.cashflow
    except Exception:
        cashflow = pd.DataFrame()
    try:
        balance = t.balance_sheet
    except Exception:
        balance = pd.DataFrame()

    rev = find_row(financials, ["Total Revenue", "Operating Revenue"])
    net = find_row(financials, ["Net Income", "Net Income Common Stockholders"])

    # Mandatory eligibility rule: five complete annual values, each positive,
    # with every newer year's net income strictly greater than the prior year.
    net_values_5y = list(net.iloc[:5]) if net is not None and len(net) >= 5 else []
    net_up_5y = (
        len(net_values_5y) == 5
        and all(v > 0 for v in net_values_5y)
        and all(net_values_5y[i] > net_values_5y[i + 1] for i in range(4))
    )

    if len(net_values_5y) < 5:
        eligibility_reason = "بيانات صافي الأرباح لآخر 5 سنوات غير مكتملة"
    elif not all(v > 0 for v in net_values_5y):
        eligibility_reason = "صافي الأرباح ليس موجبًا في كل سنة من آخر 5 سنوات"
    elif not net_up_5y:
        eligibility_reason = "صافي الأرباح لم يزد سنة بعد سنة خلال آخر 5 سنوات"
    else:
        eligibility_reason = ""

    revenue_growth = None
    rev_up = False
    if rev is not None and len(rev) >= 3:
        rev_values = list(rev.iloc[:3])
        if rev_values[1]:
            revenue_growth = (rev_values[0] / rev_values[1] - 1) * 100
        rev_up = rev_values[0] > rev_values[1] > rev_values[2]

    fcf = find_row(cashflow, ["Free Cash Flow"])
    if fcf is None:
        ocf = find_row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        capex = find_row(cashflow, ["Capital Expenditure"])
        if ocf is not None and capex is not None:
            fcf = ocf.add(capex, fill_value=0)
    fcf_latest = safe_num(fcf.iloc[0]) if fcf is not None and len(fcf) else None

    debt = equity = None
    if balance is not None and not balance.empty:
        debtrow = find_row(balance, ["Total Debt", "Long Term Debt And Capital Lease Obligation"])
        eqrow = find_row(balance, ["Stockholders Equity", "Total Stockholder Equity"])
        debt = safe_num(debtrow.iloc[0]) if debtrow is not None and len(debtrow) else None
        equity = safe_num(eqrow.iloc[0]) if eqrow is not None and len(eqrow) else None
    debt_equity = debt / equity if debt is not None and equity and equity > 0 else None

    parts = {}
    parts["growth"] = 25 if rev_up and net_up_5y else 0
    parts["valuation"] = 0
    fair_value = None
    shares = safe_num(info.get("sharesOutstanding"))

    # Simplified indicative DCF only; never treat it as a professional valuation.
    if fcf_latest and fcf_latest > 0 and shares and shares > 0:
        growth = min(max((safe_num(info.get("revenueGrowth")) or 0.05), 0.00), 0.12)
        discount = 0.10
        terminal = 0.025
        pv = sum(
            fcf_latest * ((1 + growth) ** yr) / ((1 + discount) ** yr)
            for yr in range(1, 6)
        )
        terminal_value = fcf_latest * ((1 + growth) ** 5) * (1 + terminal) / (discount - terminal)
        pv_terminal = terminal_value / ((1 + discount) ** 5)
        cash = safe_num(info.get("totalCash")) or 0
        fair_value = (pv + pv_terminal + cash - (debt or 0)) / shares
        margin = ((fair_value - price) / fair_value * 100) if fair_value > 0 else None
        parts["valuation"] = (
            20 if margin is not None and margin >= 30
            else 12 if margin is not None and margin >= 15
            else 5 if margin is not None and margin > 0
            else 0
        )

    parts["balance"] = (
        15 if debt_equity is not None and debt_equity < 0.5
        else 9 if debt_equity is not None and debt_equity < 1.5
        else 3 if debt_equity is not None
        else 0
    )
    parts["fcf"] = 10 if fcf_latest is not None and fcf_latest > 0 else 0
    parts["insider"] = 0  # No reliable insider-transaction feed in this version.
    parts["drawdown"] = (
        10 if drop is not None and drop >= min_drop_pct
        else 5 if drop is not None and drop >= min_drop_pct * 0.7
        else 0
    )
    parts["liquidity"] = (
        10 if avg_dollar_vol is not None and avg_dollar_vol >= 20_000_000
        else 5 if avg_dollar_vol is not None and avg_dollar_vol >= 5_000_000
        else 0
    )

    total = sum(parts.values())
    # Keep the original 100-point scale. Missing Insider Buying data earns zero;
    # do not rescale 90 available points into 100.
    displayed_score = round(total, 1) if net_up_5y else None

    try:
        tr = pd.concat([
            hist["High"] - hist["Low"],
            (hist["High"] - hist["Close"].shift()).abs(),
            (hist["Low"] - hist["Close"].shift()).abs()
        ], axis=1).max(axis=1)
        atr = safe_num(tr.tail(14).mean())
    except Exception:
        atr = None

    stop = price - 1.5 * atr if atr else None
    risk = price - stop if stop else None
    tp1 = price + 2 * risk if risk else None
    tp2 = price + 3 * risk if risk else None

    return {
        "Ticker": ticker,
        "الشركة": info.get("shortName", ticker),
        "السعر": price,
        "مؤهل للترشيح": "نعم" if net_up_5y else "لا",
        "سبب الاستبعاد": eligibility_reason,
        "الهبوط من قمة 52أسبوع %": round(drop, 1) if drop is not None else None,
        "نمو الإيرادات آخر سنة %": round(revenue_growth, 1) if revenue_growth is not None else None,
        "صافي الأرباح موجب ومتزايد 5 سنوات": "نعم" if net_up_5y else "لا",
        "التدفق النقدي الحر": fcf_latest,
        "Debt/Equity": round(debt_equity, 2) if debt_equity is not None else None,
        "القيمة العادلة التقديرية": round(fair_value, 2) if fair_value else None,
        "وقف الخسارة الفني": round(stop, 2) if stop else None,
        "الهدف 1": round(tp1, 2) if tp1 else None,
        "الهدف 2": round(tp2, 2) if tp2 else None,
        "الدرجة /100": displayed_score,
        "الدرجة الخام": total if net_up_5y else None,
        "ملاحظة": "بيانات غير مكتملة" if rev is None or net is None else "فحص أولي"
    }

if run:
    tickers = list(dict.fromkeys(
        x.strip().upper()
        for x in tickers_text.replace("\n", ",").split(",")
        if x.strip()
    ))
    if not tickers:
        st.error("أدخل رمز سهم واحدًا على الأقل.")
    else:
        rows = []
        progress = st.progress(0, text="جارٍ تحميل بيانات الأسهم...")
        status = st.empty()
        for i, ticker in enumerate(tickers):
            status.write(f"يتم فحص {ticker} ({i + 1}/{len(tickers)})")
            try:
                rows.append(score_stock(ticker, min_drop))
            except Exception:
                rows.append({
                    "Ticker": ticker,
                    "الحالة": "تعذر جلب البيانات",
                    "مؤهل للترشيح": "لا",
                    "سبب الاستبعاد": "تعذر جلب البيانات أو تحليلها",
                    "الدرجة /100": None
                })
            progress.progress((i + 1) / len(tickers))
        progress.empty()
        status.empty()

        df = pd.DataFrame(rows)
        if "الهبوط من قمة 52أسبوع %" in df:
            df["مطابق لشرط الهبوط"] = df["الهبوط من قمة 52أسبوع %"].fillna(-1) >= min_drop

        st.subheader("أفضل الفرص المؤهلة")
        st.caption(
            f"وقت الفحص: {datetime.now().strftime('%Y-%m-%d %H:%M')} "
            f"— الرموز المفحوصة: {len(tickers)}"
        )

        eligible = df[df.get("مؤهل للترشيح", pd.Series(index=df.index, dtype=str)) == "نعم"].copy()
        if not eligible.empty:
            eligible = eligible.sort_values("الدرجة /100", ascending=False, na_position="last")
            st.success(f"تم العثور على {len(eligible)} شركة اجتازت شرط صافي الأرباح لخمس سنوات.")
            st.dataframe(eligible.head(max_results), use_container_width=True, hide_index=True)
        else:
            st.warning(
                "لم تجتز أي شركة شرط صافي الأرباح الموجب والمتزايد خلال آخر 5 سنوات. "
                "لن نعرض أسهمًا غير مؤهلة كفرص."
            )

        with st.expander("عرض الشركات المستبعدة وأسباب الاستبعاد"):
            rejected = df[df.get("مؤهل للترشيح", pd.Series(index=df.index, dtype=str)) != "نعم"]
            if not rejected.empty:
                st.dataframe(rejected, use_container_width=True, hide_index=True)

        st.download_button(
            "⬇️ تحميل كل نتائج الفحص CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name="opportunity_hunter_results.csv",
            mime="text/csv"
        )

        st.subheader("تفاصيل التقييم")
        st.write(
            "شرط أهلية إلزامي: صافي الربح موجب ومتزايد سنة بعد سنة في آخر 5 سنوات مالية، "
            "مع توافر بيانات السنوات الخمس كاملة. الشركات المخالفة أو ذات البيانات الناقصة "
            "تُستبعد من الترشيحات. النقاط من 100: نمو الإيرادات والأرباح 25، القيمة العادلة 20، "
            "المركز المالي 15، التدفق النقدي 10، Insider Buying 10، الهبوط 10، السيولة 10. "
            "بند Insider Buying لا يحصل على نقاط حتى يتوفر مصدر موثوق."
        )
        st.warning(
            "القيمة العادلة هنا تقدير DCF مبسط وحساس للافتراضات، وليست تقييمًا مهنيًا. "
            "لا تدخل صفقة اعتمادًا على الدرجة وحدها."
        )
else:
    st.subheader("كيف يعمل؟")
    c1, c2, c3 = st.columns(3)
    c1.metric("الأسواق", "الولايات المتحدة")
    c2.metric("نموذج التقييم", "100 نقطة")
    c3.metric("قائمة الفحص", "قابلة للتعديل")
    st.markdown("""
    - يرصد الهبوط من أعلى سعر خلال سنة.
    - يشترط صافي ربح موجبًا ومتزايدًا في كل سنة من آخر 5 سنوات مالية؛ وإلا تُستبعد الشركة من الترشيحات.
    - يفحص التدفق النقدي الحر والمديونية والسيولة.
    - يحسب قيمة عادلة تقديرية بطريقة DCF عند توافر البيانات.
    - يقترح مستويات فنية أولية من ATR، لا أوامر تداول.
    """)
    st.info("اضغط «افحص الأسهم الآن» من القائمة الجانبية لبدء أول فحص.")

st.divider()
st.caption(
    "تنبيه: بيانات Yahoo Finance قد تكون متأخرة أو غير مكتملة، والنسخة الأولى لا تغطي تلقائيًا "
    "كل الأسهم الأمريكية. لا توجد ضمانات للربح. راجع أحدث التقارير الرسمية قبل الاستثمار."
)
