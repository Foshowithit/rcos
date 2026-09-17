# Receipt Figure Render

Registry id: `receipt-figure-render` · kind: `workflow`

## Contract

**Covers.** Deterministic figures for reports/dashboards, straight from the
registry: `capabilities/receipt-figure-render/adapter/receipt_figures.py`
renders `fig-verdicts.png` (verdict distribution bar) and
`fig-per-capability.png` (evals per capability, stacked by verdict, sorted
desc) from `registry/capability-registry.json` with PIL — fixed palette
(ship green / fix amber / blocked red), layout derived from data
(`H = 60 + n*(BAR_H+10) + 40`), and a `values.json` sidecar recording every
plotted number. `check_figures.py` is the second code path: it recomputes the
stats from the registry and diffs them against the sidecar.

**Does NOT cover.** Interactive or animated charts (static PNGs only).
Sight-judged aesthetics on its own (the muse legibility gate still runs).
Arbitrary data sources — registry JSON in, that's the input contract.

**Adapter pointer.** `capabilities/receipt-figure-render/adapter/receipt_figures.py`
+ `check_figures.py`.

## Gates

| id | kind | check |
|----|------|-------|
| render | deterministic | both PNGs + values.json produced; no zero-byte files |
| sidecar-agrees | deterministic | check_figures.py recomputes n_capabilities / n_evals / verdict_distribution / per-capability counts from the registry and diffs the sidecar; any mismatch names the field and exits 3 |
| legible | llm | sighted read: bars/labels legible; no broken-image or empty-slab glyph that reads as an error (an empty 0-row reads as data, not a failed component) |

## Attack case

**The tampered sidecar.** A figure whose plotted values were hand-edited after
render (attack: ship 65→99 in values.json) — the PNG looks authoritative, the
sidecar lies. Caught by the second-code-path checker: exit 3 naming
`verdict_distribution {'ship': 99...} != {'ship': 65...}`. This is the
check-that-cannot-fail doctrine applied to figures: the checker reads the
registry independently, never the renderer's own output state.

## Lineage

Descends from the OW Lab exhibit pattern (figures generated from artifacts,
values sidecar, independent checker — commit `05817f8`) and the
rcos-famc dashboard figures. Built 09-17 during the admission campaign.

## Eval log

- 09-17 eval-1 (traced): registry at 74 evals / 20 caps — first render failed
  with a NameError (BAR_H referenced inside its own assignment — caught by
  running it, fixed), rerun rendered + FIGURE_CHECK_PASS; muse legibility SHIP.
- 09-17 eval-2 (traced): regeneration AFTER the registry moved (75 evals —
  this campaign's own traces) — figures tracked the change, sidecar agrees.
  Proves regeneration-after-change, not copy-of-first-render.
- 09-17 attack (traced): tampered values.json (ship 65→99) — exit 3 with the
  named diff.
