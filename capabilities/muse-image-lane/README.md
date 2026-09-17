# Muse image generation lane

Registry id: `muse-image-lane` · kind: `runbook`

## Contract

**Covers.** Text→image generation from the Mac via `api.meta.ai/v1/images/generations`
(muse-image-1.0). Mac-vault key `~/.agent-vault/keys/meta-muse.key` (the Dell has none;
the key is never printed, echoed, or committed). Responses arrive base64 **WebP inside
a .png wrapper** at native 2240x1120 (1600x2240 portrait) — convert with
`sips -s format png` before anything downstream sees the bytes. Notable strength:
**spelled-in-image text** has gone 4/4 across title cards and signs — rare for a
generative lane. Typical round-trip 15–60 s, $0.

**Does NOT cover.** Dell hosts (no key). Deterministic/reproducible pixels (same
prompt → different image; bytes-reproducible figures go to PIL/three.js lanes).
Exact geometry or pixel-level control. Sighted verdicts on lane output are
stochastic → a SHIP needs **2-run consensus**; a single SHIP is provisional.

**Adapter pointer.** Inline recipe (curl + sips, ~5 lines) as used in eval run
logs; canonical invocation recorded in zcode memory `muse-image-lane-20260913`.

## Gates

| id | kind | check |
|----|------|-------|
| vault-key | deterministic | request authenticates from the Mac vault key ref; key never printed or committed |
| transport | deterministic | HTTP 200, b64 payload decodes, `sips` WebP→PNG conversion yields nonzero image |
| dimensions | deterministic | delivered asset matches the lane's native shape (2240x1120 / 1600x2240) |
| sighted-consensus | llm | muse-spark sighted prompt-adherence read; **SHIP×2 consensus** to count as a ship; spelled words match the brief exactly |

## Attack case

**WebP-in-.png trap.** The delivered bytes are WebP regardless of the `.png`
wrapper; a downstream consumer that opens them as PNG (PIL default codecs,
three.js TextureLoader) fails or silently renders nothing. The transport gate
forces a real container conversion before hand-off. Secondary attack: **stochastic
verdict flip** — the same image reads SHIP on one sighted run and KILL on the
next; the consensus gate refuses to credit a single-run verdict, and KILLs are
treated as health signal rather than lane failure.

## Lineage

zcode memory `muse-image-lane-20260913` (lane proven from Mac). Shipped the HOG
CRANKERS gen2 art wave (moon-skull + 5 billboards) and fapcoin title cards.
Descends from the muse-spark sighted/text lanes (`muse-spark-lanes`).

## Eval log

- 09-13 first Mac proof (memory receipt, run log archived in zcode memories).
- 09-14 fapcoin title card — spelled text exact, sighted SHIP.
- 09-17 eval (traced `muse-image-lane-eval-1`, art brief in the FlowRouter
  grammar): vault-key + transport + dimensions PASS, sighted SHIP×2.
- 09-17 eval-2 (traced `muse-image-lane-eval-2`): bearing product shot for the
  hunyuan3d-mlx-local eval-2 reference — 17 s round-trip, all gates PASS,
  SHIP×2; output consumed downstream (proves the chain, not just the lane).
