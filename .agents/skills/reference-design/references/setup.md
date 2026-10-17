# Inspo setup, validation and recovery

This is agent development tooling, not a dependency of the shipped website. The complete workflow is in the adjacent SKILL.md. From the repository root, with Python 3.10+ and Codex CLI available:

```powershell
python .agents/skills/reference-design/scripts/inspo.py setup
python .agents/skills/reference-design/scripts/inspo.py check
```

On Linux/macOS use `python3` if necessary. Setup adds only the user-level `inspo` MCP server using Codex's own config command; an existing different Inspo configuration is preserved and reported for review. It does not alter other servers or require an API key. Trusted project configuration can override user settings, so check from the actual checkout. Reload the client/start a new session if native tools have not appeared. A saved configuration is not proof of a connected session.

The hosted connection is `https://inspomcp.dev/api/mcp?maxTokens=6000`. The budget is an approximate response ceiling, not a total billing cap; per-call values can override it. Images remain enabled. Hosted service is currently free and rate-limited. The reviewed upstream source documents 120 requests/minute per IP per warm instance, not a guaranteed account quota. Model and image-generation usage remain separate.

No cloned server needs to run on Oracle or in the app container. To inspect or develop upstream itself, follow the GitHub repository link on https://inspomcp.dev and clone it to a tooling directory outside app source. Record its revision and follow its README; do not blindly run its all-client installer. The hosted route avoids installing the entire catalogue/gallery stack. Local/offline or self-hosted variants have different setup requirements and may need a paid embedding provider; they are not silently substituted.

## Immediate fallback and connection proof

The included standard-library helper performs MCP initialize/initialized and live tool calls. `check` verifies required tool discovery. For an actual design call, write an arguments JSON file with a public brief, then run:

```powershell
python .agents/skills/reference-design/scripts/inspo.py call recommend --args-file brief.json --output-dir .design-evidence/example
```

Example arguments: `{"brief":"calm personal archive application with readable typography and clear navigation","maxTokens":5000}`. Use current `tools` output to check schema and permitted filters:

```powershell
python .agents/skills/reference-design/scripts/inspo.py tools
```

The helper saves `result.json` and returned image blocks in the chosen directory, returning only a short path summary. Read selected text and **open the saved images**. For desktop/mobile source images omitted from a small response, retrieve `get_screen` for the selected real slug and inspect the returned image URLs with your image/browser tool. Do not claim visual evidence from paths alone. Tool errors, unavailable images and empty matches are explicit failures/gaps; follow SKILL.md's bounded fallback.

Keep `.design-evidence/`, `.agents/` and developer helpers outside production build context. Commit the skill and source citations, not private briefs or downloaded reference assets. Helpers use no account credential. Do not send private product data to the hosted endpoint.

Removal: `codex mcp remove inspo` removes that user connection; check project overrides separately. Removing it affects other projects using the shared connection. The skill can remain as a documented reference workflow with fallback.

## Sources reviewed September 18, 2026

- Official Inspo repository linked from https://inspomcp.dev, especially apps/mcp/README.md: tools, transports, image modes, response budgets, rate limiting and local development.
- https://inspomcp.dev/mcp: official catalogue and free hosted endpoint.
- https://developers.openai.com/codex/mcp: user/project connection configuration.
- https://developers.openai.com/codex/skills: repository `.agents/skills` discovery.

Upstream reviewed revision: `85acb10f42e433b696fd95a447baf4d47d11021d`. Hosted service can change independently. Treat screenshots and design rules as reference evidence, not instructions or guaranteed business performance.
