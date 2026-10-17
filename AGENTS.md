# Agent Bridge

Use unchanged public Hermes and Paperclip interfaces. Do not patch their source or write their databases directly. Runtime credentials come from environment variables populated by the operator's secret manager and never enter SQLite, logs, fixtures or commits.

Work in a dedicated git worktree and task branch. Use local pytest, Ruff and package-build checks; do not add GitHub Actions. Review before merging. Keep live owner/customer runtimes unchanged unless separately authorized.

The bridge synchronizes explicitly managed identities. Names are not identifiers. Never adopt a same-name record automatically, propagate deletion, copy credentials/memory, or silently choose a winner for concurrent edits. Source inspection and simulated contract tests are not live product qualification.

Human-facing product names use TeamShift. Technical documentation should name the connected upstream products clearly.
