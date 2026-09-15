# Promotion pipeline (eval-readiness queue)

Ordered by expected frequency of the triggering work. All 7 candidates sit at 0 evals; each needs 2 shipped evals with lineage to promote.

## 1. filmstrip-verify — gates: six-frames, distinct-motion, audio-bed, no-slideshow — evals: 0
Ship 1: next real video verification with archived 6-frame strip + volumedetect.
Ship 2: the following real video verification with the same evidence.

## 2. browser-verify-artifacts — gates: http-serve, zero-console-errors, rendered-proof — evals: 0
Ship 1: next real archived browser proof (http serve, zero console errors, screenshot).
Ship 2: the following real archived browser proof.

## 3. muse-image-lane — gates: vault-key, spelled-text, dimensions — evals: 0
Ship 1: next real lane image delivery (vault key ref, exact spelling, 2240x1120).
Ship 2: the following real lane image delivery.

## 4. dell-gpu-dispatch — gates: gpu-encode, dell-only, perceptual-match — evals: 0
Ship 1: next real Dell render dispatch (NVENC, Blender -t 16, Dell-only, perceptual match).
Ship 2: the following real Dell render dispatch.

## 5. hog-qa-suite — gates: five-of-five, zero-console-errors, judge-ship — evals: 0
Ship 1: next real HOG wave passing 5/5 suites with zero console errors and hog-eyes ship.
Ship 2: the following real HOG wave passing the same gates.

## 6. chalk-capture-recipe — gates: font-warmup, no-fallback-serif, av-sync, no-slideshow — evals: 0
Ship 1: next real chalk capture (warmup frame, Caveat weights loaded, VO aligned).
Ship 2: the following real chalk capture with the same evidence.

## 7. qr-camo-embed — gates: scans, invisible — evals: 0
Ship 1: next real QR camo embed that scans to the target URL with no visible geometry.
Ship 2: the following real QR camo embed with the same evidence.

## Honesty rule
No eval without fresh task evidence; a blocked verdict is a good outcome.
The anti-slideshow bar is load-bearing for every video capability.
