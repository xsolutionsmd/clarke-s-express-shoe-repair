# Project-specific route

Read the repository README, AGENTS.md, requirements, accepted design system and validation record. These own the project's facts, stack, start/check commands and release policy. Fill missing product decisions from the user's request; do not import another project's context.

For new App Launchpad applications, implement the requested product alongside its lifecycle. Use the selected source directory and existing Docker/CI/host contract. Browser applications apply this design workflow; command-line/backend-only applications need no visual design pass. Keep tooling and captured references out of runtime images.

If Stitch is available and the project requires it, use the installed skills. Otherwise implement from the selected reference and explicit design decisions with the existing stack. Preserve a named project-specific generator choice; explain an unavailable dependency before using a fallback.
