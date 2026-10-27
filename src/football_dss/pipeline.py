"""End-to-end run: data -> features -> models -> audit -> scouting -> optimiser -> report.

    python -m football_dss.pipeline            (from the src/ folder, or via run.ps1 / run.sh)
    python -m football_dss.pipeline --club "Real Sociedad"
"""
import argparse
import json
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from . import config, data, features, models, optimizer, scouting, squad, style
from .llm_report import llm_report

sns.set_theme(style="whitegrid")


def step(msg):
    print(f"\n=== {msg} ({time.strftime('%H:%M:%S')})")


def save(df: pd.DataFrame, name: str):
    df.to_csv(config.OUTPUTS / f"{name}.csv", index=False)


def score_season(df, pairs, version, fair, reg, clf):
    base = pairs if version < config.LAST_VERSION else df
    s = base[base["fifa_version"] == version].copy()
    s = s.merge(fair, on="player_id", how="left").merge(models.predict_future(s, reg, clf), on="player_id")
    s["moneyball"] = scouting.moneyball_score(s)
    return s


def figures(cur, val_metrics, growth, bt, audit, scen, pairs):
    f = config.FIGURES
    fig, ax = plt.subplots(figsize=(7, 4))
    audit.plot.barh(x="group", y="gap_vs_elite", ax=ax, legend=False,
                    color=["#c0392b" if v < 0 else "#27ae60" for v in audit["gap_vs_elite"]])
    ax.axvline(0, color="k", lw=1)
    ax.set_title("Starters' tactical fit vs elite clubs")
    ax.set_xlabel("role-fit difference")
    fig.tight_layout(); fig.savefig(f / "squad_gaps.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    d = pairs.dropna(subset=["delta_overall"])
    d.groupby("age")["delta_overall"].mean().loc[16:38].plot(ax=ax, marker="o")
    ax.axhline(0, color="k", lw=1)
    ax.set_title("Average change of overall in the next season by age")
    ax.set_ylabel("delta overall")
    fig.tight_layout(); fig.savefig(f / "age_curve.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    sns.barplot(data=growth["importance"], y="feature", x="importance", ax=ax, color="#2c7fb8")
    ax.set_title("What predicts next-season development (permutation importance)")
    fig.tight_layout(); fig.savefig(f / "growth_importance.png", dpi=150); plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for ax, col in zip(axes, ["next-season role fit", "median value growth", "bust rate"]):
        sns.barplot(data=bt, x="strategy", y=col, ax=ax, palette="Set2", hue="strategy", legend=False)
        ax.set_title(col); ax.set_xlabel(""); ax.tick_params(axis="x", rotation=20)
    fig.suptitle("Backtest FIFA 22 -> 23: shortlists of affordable players")
    fig.tight_layout(); fig.savefig(f / "backtest.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot([float(s.strip("%")) for s in scen["budget share"]], scen["XI role-fit gain"], marker="o")
    ax.set_xlabel("budget, % of plan"); ax.set_ylabel("XI role-fit gain")
    ax.set_title("Budget sensitivity")
    fig.tight_layout(); fig.savefig(f / "budget_scenarios.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 5))
    pool = cur[cur["overall"] >= 70].dropna(subset=["value_eur"])
    ax.scatter(pool["value_eur"] / 1e6, pool["style_bonus"], s=6, alpha=.3)
    ax.set_xscale("log"); ax.set_xlabel("FIFA value, M EUR (log)"); ax.set_ylabel("role fit - overall")
    ax.set_title("Market prices overall, not fit to our style")
    fig.tight_layout(); fig.savefig(f / "style_bonus_vs_value.png", dpi=150); plt.close(fig)


def md(df: pd.DataFrame, cols=None, n=15) -> str:
    d = df if cols is None else df[[c for c in cols if c in df]]
    return d.head(n).to_markdown(index=False, floatfmt=".2f")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--club", default=config.TARGET_CLUB)
    ap.add_argument("--rebuild", action="store_true", help="rebuild processed parquet from the raw csv")
    args = ap.parse_args(argv)

    step("1. data")
    df = data.build_processed(force=args.rebuild)
    dq = data.data_quality_report(df); save(dq, "data_quality"); print(dq.to_string(index=False))

    step("2. features")
    df = features.add_features(df)
    pairs = features.add_next_season(df)

    step("3. models (time split: train <= FIFA 22, test = FIFA 23)")
    _, val_metrics = models.value_model(df); save(val_metrics, "metrics_value"); print(val_metrics.to_string(index=False))
    growth = models.growth_models(pairs)
    save(growth["growth_metrics"], "metrics_growth"); save(growth["risk_metrics"], "metrics_bust")
    print(growth["growth_metrics"].to_string(index=False)); print(growth["risk_metrics"].to_string(index=False))

    step("4. scoring current & previous season")
    last, prev_v = config.LAST_VERSION, config.LAST_VERSION - 1
    cur = score_season(df, pairs, last, models.fair_value_oof(df, last), growth["reg_full"], growth["clf_full"])
    prev = score_season(df, pairs, prev_v, models.fair_value_oof(df, prev_v), growth["reg_test"], growth["clf_test"])

    step("5. backtest Moneyball vs simple rankings")
    bt = scouting.backtest(prev); save(bt, "backtest"); print(bt.to_string(index=False))

    step("6. style clusters + similarity validation")
    cur, silhouettes = style.add_clusters(cur)
    retr = style.self_retrieval_check(prev, cur); save(retr, "similarity_validation"); print(retr.to_string(index=False))

    step("7. squad audit")
    club = squad.find_club(cur, args.club)
    audit = squad.audit(cur, club); save(audit, "squad_audit"); print(audit.to_string(index=False))
    sq, sell, loan = squad.sell_and_loan(cur, club)
    save(sq, "squad"); save(sell, "sell_candidates"); save(loan, "loan_candidates")

    step("8. shortlists + optimiser")
    need = audit[audit["slots"] > 0].head(4)["group"].tolist()
    lists = [scouting.shortlist(cur, club, g, max_fee=config.TRANSFER_BUDGET_EUR) for g in need]
    cand = pd.concat(lists)
    save(cand, "shortlists")
    plan = optimizer.optimise(sq, cand, sell)
    save(plan["buys"], "plan_buys"); save(plan["sells"], "plan_sells")
    scen = optimizer.budget_scenarios(sq, cand, sell); save(scen, "budget_scenarios")
    print(scen.to_string(index=False))

    gems = scouting.hidden_gems(cur, club); save(gems, "hidden_gems")
    star = sq.sort_values("value_eur", ascending=False).iloc[0]
    twins = style.similar_players(cur, star["player_id"], max_value=star["value_eur"] * 0.3, max_age=27)
    save(twins, "cheaper_twins")

    cur.to_parquet(config.OUTPUTS / "players_scored.parquet", index=False)
    json.dump({"club": club, "silhouettes": {g: {str(k): v for k, v in s.items()} for g, s in silhouettes.items()}},
              open(config.OUTPUTS / "meta.json", "w"), indent=2)

    step("9. figures & report")
    figures(cur, val_metrics, growth, bt, audit, scen, pairs)
    facts = {
        "club": club, "budget_m": config.TRANSFER_BUDGET_EUR / 1e6, "net_spend_m": plan["net_spend"] / 1e6,
        "priorities": audit.head(4)[["group", "gap_vs_elite", "players", "min_depth"]].to_dict("records"),
        "buys": plan["buys"][["short_name", "pos_group", "age", "club_name", "role_fit", "fee", "bust_risk",
                              "overall", "potential"]].to_dict("records"),
        "sells": plan["sells"][["short_name", "pos_group", "age", "revenue"]].to_dict("records"),
        "budget_scenarios": scen.to_dict("records"),
        "backtest": bt.to_dict("records"),
    }
    memo = llm_report(facts)
    (config.REPORTS / "transfer_memo.md").write_text(memo, encoding="utf-8")

    cols = ["short_name", "age", "club_name", "pos_group", "overall", "role_fit", "overall_next_pred",
            "value_eur", "fair_value", "bust_risk", "moneyball"]
    report = f"""# Results: {club} (FIFA {last})

## Data quality
{md(dq)}

## Model quality (time split, test = FIFA {last})
### Fair value
{md(val_metrics)}
### Next-season development
{md(growth['growth_metrics'])}
### Bust risk (overall -2 or worse next season)
{md(growth['risk_metrics'])}
### Style similarity: does a player find himself one season later?
{md(retr)}

## Backtest FIFA {prev_v} -> {last}
{md(bt)}

## Squad audit
{md(audit)}

## Recommended plan (budget {config.TRANSFER_BUDGET_EUR/1e6:.0f}M EUR, status {plan['status']})
Buys:
{md(plan['buys'], cols + ['fee', 'gain'])}

Sells:
{md(plan['sells'], ['short_name', 'age', 'pos_group', 'value_eur', 'revenue'])}

Net spend: {plan['net_spend']/1e6:.1f}M EUR, wage change {plan['wage_change_week']:,.0f} EUR/week.

## Budget scenarios
{md(scen)}

## Hidden gems (fit our style much better than their overall suggests)
{md(gems, cols + ['style_bonus'])}

## Cheaper style twins of {star['short_name']}
{md(twins, cols + ['style_similarity'])}

## Loan candidates
{md(loan, ['short_name', 'age', 'pos_group', 'overall', 'potential'])}
"""
    (config.REPORTS / "results.md").write_text(report, encoding="utf-8")
    print(f"\nDone. See {config.REPORTS / 'results.md'}, {config.REPORTS / 'transfer_memo.md'}, {config.FIGURES}")


if __name__ == "__main__":
    main()
