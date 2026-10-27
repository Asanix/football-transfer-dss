"""Playing-style clusters and 'cheaper twin' search, done separately per position group."""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from . import config
from .data import DETAIL_COLS

GK_COLS = [c for c in DETAIL_COLS if c.startswith("goalkeeping")]
OUTFIELD_COLS = [c for c in DETAIL_COLS if not c.startswith("goalkeeping")]


def style_cols(group: str):
    return GK_COLS + ["skill_long_passing", "movement_reactions"] if group == "GK" else OUTFIELD_COLS


def style_vectors(df: pd.DataFrame, group: str) -> np.ndarray:
    """Style = SHAPE of the attribute profile, not its level: each player's attributes
    minus his own mean. So a 70-rated and an 85-rated player with the same profile are 'twins'."""
    a = df[style_cols(group)].to_numpy(dtype=float)
    return a - a.mean(axis=1, keepdims=True)


def cluster_group(df: pd.DataFrame, group: str, k_range=range(3, 7)):
    sub = df[df["pos_group"] == group]
    X = StandardScaler().fit_transform(style_vectors(sub, group))
    sample = np.random.default_rng(config.RANDOM_STATE).choice(len(X), min(len(X), 5000), replace=False)
    scores = {}
    for k in k_range:
        if len(X) <= k:
            continue
        labels = KMeans(k, n_init=10, random_state=config.RANDOM_STATE).fit_predict(X)
        scores[k] = silhouette_score(X[sample], labels[sample])
    best_k = max(scores, key=scores.get)
    km = KMeans(best_k, n_init=10, random_state=config.RANDOM_STATE).fit(X)
    centers = pd.DataFrame(km.cluster_centers_, columns=style_cols(group))
    names = {i: "high " + " / ".join(c.split("_", 1)[1] for c in row.nlargest(2).index)
             for i, row in centers.iterrows()}
    labels = pd.Series(km.labels_, index=sub.index).map(lambda i: f"{group}-{i}: {names[i]}")
    return labels, scores


def add_clusters(df: pd.DataFrame):
    df = df.copy()
    df["style_cluster"] = None
    silhouettes = {}
    for g in config.FORMATION:
        if (df["pos_group"] == g).sum() < 20:
            continue
        labels, scores = cluster_group(df, g)
        df.loc[labels.index, "style_cluster"] = labels
        silhouettes[g] = scores
    return df, silhouettes


def similar_players(df: pd.DataFrame, player_id: int, n: int = 10, max_value: float | None = None,
                    max_age: int | None = None) -> pd.DataFrame:
    ref = df[df["player_id"] == player_id].iloc[0]
    pool = df[(df["pos_group"] == ref["pos_group"]) & (df["player_id"] != player_id)]
    if max_value is not None:
        pool = pool[pool["value_eur"] <= max_value]
    if max_age is not None:
        pool = pool[pool["age"] <= max_age]
    if pool.empty:
        return pool
    scaler = StandardScaler().fit(style_vectors(df[df["pos_group"] == ref["pos_group"]], ref["pos_group"]))
    Xp = scaler.transform(style_vectors(pool, ref["pos_group"]))
    xr = scaler.transform(style_vectors(ref.to_frame().T, ref["pos_group"]))
    nn = NearestNeighbors(n_neighbors=min(n, len(pool)), metric="cosine").fit(Xp)
    dist, idx = nn.kneighbors(xr)
    res = pool.iloc[idx[0]].copy()
    res["style_similarity"] = 1 - dist[0]
    return res


def self_retrieval_check(prev: pd.DataFrame, cur: pd.DataFrame, k: int = 5, sample: int = 1000) -> pd.DataFrame:
    """Validation of the similarity metric: a player's style vector from season t should find
    the SAME player among nearest neighbours in season t+1. Random guessing ~ k / pool size."""
    rows = []
    rng = np.random.default_rng(config.RANDOM_STATE)
    for g in config.FORMATION:
        c = cur[cur["pos_group"] == g]
        p = prev[(prev["pos_group"] == g) & prev["player_id"].isin(c["player_id"])]
        if len(p) < 50:
            continue
        p = p.iloc[rng.choice(len(p), min(sample, len(p)), replace=False)]
        scaler = StandardScaler().fit(style_vectors(c, g))
        nn = NearestNeighbors(n_neighbors=k, metric="cosine").fit(scaler.transform(style_vectors(c, g)))
        _, idx = nn.kneighbors(scaler.transform(style_vectors(p, g)))
        found = c["player_id"].to_numpy()[idx]
        hit = (found == p["player_id"].to_numpy()[:, None]).any(axis=1).mean()
        rows.append({"group": g, f"top-{k} hit rate": hit, "random": k / len(c), "pool": len(c)})
    return pd.DataFrame(rows)
