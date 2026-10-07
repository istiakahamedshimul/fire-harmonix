"""Reproducible FIRE-HARMONIX feasibility benchmarks.

Artifacts are not used by the dashboard and are not production models.
"""
from __future__ import annotations

import csv, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT, SEED = ROOT / "data/fire_samples.csv", ROOT / "models", 42


def daily_rows():
    groups = defaultdict(list)
    with DATA.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle): groups[row["acq_date"]].append(row)
    result = []
    for date, rows in sorted(groups.items()):
        vals = lambda key: np.array([float(r[key]) for r in rows])
        dt = datetime.strptime(date, "%Y-%m-%d")
        result.append({"date": date, "count": len(rows), "mean_frp": vals("frp").mean(),
          "max_frp": vals("frp").max(), "mean_brightness": vals("brightness").mean(),
          "max_brightness": vals("brightness").max(), "day_count": sum(r["daynight"] == "D" for r in rows),
          "night_count": sum(r["daynight"] == "N" for r in rows),
          "mean_agreement": vals("sensor_agreement").mean(), "mean_hfai": vals("hfai").mean(),
          "max_hfai": vals("hfai").max(), "month": dt.month, "day_of_year": dt.timetuple().tm_yday})
    return result


def feature_rows(source):
    activity = [r["mean_hfai"] for r in source]
    rows = []
    for i in range(14, len(source) - 1):
        r = dict(source[i]); history = activity
        r.update(hfai_lag_1=history[i-1], hfai_lag_3=history[i-3], hfai_lag_7=history[i-7],
                 rolling_mean_7=np.mean(history[i-7:i]), rolling_mean_14=np.mean(history[i-14:i]),
                 rolling_std_7=np.std(history[i-7:i]), target=history[i+1])
        rows.append(r)
    return rows


def scores(actual, predicted):
    return {"mae": round(float(mean_absolute_error(actual, predicted)), 6),
            "rmse": round(math.sqrt(float(mean_squared_error(actual, predicted))), 6),
            "r2": round(float(r2_score(actual, predicted)), 6)}


def main():
    OUT.mkdir(exist_ok=True)
    source, rows = daily_rows(), None
    rows = feature_rows(source)
    features = ["count","mean_frp","max_frp","mean_brightness","max_brightness","day_count",
      "night_count","mean_agreement","mean_hfai","max_hfai","hfai_lag_1","hfai_lag_3",
      "hfai_lag_7","rolling_mean_7","rolling_mean_14","rolling_std_7","month","day_of_year"]
    X = np.array([[float(r[f]) for f in features] for r in rows]); y = np.array([r["target"] for r in rows])
    train_end, val_end = int(len(rows)*.70), int(len(rows)*.85)
    X_train, y_train = X[:train_end], y[:train_end]
    X_val, y_val = X[train_end:val_end], y[train_end:val_end]
    X_test, y_test = X[val_end:], y[val_end:]
    candidates = [
      {"n_estimators":80,"max_depth":2,"learning_rate":.03,"subsample":.9,"colsample_bytree":.9},
      {"n_estimators":120,"max_depth":2,"learning_rate":.05,"subsample":.9,"colsample_bytree":1.0},
      {"n_estimators":120,"max_depth":3,"learning_rate":.03,"subsample":.8,"colsample_bytree":.9},
      {"n_estimators":180,"max_depth":3,"learning_rate":.02,"subsample":.9,"colsample_bytree":.9}]
    trials, best = [], None
    for params in candidates:
        model = XGBRegressor(objective="reg:squarederror", random_state=SEED, n_jobs=1, **params)
        model.fit(X_train, y_train); mae = float(mean_absolute_error(y_val, model.predict(X_val)))
        trials.append({"parameters":params,"validation_mae":round(mae,6)})
        if best is None or mae < best[0]: best = (mae, params)
    model = XGBRegressor(objective="reg:squarederror", random_state=SEED, n_jobs=1, **best[1])
    model.fit(X[:val_end], y[:val_end]); prediction = model.predict(X_test)
    model.save_model(OUT / "xgboost_fire_activity_v0.1.json")
    anomaly = IsolationForest(n_estimators=200, contamination=.10, random_state=SEED, n_jobs=1).fit(X_train)
    labels, anomaly_score = anomaly.predict(X_test), -anomaly.score_samples(X_test)
    joblib.dump(anomaly, OUT / "isolation_forest_hfai_v0.1.joblib")
    report = {"status":"feasibility benchmark; not production validation", "random_seed":SEED,
      "daily_records_before_lags":len(source), "model_rows_after_lags":len(rows),
      "split":{"train":train_end,"validation":val_end-train_end,"test":len(rows)-val_end},
      "date_ranges":{"train":[rows[0]["date"],rows[train_end-1]["date"]],
        "validation":[rows[train_end]["date"],rows[val_end-1]["date"]],"test":[rows[val_end]["date"],rows[-1]["date"]]},
      "xgboost":{"selected_parameters":best[1],"validation_mae":round(best[0],6),"test":scores(y_test,prediction),"tuning_candidates":trials},
      "baselines":{"persistence":scores(y_test,X_test[:,features.index("mean_hfai")]),
        "historical_mean":scores(y_test,np.full_like(y_test,y_train.mean()))},
      "isolation_forest":{"test_anomaly_count":int((labels==-1).sum()),"test_anomaly_rate":round(float((labels==-1).mean()),6),
        "test_score_min":round(float(anomaly_score.min()),6),"test_score_max":round(float(anomaly_score.max()),6)}}
    (OUT/"metrics.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    manifest = {"version":"0.1","feature_order":features,"target":"next_day_mean_hfai",
      "models":{"anomaly":"isolation_forest_hfai_v0.1.joblib","forecast":"xgboost_fire_activity_v0.1.json"},
      "warning":"Feasibility artifacts trained on the bundled demonstration sample; not for operational use."}
    (OUT/"feature_manifest_v0.1.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__": main()
