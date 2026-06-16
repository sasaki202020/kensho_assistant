# Boat Race AI Handoff

## Scope

`boat_race_ai` is a CLI-first daily boat-race prediction and settlement system.
It does not place bets, click purchase/send buttons, or send data externally.

## Current Operating Flow

Run from `boat_race_ai/`.

```powershell
py -3.13 daily_run.py --date YYYY-MM-DD --phase morning
py -3.13 daily_run.py --date YYYY-MM-DD --phase odds --force-refresh
py -3.13 daily_run.py --date YYYY-MM-DD --phase night --bankroll-yen 10000
py -3.13 daily_status.py --date YYYY-MM-DD
```

Standard windows:

- Morning prediction: after entries are available.
- Odds refresh: after 18:00 JST.
- Night settlement: after 21:30 JST.

## 2026-06-14 Status

- Morning predictions: 144 races / 864 rows.
- Night settlement: 142 / 144 races settled.
- Unavailable races:
  - `20260614_19_11`: `result_table_not_found`
  - `20260614_19_12`: `result_unpublished`
- Current decision: `paper_trade_only`
- Live betting allowed: `False`
- Candidate conditions: 0
- Main blocker: `min_days`

Daily strategy results for 2026-06-14:

- `top1_win`: hit rate 57.0%, ROI 97.61%, bets 142
- `top2_win`: hit rate 75.4%, ROI 76.44%, bets 284
- `value_filter`: bets 0 because pre-race expected value was unavailable

## 2026-06-16 Morning Status

- Morning predictions were generated after a long official-site fetch.
- Coverage: 12 courses / 144 races / 864 rows.
- Complete races: 144 / 144.
- Missing racer names: 0.
- Missing grades: 0.
- Missing win odds: 371 rows.
- `win_odds=0.0` from official odds pages is treated as unavailable, not as a real odds value.
- Next action at 14:42 JST: wait for official odds refresh after 18:00.

## Important Fixes In This Handoff

- Result parser extracts winner single-win payout from official result pages as `win_odds = payout_yen / 100`.
- Old result CSV caches are reparsed from cached HTML when `win_odds` is missing.
- Settlement can use result-side winner payout only when saved prediction odds are missing.
- `value_filter` now uses saved pre-race `expected_value` only. It must not recompute value from post-race result payout odds.
- Profitability analysis counts losing settled bets even when losing-row odds are missing, while payout remains zero.
- Official odds values of `0.0` are normalized to missing because they represent unavailable odds, not valid odds.

## Validation

Last targeted checks:

```powershell
py -3.13 -m pytest tests/test_daily_ops.py tests/test_real_data_fetcher.py tests/test_profitability_analysis.py -q
py -3.13 -m pytest tests/test_daily_status.py tests/test_daily_verify.py -q
py -3.13 daily_verify.py --date 2026-06-14 --stage night
```

Observed results:

- `21 passed`
- `10 passed`
- `daily_verify --stage night`: `status=ok`

## Next Work

1. Run the same daily flow for 2026-06-15.
2. Confirm whether pre-race odds can be parsed from the current official odds page format.
3. Keep `value_filter` as shadow-only until real pre-race odds coverage is stable.
4. Do not enable live betting until profitability gates pass across enough distinct days.
