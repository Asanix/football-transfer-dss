"""ML models, each validated on a TIME split against a simple baseline.

1. Fair value  : log(value_eur) from attributes.   train <= FIFA 22, test = FIFA 23
2. Growth      : overall change next season.        train pairs <= (21->22), test (22->23)
3. Bust risk   : P(overall drops >= 2 next season). same split as growth

Deliberately excluded features (leakage / circularity):
- release_clause_eur : computed by EA directly from value
- wage_eur           : set together with value, would make "fair value" ~ wage lookup
- anything from version t+1 for growth/bust models
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score, brier_score_loss
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config
from .features import model_matrix

TEST_VERSION = config.LAST_VERSION


def _age_bucket(age):
    return pd.cut(age, [0, 20, 23, 26, 29, 32, 50], labels=False)


# ---------------------------------------------------------------- fair value
def _grid_baseline(train, test, target):
    """Baseline = median target in the same (overall, age bucket) cell."""
    key_tr = list(zip(train["overall"].round(), _age_bucket(train["age"])))
    key_te = list(zip(test["overall"].round(), _age_bucket(test["age"])))
    table = pd.Series(train[target].values, index=pd.MultiIndex.from_tuples(key_tr)).groupby(level=[0, 1]).median()
    pred = pd.Series(key_te).map(table.to_dict()).astype(float)
    return pred.fillna(train[target].median()).values


def value_model(df: pd.DataFrame):
    data = df.dropna(subset=["log_value"])
    train = data[data["fifa_version"] < TEST_VERSION]
    test = data[data["fifa_version"] == TEST_VERSION]
    Xtr, Xte = model_matrix(train), model_matrix(test)
    ytr, yte = train["log_value"], test["log_value"]

    hgb = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, random_state=config.RANDOM_STATE)
    hgb.fit(Xtr, ytr)
    lin = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LinearRegression()).fit(Xtr, ytr)

    preds = {"baseline: median(overall, age)": _grid_baseline(train, test, "log_value"),
             "linear regression": lin.predict(Xte),
             "gradient boosting": hgb.predict(Xte)}
    metrics = pd.DataFrame([{
        "model": name,
        "MAE log-value": mean_absolute_error(yte, p),
        "R2": r2_score(yte, p),
        "median abs % error": float(np.median(np.abs(np.expm1(p) / np.expm1(yte) - 1))),
    } for name, p in preds.items()])

    return hgb, metrics


def fair_value_oof(df: pd.DataFrame, version: int) -> pd.DataFrame:
    """Fair value inside one season, out-of-fold: otherwise every player's own
    price leaks into his "fair" price."""
    cur = df[df["fifa_version"] == version].copy()
    has_v = cur["log_value"].notna()
    oof = cross_val_predict(
        HistGradientBoostingRegressor(max_iter=400, learning_rate=0.06, random_state=config.RANDOM_STATE),
        model_matrix(cur[has_v]), cur.loc[has_v, "log_value"],
        cv=KFold(5, shuffle=True, random_state=config.RANDOM_STATE))
    cur["fair_value"] = np.nan
    cur.loc[has_v, "fair_value"] = np.expm1(oof)
    cur["value_gap"] = cur["fair_value"] / cur["value_eur"] - 1
    return cur[["player_id", "fair_value", "value_gap"]]


# ---------------------------------------------------------------- growth & bust
def growth_models(df_pairs: pd.DataFrame):
    """df_pairs: output of features.add_next_season (rows without next season dropped here)."""
    data = df_pairs.dropna(subset=["delta_overall"])
    train = data[data["fifa_version"] < TEST_VERSION - 1]
    test = data[data["fifa_version"] == TEST_VERSION - 1]
    Xtr, Xte = model_matrix(train), model_matrix(test)

    reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=config.RANDOM_STATE)
    reg.fit(Xtr, train["delta_overall"])
    base = train.groupby(_age_bucket(train["age"]))["delta_overall"].mean()
    base_pred = _age_bucket(test["age"]).map(base).fillna(train["delta_overall"].mean())
    growth_metrics = pd.DataFrame([
        {"model": "baseline: mean delta by age", "MAE": mean_absolute_error(test["delta_overall"], base_pred),
         "R2": r2_score(test["delta_overall"], base_pred)},
        {"model": "gradient boosting", "MAE": mean_absolute_error(test["delta_overall"], reg.predict(Xte)),
         "R2": r2_score(test["delta_overall"], reg.predict(Xte))},
    ])

    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=config.RANDOM_STATE)
    clf.fit(Xtr, train["bust"].astype(int))
    logit = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          LogisticRegression(max_iter=2000)).fit(Xtr[["age", "overall"]], train["bust"].astype(int))
    y = test["bust"].astype(int)
    p_hgb = clf.predict_proba(Xte)[:, 1]
    p_base = logit.predict_proba(Xte[["age", "overall"]])[:, 1]
    risk_metrics = pd.DataFrame([
        {"model": "baseline: logistic(age, overall)", "ROC-AUC": roc_auc_score(y, p_base), "Brier": brier_score_loss(y, p_base)},
        {"model": "gradient boosting", "ROC-AUC": roc_auc_score(y, p_hgb), "Brier": brier_score_loss(y, p_hgb)},
    ])
    risk_metrics["bust rate (test)"] = y.mean()
    importance = _top_features(reg, Xte, test["delta_overall"])

    # final models for the live season: refit on ALL known pairs (incl. 22->23)
    Xall = model_matrix(data)
    reg_full = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=config.RANDOM_STATE)
    reg_full.fit(Xall, data["delta_overall"])
    clf_full = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=config.RANDOM_STATE)
    clf_full.fit(Xall, data["bust"].astype(int))
    return {"reg_test": reg, "clf_test": clf, "reg_full": reg_full, "clf_full": clf_full,
            "growth_metrics": growth_metrics, "risk_metrics": risk_metrics, "importance": importance}


def _top_features(model, X, y, n=12):
    from sklearn.inspection import permutation_importance
    idx = np.random.default_rng(config.RANDOM_STATE).choice(len(X), min(len(X), 5000), replace=False)
    r = permutation_importance(model, X.iloc[idx], y.iloc[idx], n_repeats=5, random_state=config.RANDOM_STATE)
    return (pd.DataFrame({"feature": X.columns, "importance": r.importances_mean})
            .sort_values("importance", ascending=False).head(n))


def predict_future(df_cur: pd.DataFrame, reg, clf) -> pd.DataFrame:
    X = model_matrix(df_cur)
    out = df_cur[["player_id"]].copy()
    out["pred_delta"] = reg.predict(X)
    out["overall_next_pred"] = df_cur["overall"] + out["pred_delta"]
    out["bust_risk"] = clf.predict_proba(X)[:, 1]
    return out
