"""Transfer-window optimiser (integer linear programme, scipy.optimize.milp / HiGHS).

Decide whom to BUY (from shortlists) and whom to SELL (from the sell list) to maximise
the improvement of the starting XI under fee, wage, squad-size and depth constraints.

Variables: x_i = 1 if we buy candidate i, y_j = 1 if we sell squad player j.
"""
import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from . import config


def _current_slot_fit(squad: pd.DataFrame) -> dict:
    """Role fit of the WEAKEST current starter in each group = the bar a signing must clear."""
    out = {}
    for g, n in config.FORMATION.items():
        fits = squad[squad["pos_group"] == g]["role_fit"].nlargest(max(n, 1))
        out[g] = fits.min() if len(fits) else 0.0
    return out


def optimise(squad: pd.DataFrame, candidates: pd.DataFrame, sell_pool: pd.DataFrame,
             budget: float = config.TRANSFER_BUDGET_EUR, wage_budget: float = config.WAGE_BUDGET_EUR_WEEK,
             max_signings: int = config.MAX_SIGNINGS, resale_weight: float = 2.0) -> dict:
    bar = _current_slot_fit(squad)
    cand = candidates.drop_duplicates("player_id").copy()
    # use next-season role fit where available: we buy for the coming season, not the past one
    fit_now = cand["role_fit"]
    fit_next = cand["role_fit"] + cand.get("pred_delta", 0)
    cand["fit_used"] = (fit_now + fit_next) / 2
    cand["gain"] = (cand["fit_used"] - cand["pos_group"].map(bar)).clip(lower=0)
    cand["fee"] = cand["value_eur"] * config.FEE_PREMIUM
    # small bonus for resale potential, penalty for bust risk
    cand["score"] = (cand["gain"] + resale_weight * cand["pred_delta"].clip(lower=0) / 2
                     - 5 * cand["bust_risk"])
    sell = sell_pool.drop_duplicates("player_id").copy()
    sell["revenue"] = sell["value_eur"].fillna(0) * config.SALE_DISCOUNT
    cand[["wage_eur", "score", "fee"]] = cand[["wage_eur", "score", "fee"]].fillna(0)
    sell[["wage_eur", "role_fit"]] = sell[["wage_eur", "role_fit"]].fillna(0)

    nc, ns = len(cand), len(sell)
    zeros_c, zeros_s = np.zeros(nc), np.zeros(ns)
    # objective (milp minimises, so negate). Losing a squad player costs a little
    # (depth / dressing room), scaled by his fit.
    obj = -np.concatenate([cand["score"].to_numpy(), -0.05 * sell["role_fit"].to_numpy()])

    rows, lb, ub = [], [], []

    def add(coef_c, coef_s, lo=-np.inf, hi=np.inf):
        rows.append(np.concatenate([coef_c, coef_s])); lb.append(lo); ub.append(hi)

    add(cand["fee"].to_numpy(), -sell["revenue"].to_numpy(), hi=budget)
    add(cand["wage_eur"].to_numpy(), -sell["wage_eur"].to_numpy(), hi=wage_budget)
    add(np.ones(nc), zeros_s, hi=max_signings)
    for g, n in config.FORMATION.items():
        gc = (cand["pos_group"] == g).to_numpy(dtype=float)
        gs = (sell["pos_group"] == g).to_numpy(dtype=float)
        if gc.any():
            add(gc, zeros_s, hi=max(n, 1))                              # don't stack one position
        have = int((squad["pos_group"] == g).sum())
        add(gc, -gs, lo=min(config.MIN_DEPTH[g], have) - have)          # keep minimum depth

    res = milp(obj, constraints=LinearConstraint(np.array(rows), lb, ub),
               integrality=np.ones(nc + ns), bounds=Bounds(0, 1))
    z = res.x if res.x is not None else np.zeros(nc + ns)
    buys = cand[z[:nc] > 0.5].reset_index(drop=True)
    sells = sell[z[nc:] > 0.5].reset_index(drop=True)
    net_spend = buys["fee"].sum() - sells["revenue"].sum()
    return {
        "status": "Optimal" if res.success else res.message,
        "buys": buys, "sells": sells,
        "net_spend": net_spend, "gross_spend": buys["fee"].sum(), "sales": sells["revenue"].sum(),
        "wage_change_week": buys["wage_eur"].sum() - sells["wage_eur"].sum(),
        "xi_gain": buys["gain"].sum(),
        "squad_value_change": buys["value_eur"].sum() - sells["value_eur"].sum(),
    }


def budget_scenarios(squad, candidates, sell_pool, factors=(1.0, 0.8, 0.6, 0.4)) -> pd.DataFrame:
    """Sensitivity: what changes if the board cuts the budget?"""
    rows = []
    for f in factors:
        r = optimise(squad, candidates, sell_pool, budget=config.TRANSFER_BUDGET_EUR * f,
                     wage_budget=config.WAGE_BUDGET_EUR_WEEK * f)
        rows.append({
            "budget share": f"{f:.0%}",
            "budget, M EUR": config.TRANSFER_BUDGET_EUR * f / 1e6,
            "buys": ", ".join(r["buys"]["short_name"]) or "-",
            "sells": ", ".join(r["sells"]["short_name"]) or "-",
            "net spend, M EUR": r["net_spend"] / 1e6,
            "XI role-fit gain": r["xi_gain"],
            "status": r["status"],
        })
    return pd.DataFrame(rows)
