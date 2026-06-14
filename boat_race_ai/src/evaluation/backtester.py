from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass
class BoatRaceBacktester:
    stake_per_bet: float = 100.0

    def evaluate(self, frame: pd.DataFrame, probability_column: str = "pred_prob") -> tuple[pd.DataFrame, pd.DataFrame]:
        if frame.empty:
            return pd.DataFrame(), pd.DataFrame()
        required = {"race_id", "lane", "win", "win_odds", probability_column}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        strategies: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
            "top1_win": self._top_n_strategy(1, probability_column),
            "top2_win": self._top_n_strategy(2, probability_column),
            "value_filter": self._value_strategy(probability_column),
        }
        summary_rows = []
        detail_rows = []
        for strategy_name, selector in strategies.items():
            total_races = 0
            hit_races = 0
            total_bets = 0
            total_stake = 0.0
            total_payout = 0.0
            for race_id, race_frame in frame.groupby("race_id", sort=False):
                total_races += 1
                bets = selector(race_frame).copy()
                if bets.empty:
                    detail_rows.append(
                        {
                            "strategy": strategy_name,
                            "race_id": race_id,
                            "bets": 0,
                            "stake": 0.0,
                            "payout": 0.0,
                            "hit": 0,
                        }
                    )
                    continue
                bets["stake"] = self.stake_per_bet
                bets["payout"] = np.where(bets["win"].astype(int) == 1, bets["win_odds"].astype(float) * self.stake_per_bet, 0.0)
                stake = float(bets["stake"].sum())
                payout = float(bets["payout"].sum())
                hit = int((bets["win"].astype(int) == 1).any())
                total_bets += len(bets)
                total_stake += stake
                total_payout += payout
                hit_races += hit
                detail_rows.append(
                    {
                        "strategy": strategy_name,
                        "race_id": race_id,
                        "bets": len(bets),
                        "stake": stake,
                        "payout": payout,
                        "hit": hit,
                    }
                )
            summary_rows.append(
                {
                    "strategy": strategy_name,
                    "races": total_races,
                    "race_hit_rate": (hit_races / total_races) if total_races else 0.0,
                    "bets": total_bets,
                    "avg_bets_per_race": (total_bets / total_races) if total_races else 0.0,
                    "stake": total_stake,
                    "payout": total_payout,
                    "roi_pct": (total_payout / total_stake * 100.0) if total_stake else 0.0,
                    "net_profit": total_payout - total_stake,
                }
            )
        return pd.DataFrame(summary_rows), pd.DataFrame(detail_rows)

    def _top_n_strategy(self, n: int, probability_column: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
        def selector(race_frame: pd.DataFrame) -> pd.DataFrame:
            return race_frame.sort_values(probability_column, ascending=False).head(n)

        return selector

    def _value_strategy(self, probability_column: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
        def selector(race_frame: pd.DataFrame) -> pd.DataFrame:
            ranked = race_frame.sort_values(probability_column, ascending=False).copy()
            if "expected_value" in ranked.columns:
                expected_value = pd.to_numeric(ranked["expected_value"], errors="coerce")
            else:
                expected_value = ranked[probability_column].astype(float) * ranked["win_odds"].astype(float)
            ranked["_value_expected_value"] = expected_value
            return ranked.loc[ranked["_value_expected_value"] >= 1.0]

        return selector
