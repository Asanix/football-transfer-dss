"""Generate a FAKE male_players.csv with the real column layout - only to smoke-test the code.
Never use it for conclusions.

    python tests/make_synthetic.py <out_dir>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from football_dss.data import DETAIL_COLS  # noqa: E402

rng = np.random.default_rng(0)
POS = ["GK", "CB", "CB", "LB", "RB", "CDM", "CM", "CM", "CAM", "LW", "RW", "ST", "LM", "CF"]
CLUBS = ["Real Madrid CF"] + [f"Club {i}" for i in range(59)]


def main(out_dir: Path, n_players: int = 3000):
    base = pd.DataFrame({
        "player_id": np.arange(n_players),
        "short_name": [f"P. Player{i}" for i in range(n_players)],
        "player_positions": rng.choice(POS, n_players),
        "age0": rng.integers(16, 34, n_players),
        "talent": rng.normal(68, 7, n_players),
        "club_name": rng.choice(CLUBS, n_players),
    })
    rows = []
    for v in range(17, 24):
        for upd in (1, 2):
            d = base.copy()
            d["fifa_version"] = float(v)
            d["fifa_update"] = upd
            d["age"] = d["age0"] + (v - 17)
            peak = -0.08 * (d["age"] - 27) ** 2
            d["overall"] = (d["talent"] + peak + rng.normal(0, 1.5, n_players)).clip(45, 93).round()
            d["potential"] = np.maximum(d["overall"], d["overall"] + (28 - d["age"]).clip(0) * 1.2).round()
            d["value_eur"] = (np.exp((d["overall"] - 50) / 6.5) * 1e4 * (1 + (30 - d["age"]).clip(0) / 10)).round(-4)
            d["wage_eur"] = (d["value_eur"] / 400).round(-2)
            d["release_clause_eur"] = d["value_eur"] * 1.9
            d["league_name"] = "League " + (d["club_name"].str[-1])
            d["league_level"] = 1
            d["club_contract_valid_until_year"] = 2000 + v + rng.integers(0, 5, n_players)
            d["international_reputation"] = (d["overall"] > 82).astype(int) + 1
            d["height_cm"] = rng.normal(181, 7, n_players).round()
            d["weight_kg"] = rng.normal(75, 7, n_players).round()
            d["weak_foot"] = rng.integers(1, 6, n_players)
            d["skill_moves"] = rng.integers(1, 6, n_players)
            for c in DETAIL_COLS:
                d[c] = (d["overall"] + rng.normal(0, 10, n_players)).clip(10, 99).round()
            for c in ["pace", "shooting", "passing", "dribbling", "defending", "physic"]:
                d[c] = (d["overall"] + rng.normal(0, 8, n_players)).clip(20, 99).round()
            d.loc[d["player_positions"] == "GK", ["pace", "shooting"]] = np.nan
            d["long_name"] = d["short_name"]
            d["nationality_name"] = "Nowhere"
            d["club_position"] = "SUB"
            d["preferred_foot"] = "Right"
            d["work_rate"] = "Medium/Medium"
            d["club_loaned_from"] = np.nan
            rows.append(d.drop(columns=["age0", "talent"]))
    df = pd.concat(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "male_players.csv", index=False)
    print(f"synthetic rows: {len(df):,} -> {out_dir / 'male_players.csv'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
