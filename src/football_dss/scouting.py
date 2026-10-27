"""Moneyball scoring + backtest that shows whether it beats a plain 'sort by overall' list."""
import numpy as np
import pandas as pd

from . import config


def moneyball_score(df: pd.DataFrame) -> pd.Series:
    """Combine what we want into one number (all parts are z-scored inside the position group).

    + tactical fit (role_fit)                      - is he good for OUR style?
    + expected rating next season                 - will he be good tomorrow?
    + style_bonus (fit above his FIFA overall)    - the market prices overall, not our style
    + value_gap (fair value above price)          - cheap relative to comparable players
    - bust risk                                   - chance he declines
    - log price                                   - we have a budget
    """
    def z(s):
        return s.groupby(df["pos_group"]).transform(lambda x: (x - x.mean()) / (x.std() + 1e-9))

    parts = (1.0 * z(df["role_fit"])
             + 1.0 * z(df["overall_next_pred"])
             + 0.6 * z(df["style_bonus"])
             + 0.5 * z(df["value_gap"].clip(-1, 2).fillna(0))
             - 0.7 * z(df["bust_risk"])
             - 0.8 * z(np.log1p(df["value_eur"].fillna(df["value_eur"].median()))))
    return parts


def shortlist(cur: pd.DataFrame, club: str, group: str, max_fee: float, max_age: int = 30,
              n: int = 15, min_fit: float | None = None) -> pd.DataFrame:
    pool = cur[(cur["pos_group"] == group) & (cur["club_name"] != club) & (cur["age"] <= max_age)
               & (cur["value_eur"].notna()) & (cur["value_eur"] * config.FEE_PREMIUM <= max_fee)
               & (cur["overall"] >= config.MIN_OVERALL_POOL)]
    if min_fit is not None:
        pool = pool[pool["role_fit"] >= min_fit]
    return pool.sort_values("moneyball", ascending=False).head(n)


def hidden_gems(cur: pd.DataFrame, club: str, n: int = 20) -> pd.DataFrame:
    """Players whose FIFA overall looks ordinary but who fit our tactical model much better."""
    pool = cur[(cur["club_name"] != club) & cur["value_eur"].notna() & (cur["age"] <= 26)
               & (cur["overall"].between(70, 80))]
    return pool.sort_values(["style_bonus"], ascending=False).head(n)


def backtest(prev_scored: pd.DataFrame, budget_per_player: float = 30e6, k: int = 20) -> pd.DataFrame:
    """Season t lists (built only from season-t info) vs what actually happened at t+1.

    prev_scored: season-t players with moneyball score AND realised overall_next / value_next.
    For each position group we take the top-k affordable players by each strategy and compare
    realised next-season role fit and value growth (resale)."""
    pool = prev_scored[(prev_scored["value_eur"] <= budget_per_player) & prev_scored["overall_next"].notna()
                       & (prev_scored["overall"] >= config.MIN_OVERALL_POOL) & (prev_scored["age"] <= 30)]
    strategies = {
        "sort by overall": "overall",
        "sort by overall / price": "_ovr_per_price",
        "Moneyball score (ours)": "moneyball",
    }
    pool = pool.assign(_ovr_per_price=pool["overall"] / np.log1p(pool["value_eur"]))
    rows = []
    for name, col in strategies.items():
        picks = pool.sort_values(col, ascending=False).groupby("pos_group").head(k)
        rows.append({
            "strategy": name,
            "players": len(picks),
            "avg price, M EUR": picks["value_eur"].mean() / 1e6,
            "next-season role fit": picks["role_fit_next"].mean(),
            "next-season overall": picks["overall_next"].mean(),
            "median value growth": picks["value_growth"].median(),
            "bust rate": picks["bust"].mean(),
        })
    return pd.DataFrame(rows)
