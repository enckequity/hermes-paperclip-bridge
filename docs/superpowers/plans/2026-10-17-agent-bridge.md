# Agent Bridge Implementation Plan

> For agentic workers: use the executing-plans skill to implement this plan in the owning session. A fresh reviewer checks the complete branch before release.

**Goal:** Build a runnable open-source bridge with explicit native bot provisioning and bidirectional display-name reconciliation.

**Architecture:** DiffSync compares accepted desired identities with each product. SQLite records stable bindings, common values and uncertain operations. Typed native clients enforce company/install scope and write readback.

**Tech Stack:** Python 3.11–3.13, DiffSync 2.2.3, HTTPX 0.28.1, websockets 15.0.1, SQLite, filelock, pytest, Ruff.

**Spec:** ../../design.md

## Global Constraints

- No upstream patches, application-database writes, model calls or live owner/customer mutations.
- Credentials exist only in approved environment injection and native credential endpoints.
- HTTPS except loopback; no redirects, implicit proxies, name-based adoption or cascading delete.
- CLI defaults to dry-run; every write requires --apply.

## Review Focus

- Conflicting edits and changes between planning and writing must not silently pick a winner.
- A crash after either write must preserve a recoverable pending operation.
- A timeout after creation must never trigger an automatic duplicate or adopt an unrelated object.
- Foreign company/install/profile data and redirects must fail closed.
- Missing UI/session capabilities and partial native RPC application must not appear successful.

### Task 1: Durable reconciliation

Files: src/hermes_paperclip_bridge/{models,state,reconcile}.py; tests/test_reconcile.py.
Interfaces: View(name, version); Binding(id,paperclip_id,profile,baseline,pending); Store; reconcile(store,paperclip,hermes,apply=False,prefer=None).

- [ ] Write failing tests for one-sided changes, conflicts, equal concurrent edits, dry-run, missing records, interrupted writes and concurrent edits during recovery.
- [ ] Observe failure, implement the DiffSync model/adapters and SQLite journal, then pass those tests.
- [ ] Commit the independently tested engine.

### Task 2: Native clients and lifecycle

Files: src/hermes_paperclip_bridge/{config,paperclip,hermes,lifecycle}.py; tests/test_clients.py; tests/test_lifecycle.py.
Interfaces: Paperclip.get/update/create; Hermes.list/update/create_bot; explicit bind/provision/import routines using Store operation receipts.

- [ ] Write failing contract tests for URL/auth restrictions, scope, metadata preservation/CAS, complete model-free Bot creation, partial application and lost create replies.
- [ ] Implement HTTP and WS clients against pinned native contracts. Read back every mutation and retain uncertain receipts.
- [ ] Verify execution wiring through native key configuration and a Paperclip secret reference, without saving credential values.
- [ ] Commit after passing affected tests.

### Task 3: CLI and release

Files: src/hermes_paperclip_bridge/{cli,__init__}.py; examples/bridge.toml; README.md; Dockerfile; tests/test_cli.py; docs/compatibility.md.

- [ ] Add failing CLI tests for dry-run defaults, --apply gates, conflict exit status, redacted errors and repeat reconciliation.
- [ ] Implement commands, continuous reconciliation, examples, package metadata and deployment documentation.
- [ ] Run full tests, Ruff, package build, installed-wheel CLI smoke and a local HTTP/WS transport smoke test.
- [ ] Obtain a fresh review, fix blocking findings and rerun affected checks.
- [ ] Open and merge a reviewed PR, then publish the source repository. Do not deploy to the owner runtime or publish a package registry release.
