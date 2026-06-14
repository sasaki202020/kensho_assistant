from __future__ import annotations

from src.data_processing.dummy_generator import DummyDataGenerator
from src.data_processing.preprocessor import BoatRacePreprocessor
from src.features.feature_engineer import BoatRaceFeatureEngineer
from src.models.prediction_system import PredictionSystem


def test_prediction_system_trains_and_predicts() -> None:
    raw = DummyDataGenerator(seed=9).generate(n_races=12, start_date="2026-06-01", course_ids=["07"])
    raw = raw.sort_values(["race_date", "race_id", "lane"]).reset_index(drop=True)
    train_races = raw["race_id"].drop_duplicates().tolist()[:8]
    test_races = raw["race_id"].drop_duplicates().tolist()[8:]
    preprocessor = BoatRacePreprocessor().fit(raw[raw["race_id"].isin(train_races)])
    processed = preprocessor.transform(raw)
    engineered = BoatRaceFeatureEngineer().transform(processed)
    train_frame = engineered[engineered["race_id"].isin(train_races)].copy()
    test_frame = engineered[engineered["race_id"].isin(test_races)].copy()
    model = PredictionSystem(random_state=3, xgb_estimators=20, lgbm_estimators=20, rf_estimators=20)
    model.fit(train_frame)
    predicted = model.predict_frame(test_frame)
    assert predicted["pred_prob"].between(0.0, 1.0).all()
    assert len(predicted) == len(test_frame)
