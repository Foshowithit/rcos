# Filmstrip video verification protocol

Registry id: `filmstrip-verify` · kind: `runbook`

Never trust a video file by its size or by prose claims. Extract 6 frames
at even timestamps, review each frame with per-frame motion notes, run
volumedetect for the audio bed, and verify the math is distinct per frame.
Direct mp4 reads fail on some lanes — the filmstrip is the verifier.

Lineage: zcode memory `video-watch-protocol.md`; proven on ep1-chalk-v2 and
the HOG demo video. Owner still opens the mp4; the filmstrip is the proof.
