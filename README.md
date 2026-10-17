# TeamShift Agent Bridge

Pair Paperclip agents with native Hermes Bot Mode profiles. Change a teammate's display name in either product and reconcile it to the other. Explicit provisioning and importing establish those pairs without matching records by name.

Built on [Network to Code's DiffSync](https://github.com/networktocode/diffsync), an Apache-2.0 inventory synchronization library. DiffSync computes and applies inventory changes; a SQLite journal tracks the common baseline, conflicts and interrupted operations. No additional server is required. This is an independent community integration, not an official Nous Research or Paperclip package.

**Status: experimental, version 0.1.0.** Local tests cover reconciliation, native API contracts and actual WebSocket transport. A disposable deployment of both upstream applications has not yet been qualified. The bridge has not been connected to the owner's live setup.

## What you get

- Stable one-to-one binding of Paperclip agent IDs and Hermes profile keys.
- Bidirectional display-name synchronization, conflict detection and preview by default.
- Paperclip → Hermes provisioning through native profile RPC, Bot metadata and canonical Bot Chat creation. No model call, credential mirroring or default-profile cloning.
- Hermes → Paperclip importing with timer/event wakes disabled, followed by verified paused status.
- Explicit execution wiring through Paperclip's built-in `hermes_gateway` adapter.
- A durable journal and process lock. Missing records never trigger deletion; uncertain creation outcomes stop for inspection.

Names synchronize. Org hierarchy, human memberships, avatars, skills, memory, transcripts, permissions and pause state do not. Paperclip owns its organization and work board; Hermes owns execution and profile settings. This bridge does not synchronize task boards. Tasks use separate issue sessions within the bound profile, rather than sharing its canonical Bot Chat.

## Install

Requires Python 3.11–3.13. No Docker, Redis or cloud account is needed for the bridge.

```sh
git clone https://github.com/enckequity/hermes-paperclip-bridge.git
cd hermes-paperclip-bridge
python -m venv .venv
# Activate .venv using your shell's activation command.
python -m pip install .
cp examples/bridge.toml bridge.toml
teamshift-bridge --help
```

Edit `bridge.toml` with the company UUID, native installation ID and management listener URLs. The installation ID comes from native `profiles.list`; it is not a profile name. Keep the state file with this exact company/installation pair. Back it up while the bridge is stopped.

Supply credentials through the configured environment variables using your secret manager, for example `op run --env-file .env.1password -- teamshift-bridge --config bridge.toml status`. Keep secret references outside git. TOML stores environment variable **names**, never token values.

Paperclip needs an existing credential authorized for company agent/secret management. Hermes needs a native dashboard session: `bearer` uses a provider session token and short-lived WebSocket ticket; `loopback` uses `HERMES_DASHBOARD_SESSION_TOKEN` and is allowed only on loopback. The execution listener's `API_SERVER_KEY` is separate. The bridge does not bypass native hire approvals or set up authentication providers.

Remote URLs require HTTPS. Redirects and ambient proxies are disabled. Use listener root URLs without embedded credentials or queries. One company must map to an already-isolated Hermes installation: profiles are not a tenant security boundary.

Provisioning disables native credential-file mirroring. Native Hermes profiles can still use root provider OAuth fallback. The bridge does not enforce credential isolation inside an installation; configure that boundary in the runtime.

## Pair and synchronize

Every mutation requires `--apply`. Preview may create the local state file but does not create bindings or change remote records. `status` needs no credentials.

```sh
teamshift-bridge bind PAPERCLIP_AGENT_UUID hermes-profile
teamshift-bridge bind PAPERCLIP_AGENT_UUID hermes-profile --apply
teamshift-bridge provision PAPERCLIP_AGENT_UUID --apply
teamshift-bridge import hermes-profile --manager-id PAPERCLIP_MANAGER_UUID --apply
teamshift-bridge status
teamshift-bridge reconcile
teamshift-bridge reconcile --apply
teamshift-bridge resolve BINDING_UUID --prefer hermes --apply
teamshift-bridge watch --interval 30 --apply
```

`resolve` affects only the selected binding. `reconcile` and `watch` process existing bindings; neither discovers or creates new teammates automatically. A conflict stops that binding while others continue. Stop watch with Ctrl+C. Output is JSON; DiffSync diagnostics go to stderr. Exit codes: `0` success, `2` conflict/missing record, `3` operational failure, `130` interrupted. Watch emits an array each cycle and continues through reported per-binding failures.

| Since the common name | Result |
| --- | --- |
| Only Paperclip changed | Update Hermes |
| Only Hermes changed | Update Paperclip |
| Both now have the same name | Accept the common name |
| Both changed differently | Conflict; write neither |
| A record is missing | Report missing; delete nothing |

Hermes updates use native revision checks and preserve other Bot metadata. Paperclip has no established atomic conditional-name update in the inspected version. A fresh comparison before PATCH and readback afterward reduce the race; an external edit between those requests can still be overwritten. Coordinate overlapping writers.

## Wire native execution

Provision/import establishes identity. Configure the profile's provider/model and enable the native execution listener separately. Imports remain paused with scheduling disabled until enabled in Paperclip.

Create a profile-specific execution key in your secret manager and store the same value in a native encrypted Paperclip company secret. Pass only its UUID and the environment variable name:

```sh
teamshift-bridge wire BINDING_UUID \
  --execution-url http://127.0.0.1:8642 \
  --secret-id PAPERCLIP_SECRET_UUID \
  --key-env HERMES_PROFILE_EXECUTION_KEY
# Repeat with --apply after checking the preview.
```

The agent must already use `hermes_gateway`. Apply sets the profile's `API_SERVER_KEY` through native `/api/env`, verifies authenticated `/p/<profile>/v1/capabilities`, then patches the gateway URL, secret reference and issue-session strategy. Native top-level merge preserves other adapter fields. No plaintext key enters bridge state.

The operator must ensure that the existing Paperclip secret contains the same key. The bridge never reads decrypted secret values. Capabilities verify the listener contract, not a model run or secret value. After a failed wire, the profile key may already be changed: inspect native services before retrying. Wiring does not start a listener, unpause an agent, enable scheduling or submit a model run.

## Recovery and qualification

Keep SQLite state: it contains identities, names and operation phases, but no credentials. Interrupted renames recover from the pending journal and readback. An uncertain create is never retried or adopted by name. Inspect the target product and explicitly `bind` verified IDs; retain the uncertain operation as evidence. Do not delete state to force a retry.

Profile keys stay stable when names change. Canonical Bot Chat setup uses exact-title lookup and verifies the durable session identity. Ambiguous sessions require operator review.

Contracts inspected: Hermes `d923a5eb` (v0.22.2-desktop) and Paperclip `bba6a45f0d364cfd962ac59b3bdf2426a8222adb` (2026.1012.0). See [compatibility evidence](docs/compatibility.md). Future versions may change these interfaces.

## Develop

```sh
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m build
python -m pip check
```

Tests use fixtures and disposable local transport servers. No real credentials, model calls or production writes are required. No GitHub Actions workflow is installed. See [design](docs/design.md), [contributing](CONTRIBUTING.md), [security](SECURITY.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

Apache-2.0 licensed.
