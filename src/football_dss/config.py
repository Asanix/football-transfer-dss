"""Project-wide settings: paths, target club, tactical model, budget assumptions.

Anything marked ASSUMPTION is our own estimate, not a fact from the data.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = Path(os.environ.get("FOOTBALL_DATA_RAW", ROOT / "data" / "raw"))
DATA_PROCESSED = Path(os.environ.get("FOOTBALL_DATA_PROCESSED", ROOT / "data" / "processed"))
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
OUTPUTS = ROOT / "outputs"

KAGGLE_DATASET = "stefanoleone992/fifa-23-complete-player-dataset"
RAW_FILE = "male_players.csv"
PLAYERS_PARQUET = DATA_PROCESSED / "players.parquet"

# FIFA versions used. FIFA 23 = snapshot of the 2022/23 season.
FIRST_VERSION = 17
LAST_VERSION = 23

TARGET_CLUB = os.environ.get("FOOTBALL_CLUB", "Real Madrid CF")

# ---- Tactical model: 4-3-3, possession + high press -------------------------
# Number of starters and the minimum squad depth per position group.
FORMATION = {"GK": 1, "CB": 2, "FB": 2, "DM": 1, "CM": 2, "AM": 0, "W": 2, "ST": 1}
MIN_DEPTH = {"GK": 3, "CB": 4, "FB": 4, "DM": 2, "CM": 3, "AM": 1, "W": 4, "ST": 2}

# Role profiles: which attributes matter for each group in OUR style.
# Weights are normalised inside features.role_fit(), so only ratios matter.
ROLE_WEIGHTS = {
    "GK": {"goalkeeping_reflexes": 3, "goalkeeping_diving": 2, "goalkeeping_positioning": 2,
           "goalkeeping_handling": 1, "goalkeeping_kicking": 2, "skill_long_passing": 1},
    "CB": {"defending_standing_tackle": 3, "defending_marking_awareness": 3, "mentality_interceptions": 2,
           "power_jumping": 1, "power_strength": 1, "movement_sprint_speed": 2,
           "attacking_short_passing": 2, "skill_long_passing": 1, "mentality_composure": 1},
    "FB": {"movement_sprint_speed": 3, "power_stamina": 3, "attacking_crossing": 2,
           "defending_standing_tackle": 2, "mentality_interceptions": 1, "attacking_short_passing": 1,
           "skill_dribbling": 1},
    "DM": {"mentality_interceptions": 3, "defending_standing_tackle": 2, "attacking_short_passing": 3,
           "skill_long_passing": 2, "mentality_composure": 2, "power_stamina": 2, "mentality_aggression": 1},
    "CM": {"attacking_short_passing": 3, "mentality_vision": 2, "skill_ball_control": 2,
           "power_stamina": 3, "mentality_composure": 1, "mentality_interceptions": 1,
           "power_long_shots": 1, "skill_dribbling": 1},
    "AM": {"mentality_vision": 3, "attacking_short_passing": 2, "skill_dribbling": 2,
           "skill_ball_control": 2, "power_long_shots": 1, "attacking_finishing": 1, "movement_agility": 1},
    "W":  {"movement_acceleration": 3, "movement_sprint_speed": 2, "skill_dribbling": 3,
           "attacking_finishing": 2, "attacking_crossing": 1, "movement_agility": 1,
           "power_stamina": 1, "mentality_positioning": 1},
    "ST": {"attacking_finishing": 3, "mentality_positioning": 3, "movement_acceleration": 2,
           "attacking_heading_accuracy": 1, "power_shot_power": 1, "mentality_composure": 1,
           "power_stamina": 1, "mentality_aggression": 1},
}

# ---- Budget (ASSUMPTIONS) ----------------------------------------------------
TRANSFER_BUDGET_EUR = float(os.environ.get("FOOTBALL_BUDGET", 120_000_000))
WAGE_BUDGET_EUR_WEEK = float(os.environ.get("FOOTBALL_WAGE_BUDGET", 600_000))  # extra weekly wages allowed
FEE_PREMIUM = 1.20     # real fee ~= FIFA value * premium (clubs rarely sell at "market value")
SALE_DISCOUNT = 0.85   # we usually sell below value
MAX_SIGNINGS = 4

RANDOM_STATE = 42
MIN_OVERALL_POOL = 65  # ignore players below this for scouting (not first-team level for a top club)

LLM_MODEL = "claude-opus-5-5"

for _p in (DATA_RAW, DATA_PROCESSED, FIGURES, OUTPUTS):
    _p.mkdir(parents=True, exist_ok=True)
