Update CHANGELOG.md from recent git history in Keep a Changelog format.

Usage: /update-changelog [optional: version or "since <ref>"]

Examples:
- /update-changelog                (summarize commits since the last changelog entry)
- /update-changelog 1.4.0          (cut a new released section)
- /update-changelog since v1.3.0   (summarize a specific range)

Steps to follow:
1. If `CHANGELOG.md` does not exist, create it with a Keep a Changelog header (https://keepachangelog.com) and an `## [Unreleased]` section.
2. Determine the range:
   - Default: commits since the date/tag of the top existing changelog entry.
   - If a ref/range was given, use it.
   Run `rtk git log --oneline --no-merges <range>` to gather commits.
3. Group changes under the standard headings — Added, Changed, Fixed, Removed, Deprecated, Security — dropping empty groups.
4. Rewrite each entry as a user-facing, present-tense line (what changed and why it matters), not a raw commit subject. Collapse noisy/related commits into one line.
5. Placement:
   - No version arg → put entries under `## [Unreleased]`.
   - Version arg → move Unreleased items into `## [<version>] - <today's date>` and leave a fresh empty Unreleased.
6. Skip purely internal churn (formatting-only, merge commits, WIP) unless it changes behavior.
7. Show a diff of the changelog edit and confirm before committing (do not commit unless the user asks).
