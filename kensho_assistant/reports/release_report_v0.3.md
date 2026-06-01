# Release report v0.3-beta
- version: v0.3-beta
- release_status: OK
- collected_count: 122
- analyzed_count: 122
- resolved_count: 45
- inspected_count: 36
- ready_for_fill_count: 0
- review_only_count: 12
- landing_page_count: 4
- search_only_count: 5
- low_confidence_count: 10
- submitted_count: 0
- final_test_note: 本番profile相当テスト 1 件実施 / 応募送信なし
- auto_scan: OK
- pytest_status: run separately
- doctor_status: run separately
- profile_store: profile.enc
- privacy_check_status: manual log scan required

## known limitations
- v0.3-beta でも本番送信を推奨しない
- REVIEW_ONLY は人間確認が必要
- 年齢・同意・メルマガ・任意項目は自動入力しない

## next steps
- READY_FOR_FILL 候補を増やす
- REVIEW_ONLY の手動確認 UX を改善する
- 本番送信は必ず人間確認後に判断する

## safety
- 本番送信は人間確認が必要
