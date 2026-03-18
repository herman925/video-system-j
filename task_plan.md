# Task Plan

## Goal

Revamp the organiser layout so Rename and Move can keep separate left-panel widths, and tighten the Move inspector so it uses space more intentionally.

## Phases

| Phase | Status | Notes |
|---|---|---|
| Inspect organiser layout and settings flow | complete | Located shared organiser width state in page + settings, plus mover inspector density problems |
| Implement per-tab organiser widths | complete | Added separate saved widths for Rename and Move tabs, with legacy width fallback |
| Revamp mover layout density | complete | Tightened mover list status columns and rebuilt mover inspector into compact action/editor/preview cards |
| Validate behavior | complete | Editor diagnostics are clean for organiser page and settings; only pre-existing CSS compatibility warnings remain in theme.css |
| Refactor renamer visual language | complete | Renamer now uses its own hero/detail CSS and full-width preview flow, while mover keeps its existing inspector markup and styling |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| Large patch missed organiser inspector context | 1 | Re-read the affected block and reapplied changes in smaller patches |
| NiceGUI served stale organiser markup after CSS/Python edits | repeated | Full process restarts were required when not using reload-enabled dev startup |