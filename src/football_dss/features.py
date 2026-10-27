"""Feature engineering: position groups, tactical role fit, contract, next-season targets."""
import numpy as np
import pandas as pd

from . import config

POSITION_GROUP = {
    "GK": "GK", "CB": "CB",
    "LB": "FB", "RB": "FB", "LWB": "FB", "RWB": "FB",
    "CDM": "DM", "CM": "CM", "CAM": "AM",
    "LM": "W", "RM": "W", "LW": "W", "RW": "W",
    "ST": "ST", "CF": "ST",
}
GROUPS = list(config.FORMATION)


def main_position(positions: str) -> str:
    return str(positions).split(",")[0].strip()


def role_fit(df: pd.DataFrame, group: str) -> pd.Series:
    """Weighted average of the attributes our tactical model needs for this group (0-100)."""
    weights = config.ROLE_WEIGHTS[group]
    w = pd.Series(weights, dtype=float)
    return (df[list(w.index)] * w).sum(axis=1) / w.sum()


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["position"] = df["player_positions"].map(main_position)
    df["pos_group"] = df["position"].map(POSITION_GROUP).fillna("CM")
    df["role_fit"] = np.nan
    for g in GROUPS:
        mask = df["pos_group"] == g
        df.loc[mask, "role_fit"] = role_fit(df.loc[mask], g)
    # how much better/worse the player fits OUR style than his generic FIFA rating suggests
    df["style_bonus"] = df["role_fit"] - df["overall"]
    df["growth_room"] = df["potential"] - df["overall"]
    df["contract_years_left"] = (df["club_contract_valid_until_year"] - df["season_year"]).clip(lower=0)
    df["log_value"] = np.log1p(df["value_eur"])
    df["log_wage"] = np.log1p(df["wage_eur"])
    df["is_loan"] = df.get("club_loaned_from", pd.Series(index=df.index)).notna().astype(int)
    return df


def add_next_season(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the player's NEXT-season overall/value (targets for growth & risk models).

    Targets come from version t+1, features from version t only -> no leakage from the future.
    """
    nxt = df[["player_id", "fifa_version", "overall", "value_eur", "role_fit"]].copy()
    nxt["fifa_version"] -= 1
    nxt = nxt.rename(columns={"overall": "overall_next", "value_eur": "value_next", "role_fit": "role_fit_next"})
    out = df.merge(nxt, on=["player_id", "fifa_version"], how="left")
    out["delta_overall"] = out["overall_next"] - out["overall"]
    out["value_growth"] = out["value_next"] / out["value_eur"] - 1
    # "bust": the player got clearly worse a year later (or disappeared from the game)
    out["bust"] = (out["delta_overall"] <= -2).astype(float)
    out.loc[out["overall_next"].isna(), "bust"] = np.nan
    return out


MODEL_FEATURES = [
    "overall", "potential", "age", "growth_room", "international_reputation", "league_level",
    "contract_years_left", "skill_moves", "weak_foot", "height_cm", "role_fit",
    "pace", "shooting", "passing", "dribbling", "defending", "physic",
    "movement_reactions", "mentality_composure", "power_stamina",
]
CATEGORICAL = ["pos_group"]


def model_matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = df[MODEL_FEATURES].copy()
    for g in GROUPS:
        X[f"pos_{g}"] = (df["pos_group"] == g).astype(int)
    return X
