---
name: pension-video-factory
description: Use when creating or modifying this project's pension/giveaway explanation YouTube videos, including scripts, slides, narration, subtitles, thumbnails, or the pension-video-maker pipeline.
metadata:
  short-description: Safe pension video generation for this project
---

# pension-video-factory

Use this skill for:
- pension explanation videos
- benefit / allowance explanation videos
- senior-friendly money explainer videos
- YouTube script, slide, narration, subtitle, thumbnail generation
- `pension-video-maker` maintenance or changes
- final-check users who only verify the last package

## Rules

1. Verify pension and benefit amounts against official sources.
2. If no official source is available, do not invent numbers.
3. Avoid absolute or hype language such as "everyone gets", "always wins", or "you lose if you do not apply".
4. Produce `facts_check.md` for every video.
5. Produce `warnings.md` for every video.
6. Keep text large, explanations short, and the tone calm for older viewers.
7. Prioritize trust over flashy motion or overly complex visuals.
8. Do not do YouTube auto-posting in the first version.
9. Always output `video.mp4`, `thumbnail.png`, and `youtube_meta.txt`.
10. The user does only the final check; Codex should finish the pre-publish package.
11. Always create `publish_package/` and `publish_ready_report.md`.
12. After generation, report the command used and the output files.
13. Filmora is optional; if it is unstable or unavailable, do not stop and finish with Python + FFmpeg.
14. Treat `publish_package/` as the final delivery bundle and keep the pre-publish checks inside it.
15. Use proven pension-video TTP patterns without copying another video's contents.
16. Start with a small expectation shift, then explain who the video is for and what viewers can check within the first minute.
17. Choose one video type for each run: `判断基準型`, `チェックリスト型`, or `最新改正型`.
18. Use thumbnail text with at most three lines, large letters, and safe hooks such as `50歳以上`, `年金`, `確認`, `見落とし`, or `判断基準`.
19. Prefer title hooks such as `保存版`, `必見`, `最新`, `4選`, and `判断基準`.
20. Treat `大損`, `国が隠す`, and `全員もらえる` as warning phrases.
21. Record the selected TTP type in `publish_ready_report.md`.

## Preferred workflow

1. If an official URL is provided, fetch it first and save the summary to `sources_summary.md`.
2. Select a video type:
   - `判断基準型`: receiving age, eligibility choices, or decision criteria.
   - `チェックリスト型`: missing benefits, periodic notices, applications, or multiple items to verify.
   - `最新改正型`: annual changes, revised amounts, new official notices, or update summaries.
3. Build the opening with a safe expectation shift, not a plain system explanation.
4. Build the script only from official facts that can be confirmed.
5. Create slides with one message per slide.
6. Generate narration, subtitles, thumbnail, and final video.
7. Write `facts_check.md`, `warnings.md`, and `publish_ready_report.md`.
8. Assemble everything into `publish_package/`.
9. Report the output directory, runtime artifacts, and any verification notes.
10. If Filmora is unavailable or unstable, write `filmora_not_used_reason.md` and continue.

## Safety notes

- Do not create placeholder money amounts.
- Do not blur official information with guesses.
- Keep the first release local only.
- Filmora is optional; if it is unstable or unavailable, stop using it and complete the video with Python + FFmpeg.
- Do not use hooks such as `大損`, `国が隠す`, `全員もらえる`, `必ず増える`, or `申請すれば必ずもらえる`.
- Always end by prompting checks with the pension notice, Nenkin Net, pension office, municipality, or relevant official service.
