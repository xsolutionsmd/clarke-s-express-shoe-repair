# Handoff

Release isolation checkpoint: production was released through PR #2 as
`f8d72bd8f7ef84a0814c8706ad6a02887f86b4fc`. This handoff-only checkpoint exercises
the independent Derek preview publisher; application files are unchanged.

<!-- xs-status:start -->
Pipeline status (generated 2026-10-17T19:48:51.044900+00:00):

- **identity**: done
- **research**: done
- **spec**: done
- **assets**: done
- **delivery**: done
- **infra**: done
- **template**: done
- **build**: done
- **deploy**: todo: record verified deploy evidence
<!-- xs-status:end -->

## Current state

2026-10-17: functional/full pipeline in progress. All three live sites remain HTTPS/noindex placeholders at 7cc259a097d6a736a057d84726eda6ae74ffbfc7. Committed candidate 37fd564eb87aeffb6223d70b482c1662d483d57e passed 134 backend/API tests and 81 browser cases; the final command exited 0. Earlier backend recovery checks passed 61 recovery tests and 54 updater cases. All 19 code/visual findings are triaged and fixed, and the parent affected-screen visual pass is accepted. All 45/45 pre rows now pass. Four targeted backend/API cases and four browser scenarios closed the remaining evidence gaps without application changes. All 13 live rows remain.

## Last session

Research covered 29 official pages, both Maps locations, social profiles and directory/press corroboration. Current Bel Air hours and Dundalk appointment instructions take precedence over stale components; unresolved operating policies remain in open-questions.md. The media library contains 453 images with 17 shortlist picks; coverage gaps are in media.md. Package delivery was verified after reload and by matching a downloaded copy's hash and size.

## Next step

The first preview CI run rejected the 12 MP HEIC conversion under its memory limit (136 other backend cases passed). CI's inherited 16 MiB stack reproduced the failure locally. The decoder now starts with at most an 8 MiB stack; all nine upload cases pass under CI's inherited limit and the real container cap. The earlier allocator trial was removed. Verify required hosted CI before release. Reviewed environment-bound backup/updater scripts and units are installed on all three environments with preserved runtime configuration and keys. Complete the authorized release and all 13 live rows, then record final branch-specific revisions after the handoff/state commits.

## Blockers / waiting on

Review triage is complete. Release CI and live feature acceptance remain open. Real Google/Gmail requires a signed-in operator browser; the default profile is signed out and the Chrome automation fallback was stopped by its URL-verification safeguard. Owner-dependent policies remain demo defaults/open questions until operational handover, not evidence of client approval.
