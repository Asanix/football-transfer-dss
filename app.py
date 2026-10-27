"""Interactive DSS for the sporting director.   streamlit run app.py   (after the pipeline)"""
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from football_dss import config, optimizer, scouting, squad, style  # noqa: E402

st.set_page_config(page_title="Football DSS", layout="wide")

scored = config.OUTPUTS / "players_scored.parquet"
if not scored.exists():
    st.error("No results yet. Run the pipeline first: run.ps1 (Windows) or ./run.sh")
    st.stop()


@st.cache_data
def load():
    return pd.read_parquet(scored), json.load(open(config.OUTPUTS / "meta.json"))


cur, meta = load()
clubs = sorted(cur["club_name"].dropna().unique())
club = st.sidebar.selectbox("Club", clubs, index=clubs.index(meta["club"]) if meta["club"] in clubs else 0)
budget = st.sidebar.slider("Transfer budget, M EUR", 0, 300, int(config.TRANSFER_BUDGET_EUR / 1e6), 5) * 1e6
wage = st.sidebar.slider("Extra wage budget, k EUR/week", 0, 2000, int(config.WAGE_BUDGET_EUR_WEEK / 1e3), 50) * 1e3
max_age = st.sidebar.slider("Max age of signings", 18, 34, 29)
max_sign = st.sidebar.slider("Max signings", 1, 6, config.MAX_SIGNINGS)

COLS = ["short_name", "age", "club_name", "league_name", "pos_group", "overall", "potential", "role_fit",
        "overall_next_pred", "value_eur", "fair_value", "wage_eur", "bust_risk", "moneyball", "style_cluster"]

tab_audit, tab_scout, tab_twin, tab_plan, tab_quality = st.tabs(
    ["Squad audit", "Moneyball scout", "Cheaper twins", "Transfer plan", "Model quality"])

with tab_audit:
    audit = squad.audit(cur, club)
    st.subheader(f"{club}: where are we weaker than elite clubs?")
    st.plotly_chart(px.bar(audit, x="gap_vs_elite", y="group", orientation="h", color="gap_vs_elite",
                           color_continuous_scale="RdYlGn"), width="stretch")
    st.dataframe(audit, width="stretch")
    sq, sell, loan = squad.sell_and_loan(cur, club)
    c1, c2 = st.columns(2)
    c1.markdown("**Sell candidates**"); c1.dataframe(sell[COLS], width="stretch")
    c2.markdown("**Loan candidates**"); c2.dataframe(loan[COLS], width="stretch")
    st.markdown("**Full squad**"); st.dataframe(sq[COLS], width="stretch")

with tab_scout:
    g = st.selectbox("Position group", list(config.FORMATION), index=list(config.FORMATION).index(audit.iloc[0]["group"]))
    fee = st.slider("Max fee for one player, M EUR", 1, 200, 40) * 1e6
    sl = scouting.shortlist(cur, club, g, max_fee=fee, max_age=max_age, n=30)
    st.dataframe(sl[COLS], width="stretch")
    st.plotly_chart(px.scatter(sl, x="value_eur", y="role_fit", size="potential", color="bust_risk",
                               hover_name="short_name", log_x=True, color_continuous_scale="RdYlGn_r"),
                    width="stretch")
    st.markdown("**Hidden gems**: ordinary overall, strong fit to our style")
    st.dataframe(scouting.hidden_gems(cur, club)[COLS + ["style_bonus"]], width="stretch")

with tab_twin:
    names = cur.sort_values("value_eur", ascending=False)
    label = names["short_name"] + " (" + names["club_name"].fillna("-") + ")"
    pick = st.selectbox("Reference player", label.head(500))
    ref = names.loc[label[label == pick].index[0]]
    share = st.slider("Max price as % of reference", 5, 100, 30)
    tw = style.similar_players(cur, ref["player_id"], n=15, max_value=ref["value_eur"] * share / 100, max_age=max_age)
    st.write(f"{ref['short_name']}: overall {ref['overall']}, value {ref['value_eur']/1e6:.1f}M, cluster {ref['style_cluster']}")
    st.dataframe(tw[COLS + ["style_similarity"]] if len(tw) else tw, width="stretch")

with tab_plan:
    need = audit[audit["slots"] > 0].head(4)["group"].tolist()
    cand = pd.concat([scouting.shortlist(cur, club, gg, max_fee=max(budget, 1), max_age=max_age) for gg in need])
    plan = optimizer.optimise(sq, cand, sell, budget=budget, wage_budget=wage, max_signings=max_sign)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net spend", f"{plan['net_spend']/1e6:.1f}M")
    m2.metric("Sales", f"{plan['sales']/1e6:.1f}M")
    m3.metric("Wage change / week", f"{plan['wage_change_week']/1e3:.0f}k")
    m4.metric("XI role-fit gain", f"{plan['xi_gain']:.1f}")
    st.markdown("**Buy**"); st.dataframe(plan["buys"].reindex(columns=COLS + ["fee", "gain"]), width="stretch")
    st.markdown("**Sell**"); st.dataframe(plan["sells"].reindex(columns=COLS + ["revenue"]), width="stretch")
    st.caption(f"Solver status: {plan['status']}. Fee = FIFA value x {config.FEE_PREMIUM}, sale = value x {config.SALE_DISCOUNT} (assumptions).")

with tab_quality:
    for name in ["metrics_value", "metrics_growth", "metrics_bust", "similarity_validation", "backtest", "data_quality"]:
        p = config.OUTPUTS / f"{name}.csv"
        if p.exists():
            st.markdown(f"**{name}**"); st.dataframe(pd.read_csv(p), width="stretch")
    for img in sorted(config.FIGURES.glob("*.png")):
        st.image(str(img), caption=img.stem)
