# Rank Effects Implementation Plan

## Goal

Deliver a better effects system in stages without breaking the existing tracker UI.

## Scope

- Fix the confirmed settings/configuration bug in the current SVG badge path.
- Build a Diamond comparison lab that lets us evaluate current SVG, PixiJS, and Rive integration paths.
- Do not replace all tiers yet. The Diamond tier is the proving ground.

## Phase 1: Stabilize Current SVG Path

- Fix tracker/page.py so the badge renderer reads the saved aura config from the page closure rather than `globals()`.
- Keep the current SVG badge working as the baseline implementation.
- Avoid adding more SVG settings before the bug is fixed.

## Phase 2: Comparison Lab

- Add a new internal route for effects experiments.
- Show three panels:
  - Current inline SVG Diamond badge.
  - PixiJS Diamond prototype.
  - Rive Diamond integration panel.
- The lab should explain what each renderer is proving.

## Phase 3: PixiJS Diamond Prototype

- Use CDN-loaded PixiJS inside a NiceGUI page.
- Build the Diamond effect with layered gradient sprites/graphics, additive glow, soft particle drift, and slow orbital streaks.
- Prioritize authored motion and readable silhouette over particle count.
- Use one canvas, one container tree, and cleanup on page unload.

## Phase 4: Rive Diamond Integration

- Integrate the Rive web runtime in the same comparison lab.
- Support loading a local Diamond `.riv` asset once one exists.
- For now, expose the runtime shell and a clear missing-asset state if no `.riv` file is available.
- Document that Rive is the preferred final path if we want a truly designed animation rather than procedural code art.

## Phase 5: Evaluation Criteria

Compare the three approaches against:

- Visual quality at 48 px.
- Readability of the score label.
- Perceived depth and luminosity.
- Animation intentionality.
- Ease of iterating on style.
- Runtime complexity inside NiceGUI.

## Expected Outcome

- The current SVG path remains as fallback.
- PixiJS gives us a real procedural live prototype.
- Rive proves whether the final premium direction is worth the authoring pipeline cost.

## Likely Decision

- Keep the bug-fixed SVG path as fallback.
- Use PixiJS for quick iteration and proof-of-concept effects.
- Move to Rive only if the Diamond art direction is validated and we are willing to author assets externally.

## Decision Update

- PixiJS is now the selected renderer path for production experimentation.
- Rive is deferred until there is a real authored `.riv` asset and a reason to pay the art-pipeline cost.
- The next implementation step is to replace the tracker's Diamond badge entry point with the reusable PixiJS renderer while preserving the SVG path as a fallback.