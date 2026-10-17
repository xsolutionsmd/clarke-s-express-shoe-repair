# Beautiful website and application workflow

In this repository, ask: **Build me a beautiful website** or **Make this interface beautiful while preserving its behavior**. The agent reads the [complete repo skill](../.agents/skills/reference-design/SKILL.md), recovers [project context](../.agents/skills/reference-design/references/project-context.md), finds and views references, implements the design and checks desktop/mobile. Use `$reference-design` for explicit selection.

## First use on another computer or agent container

Python 3.10+ and a working Codex CLI are enough for the connector helper:

```powershell
python .agents/skills/reference-design/scripts/inspo.py setup
python .agents/skills/reference-design/scripts/inspo.py check
```

Use `python3` where appropriate. Run setup inside the actual agent environment: a host's user configuration is not automatically copied into a container or another person's account. Restart/reload the client if native tools have not appeared. Read [setup and fallback](../.agents/skills/reference-design/references/setup.md) for the immediate callable helper, upstream clone/development route, costs, output budgets and removal. No secret is needed for hosted Inspo; keep other design credentials private.

The skill and all its instructions ship with this repository. Installed optional Stitch/browser/accessibility tools remain environment capabilities: use the documented fallback or report the exact missing capability, never claim a tool was used when unavailable. User-level Inspo configuration is shared across this user's projects, not embedded into the shipped application.

## Completion criteria

The workflow returns editable source, a real local preview and checks of visual coherence, mobile layout, accessibility and important actions. Existing product/design decisions, source branch and deployment controls remain authoritative. Developer tools and evidence stay outside production images. Keep third-party image evidence under ignored `.design-evidence/` and source citations in appropriate design docs.

Visual quality, speed and usage must be judged on actual outputs. Setup does not redesign or deploy the current application, guarantee subjective beauty or prove a five-minute build. Existing release authorization is separate from permission to create a local preview.
