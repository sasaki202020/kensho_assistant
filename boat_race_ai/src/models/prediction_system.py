from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier


@dataclass
class AverageMetaModel:
    """Fallback meta model that averages base probabilities."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> "AverageMetaModel":
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        probs = np.asarray(X, dtype=float)
        if probs.ndim == 1:
            probs = probs.reshape(-1, 1)
        mean_probs = probs.mean(axis=1)
        return np.column_stack([1.0 - mean_probs, mean_probs])


@dataclass
class PredictionSystem:
    random_state: int = 42
    xgb_estimators: int = 100
    lgbm_estimators: int = 140
    rf_estimators: int = 180
    target_column: str = "win"
    group_column: str = "race_id"
    date_column: str = "race_date"
    feature_columns_: list[str] = field(default_factory=list)
    base_models_: dict[str, Any] = field(default_factory=dict)
    meta_model_: Any | None = None
    fitted_: bool = False

    def _make_base_models(self) -> dict[str, Any]:
        return {
            "xgb": XGBClassifier(
                n_estimators=self.xgb_estimators,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.9,
                colsample_bytree=0.85,
                reg_lambda=1.0,
                min_child_weight=1.0,
                objective="binary:logistic",
                eval_metric="logloss",
                tree_method="hist",
                random_state=self.random_state,
                n_jobs=1,
            ),
            "lgbm": LGBMClassifier(
                n_estimators=self.lgbm_estimators,
                learning_rate=0.05,
                num_leaves=31,
                subsample=0.9,
                colsample_bytree=0.85,
                min_child_samples=5,
                random_state=self.random_state,
                n_jobs=1,
            ),
            "rf": RandomForestClassifier(
                n_estimators=self.rf_estimators,
                max_depth=7,
                min_samples_leaf=3,
                random_state=self.random_state,
                n_jobs=-1,
            ),
        }

    def _feature_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not self.feature_columns_:
            self.feature_columns_ = [column for column in frame.columns if column.startswith("feat_")]
        missing = [column for column in self.feature_columns_ if column not in frame.columns]
        if missing:
            raise ValueError(f"Missing feature columns: {missing[:8]}")
        return frame[self.feature_columns_].replace([np.inf, -np.inf], np.nan).fillna(0.0)

    def _race_order(self, frame: pd.DataFrame) -> list[str]:
        order = (
            frame[[self.group_column, self.date_column]]
            .drop_duplicates()
            .sort_values([self.date_column, self.group_column])
        )
        return order[self.group_column].astype(str).tolist()

    def _build_time_folds(self, race_order: list[str]) -> list[tuple[list[str], list[str]]]:
        n_races = len(race_order)
        if n_races < 4:
            return []
        n_folds = min(4, max(1, n_races // 4))
        folds: list[tuple[list[str], list[str]]] = []
        for fold in range(n_folds):
            train_end = max(1, int(n_races * (fold + 1) / (n_folds + 1)))
            valid_end = max(train_end + 1, int(n_races * (fold + 2) / (n_folds + 1)))
            valid_end = min(valid_end, n_races)
            train_races = race_order[:train_end]
            valid_races = race_order[train_end:valid_end]
            if train_races and valid_races:
                folds.append((train_races, valid_races))
        return folds

    def fit(self, frame: pd.DataFrame) -> "PredictionSystem":
        if frame.empty:
            raise ValueError("Cannot fit the model on an empty frame.")
        data = frame.copy()
        data[self.date_column] = pd.to_datetime(data[self.date_column], errors="coerce")
        if self.target_column not in data.columns:
            raise ValueError(f"Missing target column: {self.target_column}")

        self.feature_columns_ = [column for column in data.columns if column.startswith("feat_")]
        X = self._feature_frame(data)
        y = pd.to_numeric(data[self.target_column], errors="coerce").fillna(0).astype(int).to_numpy()
        race_order = self._race_order(data)
        folds = self._build_time_folds(race_order)
        base_names = list(self._make_base_models().keys())
        oof = pd.DataFrame(index=data.index, columns=base_names, dtype=float)

        for train_races, valid_races in folds:
            train_mask = data[self.group_column].astype(str).isin(train_races)
            valid_mask = data[self.group_column].astype(str).isin(valid_races)
            if not train_mask.any() or not valid_mask.any():
                continue
            y_train = y[train_mask.to_numpy()]
            if len(np.unique(y_train)) < 2:
                continue
            for name, model in self._make_base_models().items():
                fitted_model = self._safe_fit_model(model, X.loc[train_mask], y_train)
                oof.loc[valid_mask, name] = self._predict_model_proba(fitted_model, X.loc[valid_mask])

        meta_rows = oof.dropna()
        if len(meta_rows) >= 8 and len(np.unique(y[meta_rows.index.to_numpy()])) >= 2:
            meta_model: Any = LogisticRegression(max_iter=1000, random_state=self.random_state)
            meta_model.fit(meta_rows.to_numpy(), y[meta_rows.index.to_numpy()])
        else:
            meta_model = AverageMetaModel().fit(np.zeros((len(data), len(base_names))), y)

        self.base_models_ = {}
        for name, model in self._make_base_models().items():
            self.base_models_[name] = self._safe_fit_model(model, X, y)
        self.meta_model_ = meta_model
        self.fitted_ = True
        return self

    def _safe_fit_model(self, model: Any, X: pd.DataFrame, y: np.ndarray) -> Any:
        try:
            model.fit(X, y)
            return model
        except Exception:
            fallback = DummyClassifier(strategy="prior")
            fallback.fit(X, y)
            return fallback

    def _predict_model_proba(self, model: Any, X: pd.DataFrame) -> np.ndarray:
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(X)
            if isinstance(proba, list):
                proba = np.asarray(proba)
            if proba.ndim == 2 and proba.shape[1] > 1:
                return proba[:, 1]
            return np.asarray(proba).reshape(-1)
        if hasattr(model, "decision_function"):
            scores = model.decision_function(X)
            scores = np.asarray(scores, dtype=float)
            return 1.0 / (1.0 + np.exp(-scores))
        return np.full(len(X), 0.5, dtype=float)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        if not self.fitted_:
            raise RuntimeError("PredictionSystem must be fitted before predicting.")
        X = self._feature_frame(frame)
        base_probs = np.column_stack([self._predict_model_proba(model, X) for model in self.base_models_.values()])
        if hasattr(self.meta_model_, "predict_proba"):
            meta_probs = self.meta_model_.predict_proba(base_probs)
            if meta_probs.ndim == 2 and meta_probs.shape[1] > 1:
                return meta_probs[:, 1]
            return np.asarray(meta_probs).reshape(-1)
        if hasattr(self.meta_model_, "predict"):
            return np.asarray(self.meta_model_.predict(base_probs), dtype=float)
        return base_probs.mean(axis=1)

    def predict_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        output = frame.copy()
        output["pred_prob"] = self.predict_proba(frame)
        output["pred_rank"] = output.groupby(self.group_column)["pred_prob"].rank(method="first", ascending=False)
        return output

    def save(self, path: str | Path) -> None:
        joblib.dump(self, Path(path))

    @classmethod
    def load(cls, path: str | Path) -> "PredictionSystem":
        return joblib.load(Path(path))
