"""Download the FIFA 15-23 player dataset and turn it into one tidy parquet file.

Raw file: male_players.csv (one row per player per FIFA version per in-game update).
Processed: one row per (player_id, fifa_version) - the LAST update of each version,
i.e. the end-of-season snapshot.
"""
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import config

ID_COLS = ["player_id", "fifa_version", "fifa_update", "short_name", "long_name", "player_positions",
           "club_name", "league_name", "league_level", "nationality_name", "club_position",
           "club_contract_valid_until_year", "club_loaned_from", "preferred_foot", "work_rate"]
NUM_COLS = ["overall", "potential", "value_eur", "wage_eur", "age", "height_cm", "weight_kg",
            "weak_foot", "skill_moves", "international_reputation", "release_clause_eur",
            "pace", "shooting", "passing", "dribbling", "defending", "physic"]
DETAIL_COLS = [
    "attacking_crossing", "attacking_finishing", "attacking_heading_accuracy", "attacking_short_passing",
    "attacking_volleys", "skill_dribbling", "skill_curve", "skill_fk_accuracy", "skill_long_passing",
    "skill_ball_control", "movement_acceleration", "movement_sprint_speed", "movement_agility",
    "movement_reactions", "movement_balance", "power_shot_power", "power_jumping", "power_stamina",
    "power_strength", "power_long_shots", "mentality_aggression", "mentality_interceptions",
    "mentality_positioning", "mentality_vision", "mentality_penalties", "mentality_composure",
    "defending_marking_awareness", "defending_standing_tackle", "defending_sliding_tackle",
    "goalkeeping_diving", "goalkeeping_handling", "goalkeeping_kicking", "goalkeeping_positioning",
    "goalkeeping_reflexes",
]
WANTED = set(ID_COLS + NUM_COLS + DETAIL_COLS)


def raw_path() -> Path:
    return config.DATA_RAW / config.RAW_FILE


def download() -> Path:
    """Fetch male_players.csv via kagglehub unless it is already in data/raw."""
    target = raw_path()
    if target.exists():
        print(f"[data] raw file present: {target}")
        return target
    try:
        import kagglehub
        print(f"[data] downloading {config.KAGGLE_DATASET} (several GB, takes a while)...")
        folder = Path(kagglehub.dataset_download(config.KAGGLE_DATASET))
    except Exception as exc:  # no credentials / no network
        raise SystemExit(
            f"\n[data] automatic download failed: {exc}\n"
            "Do it manually:\n"
            f"  1. open https://www.kaggle.com/datasets/{config.KAGGLE_DATASET}\n"
            f"  2. download '{config.RAW_FILE}'\n"
            f"  3. put it here: {target}\n"
            "or configure Kaggle API: https://www.kaggle.com/docs/api#authentication\n"
        )
    found = next(folder.rglob(config.RAW_FILE), None)
    if found is None:
        raise SystemExit(f"[data] {config.RAW_FILE} not found inside {folder}")
    shutil.copy(found, target)
    print(f"[data] saved to {target}")
    return target


def _clean_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = chunk[chunk["fifa_version"].between(config.FIRST_VERSION, config.LAST_VERSION)]
    # keep the last in-game update of every season
    chunk = chunk.sort_values("fifa_update").drop_duplicates(["player_id", "fifa_version"], keep="last")
    return chunk


def build_processed(force: bool = False) -> pd.DataFrame:
    out = config.PLAYERS_PARQUET
    if out.exists() and not force:
        print(f"[data] processed file present: {out}")
        return pd.read_parquet(out)

    src = raw_path()
    if not src.exists():
        download()
    print(f"[data] reading {src} in chunks...")
    parts = []
    for chunk in pd.read_csv(src, usecols=lambda c: c in WANTED, chunksize=500_000, low_memory=False):
        parts.append(_clean_chunk(chunk))
    df = pd.concat(parts, ignore_index=True)
    df = df.sort_values("fifa_update").drop_duplicates(["player_id", "fifa_version"], keep="last")
    df = clean(df)
    df.to_parquet(out, index=False)
    print(f"[data] {len(df):,} player-seasons -> {out}")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in set(NUM_COLS + DETAIL_COLS) & set(df.columns):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["fifa_version"] = df["fifa_version"].astype(int)
    # FIFA 23 describes season 2022/23 -> calendar year of the snapshot = 2000 + version - 1
    df["season_year"] = 2000 + df["fifa_version"] - 1
    # value 0 / NaN means "no market value" in FIFA (free agents, youth) - not a real price
    df.loc[df["value_eur"] <= 0, "value_eur"] = np.nan
    # outfield players have NaN goalkeeping summary stats and vice versa -> fill detail stats only
    df[DETAIL_COLS] = df[DETAIL_COLS].fillna(df[DETAIL_COLS].median())
    df = df.dropna(subset=["overall", "age", "player_positions"])
    return df.reset_index(drop=True)


def data_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """Missing values / duplicates / outliers summary for the README & slides."""
    rows = []
    for col in ["value_eur", "wage_eur", "club_name", "league_name", "club_contract_valid_until_year",
                "pace", "release_clause_eur"]:
        if col in df:
            rows.append({"check": f"missing {col}", "value": f"{df[col].isna().mean():.1%}"})
    rows.append({"check": "duplicate (player_id, fifa_version)",
                 "value": int(df.duplicated(["player_id", "fifa_version"]).sum())})
    rows.append({"check": "player-seasons", "value": len(df)})
    rows.append({"check": "unique players", "value": df["player_id"].nunique()})
    v = df["value_eur"].dropna()
    q1, q3 = v.quantile([0.25, 0.75])
    rows.append({"check": "value_eur outliers (>Q3+3*IQR)", "value": int((v > q3 + 3 * (q3 - q1)).sum())})
    rows.append({"check": "age range", "value": f"{df['age'].min():.0f}-{df['age'].max():.0f}"})
    return pd.DataFrame(rows)
