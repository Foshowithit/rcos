# Video forensics receipt (reference-clip measurer)

Registry id: `video-forensics-receipt` · kind: `script`

Turn any video — a reference film OR one of our own deliverables — into a
forensics receipt: cut rhythm, loudness, color, motion, contact sheet, with the
metric definitions recorded alongside the numbers so no reader has to guess how
a value was computed.

Implementation: `~/.zcode/workspace/default/creative-study/rig/study_run.py`
runs on the Dell (ffmpeg/ffprobe/yt-dlp live there; decodes are Dell work).
Mac wrapper `rig/run_on_dell.sh` syncs the script, runs it remotely, pulls
receipts back.

## What it measures (v0.1)

- **cuts**: ffmpeg `select gt(scene,0.30)` + a stricter 0.50 pass; shot-length
  distribution (median/mean/p5/p95/min/max), first-cut latency, cut density.
- **loudness**: ebur128 integrated LUFS, LRA, true peak.
- **color**: per-thumbnail saturation/luma, dark-frame share, k-means palette
  (k=6, fixed seed) + palette_n80 (clusters covering 80% of pixels).
- **motion**: per-second mean abs-diff of 1fps thumbnails (0..1) + stillness share.
- **sheet + profile**: labeled contact sheet of cut frames; shot-length bars +
  motion curve.
- **source metadata**: title/channel/upload date/views/url for fetched clips;
  `local-upload` provenance for our own files.

## Shape rules that made it work

- Media never enters a repo: clips/frames stay in `~/tmp/creative-study` on the
  Dell; only derived JSON is committed, sheets land in gitignored `.media/`.
- Prefer the scratch-venv yt-dlp (`~/tmp/creative-study/venv/bin/yt-dlp`) over
  the system one — the 2024-era binary 403s on modern YouTube.
- `ssh -n` / `</dev/null` on every remote call: batches run inside `while read`
  loops and an unfed ssh swallows the heredoc.
- scp/rsync remote paths are relative to the remote home — they do not expand `$HOME`.
- Two real bugs found by first use (both fixed): float-index when a clip had
  ≤40 cuts; palette sampler indexing by array when a clip had ≤40 thumbnails.

## Lineage

2026-09-17 creative-study round 1: 17 reference clips (classes: industrial
brand film, luxury macro, music video) + 3 own films measured on the Dell.
Receipts committed at `workspace/default/creative-study/studies/*.json`.
Discovery that justifies keeping it: it corrected a prior belief — NIN's
"March of the Pigs" measured as a **single 182s take** (3 scene changes,
highest in-frame motion of the corpus), not the rapid-cut video it is
remembered as. Trust receipts, not memory.
