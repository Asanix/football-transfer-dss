"""Squad audit for the target club: depth, starters, gaps vs. elite benchmark, sell/loan lists."""
import pandas as pd

from . import config


def find_club(df: pd.DataFrame, club: str) -> str:
    names = df["club_name"].dropna().unique()
    if club in names:
        return club
    hits = [n for n in names if club.lower() in n.lower()]
    if not hits:
        raise SystemExit(f"club '{club}' not found. Examples: {sorted(names)[:15]}")
    return sorted(hits, key=len)[0]


def squad(cur: pd.DataFrame, club: str) -> pd.DataFrame:
    return cur[cur["club_name"] == club].sort_values(["pos_group", "role_fit"], ascending=[True, False])


def starters_by_group(sq: pd.DataFrame) -> dict:
    """Best N players by role fit in each group, N = slots in the formation."""
    return {g: sq[sq["pos_group"] == g].nlargest(max(n, 1), "role_fit") for g, n in config.FORMATION.items()}


def elite_benchmark(cur: pd.DataFrame, club: str, top_n: int = 10) -> pd.Series:
    """Average starter role-fit per group across the top-N clubs by squad strength (excluding ours)."""
    strength = (cur[cur["club_name"].notna()].groupby("club_name")["overall"]
                .apply(lambda s: s.nlargest(15).mean()).sort_values(ascending=False))
    elite = [c for c in strength.index if c != club][:top_n]
    vals = {}
    for g, n in config.FORMATION.items():
        per_club = [cur[(cur["club_name"] == c) & (cur["pos_group"] == g)]["role_fit"].nlargest(max(n, 1)).mean()
                    for c in elite]
        vals[g] = pd.Series(per_club).mean()
    return pd.Series(vals, name="elite_starter_fit")


def audit(cur: pd.DataFrame, club: str) -> pd.DataFrame:
    sq = squad(cur, club)
    bench = elite_benchmark(cur, club)
    st = starters_by_group(sq)
    rows = []
    for g in config.FORMATION:
        grp = sq[sq["pos_group"] == g]
        starter_fit = st[g]["role_fit"].mean() if len(st[g]) else 0
        future = st[g]["overall_next_pred"].mean() if "overall_next_pred" in st[g] and len(st[g]) else float("nan")
        rows.append({
            "group": g, "slots": config.FORMATION[g], "players": len(grp), "min_depth": config.MIN_DEPTH[g],
            "starter_fit": round(starter_fit, 1), "elite_fit": round(bench[g], 1),
            "gap_vs_elite": round(starter_fit - bench[g], 1),
            "starter_overall_next_pred": round(future, 1),
            "avg_age": round(grp["age"].mean(), 1) if len(grp) else None,
            "contracts_ending_<=1y": int((grp["contract_years_left"] <= 1).sum()),
        })
    a = pd.DataFrame(rows)
    a["depth_short"] = (a["min_depth"] - a["players"]).clip(lower=0)
    # priority: quality gap matters most, depth shortage second, ageing starters third
    a["priority"] = (-a["gap_vs_elite"].clip(upper=0) * 1.0 + a["depth_short"] * 2.0
                     + (a["avg_age"].fillna(0) > 29) * 1.5) * (a["slots"] > 0)
    return a.sort_values("priority", ascending=False).reset_index(drop=True)


def sell_and_loan(cur: pd.DataFrame, club: str):
    sq = squad(cur, club).copy()
    st_ids = set(pd.concat(starters_by_group(sq).values())["player_id"])
    sq["is_starter"] = sq["player_id"].isin(st_ids)
    # sell: non-starters 27+ with value we can still cash in, or starters 31+ predicted to decline
    sell = sq[((~sq["is_starter"]) & (sq["age"] >= 27)) |
              ((sq["age"] >= 31) & (sq.get("pred_delta", 0) < -1))]
    sell = sell.sort_values("value_eur", ascending=False)
    # loan: young non-starters with growth room who need minutes
    loan = sq[(~sq["is_starter"]) & (sq["age"] <= 21) & (sq["growth_room"] >= 5)]
    return sq, sell, loan
