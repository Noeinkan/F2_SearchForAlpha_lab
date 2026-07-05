Update project documentation to match the current code and behavior.

Usage: /update-docs [optional: topic, path, or "since <ref>"]

Examples:
- /update-docs                     (audit docs against recent changes)
- /update-docs flow-scanner        (update docs for one area)
- /update-docs since HEAD~10       (base the audit on recent commits)

Docs surfaces to keep current:
- `docs/*.md` (e.g. `docs/token-efficiency.md`, `docs/openclaw-research.md`)
- The "Non-obvious essentials" section of `CLAUDE.md`
- Docstrings / module headers for any code that changed
- README or usage snippets if present

Steps to follow:
1. Scope the work:
   - If a topic/path was given, focus there.
   - Otherwise run `rtk git log --oneline -15` and `rtk git diff --stat` to find what recently changed, and audit the docs covering those areas.
2. For each doc, verify claims against the code: paths, commands, flags, defaults, and described behavior. Note anything stale, wrong, or missing.
3. Update the affected docs:
   - Match the existing voice and structure; edit the smallest span needed.
   - Keep code references as clickable relative paths.
   - Add short entries for genuinely new features; remove docs for removed features.
4. If a code change lacks any doc coverage but should have it (new flag, new route, new config key), add a concise mention in the most relevant existing doc — do not create new files unless clearly warranted.
5. Cross-check that examples still run (dry-check commands and paths; run them if cheap and safe).
6. Show a summary of what was updated and why. Do not commit unless the user asks.
