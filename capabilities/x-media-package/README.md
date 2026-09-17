# X Media Package

Registry id: `x-media-package` · kind: `workflow`

## Contract

**Covers.** Pre-flight for anything about to be posted to X with a video:
`capabilities/x-media-package/adapter/xcheck.py` asserts the platform's hard
limits before upload — duration ≤ 140 s, aspect ratio ∈ [0.5, 2.0], caption
non-empty and ≤ 280 chars, alt-text non-empty and ≤ 1000 chars — and extracts
a poster frame (`x-poster.jpg` at `min(1.0, dur/3)`) so a sighted gate can
look at what the timeline will actually show. Exit codes: 0 pass, 3 gate-fail,
4 tooling-missing.

**Does NOT cover.** Posting (nothing uploads — this is the pre-flight gate).
Media transcoding. Whether the video is *good* (sighted gate's job, using the
poster). Reply/thread mechanics.

**Adapter pointer.** `capabilities/x-media-package/adapter/xcheck.py`
— positional args, NOT flags: `xcheck.py <video> <caption-file> <alt-file>`
(sys.argv[1..3]; caption and alt are paths to text files).

## Gates

| id | kind | check |
|----|------|-------|
| platform-limits | deterministic | duration ≤ 140 s; aspect ∈ [0.5, 2.0] (ffprobe); caption 1..280 chars; alt-text 1..1000 chars |
| poster-extract | deterministic | x-poster.jpg extracted at min(1.0, dur/3) for the sighted gate |
| poster-reads | llm | sighted read of the poster: subject legible, no broken frame as the thumbnail face |

## Attack case

**The 321-char caption.** Captions written for elsewhere (a blog paragraph, a
git commit message) blow past 280; X rejects or truncates at upload time —
the worst moment to find out. Attack receipt: 321-char caption → exit 3
`FAIL CAPTION 321 > 280` before anything nears the API. Aspect traps (vertical
phone footage on a horizontal timeline) hit the same gate family.

## Lineage

Derived from the X organic limits recorded in the model-compare video
pipeline work (duration ≤140s, aspect [0.5,2.0], caption ≤280 — the
hog-crankers demo and fapcoin ships went out under these by hand). Built
09-17 during the admission campaign to make the pre-flight mechanical.

## Eval log

- 09-17 eval-1 (traced): chalk package (video + 150-char caption + 112-char
  alt) — XCHECK_PASS, poster extracted, muse sighted read SHIP ("measure
  twice" title crisp/legible).
- 09-17 eval-2 (traced): rcos-dispatch-eval-2-out.mp4 (1280x720, 4.0s) — PASS.
- 09-17 attack (traced): 321-char caption — exit 3, CAPTION 321 > 280.
