# TeamShift Agent Bridge design

Approved scope: an independent open-source bridge pairing native Hermes Bot Mode profiles with Paperclip agents, without modifying either application. The customer can manage a teammate in either product. Names synchronize in both directions; tasks continue through Paperclip's built-in gateway.

Use Network to Code's Apache-2.0 DiffSync 2.2.3 as the inventory reconciliation engine. A small SQLite journal supplies the previous common name, unfinished operations, and explicit bindings. There are no heuristic name matches or last-write-wins decisions.

One configuration binds one Paperclip company to one Hermes installation. Clients verify returned company and installation identity before mutation. Credentials are environment references, not config or database values. Remote URLs must use HTTPS; plain HTTP is limited to loopback. Do not follow redirects or use ambient proxy settings.

Implement explicit bind, provision, import, reconcile, resolve and status commands. Every mutating command requires --apply; reconciliation is dry-run by default. Creation is opt-in, not triggered for every discovered record. Provisioning uses native profile RPC with credential mirroring disabled, native Bot metadata CAS and canonical-session creation without a model call. Imports create a paused Paperclip record before binding.

Both names unchanged: no write. One changed: propagate. Both changed identically: accept. Different concurrent changes: record a conflict and write neither. Before writes, save the expected old values and intended name. After restart, continue only when both sides still contain an expected old value or the intended value. Unexpected changes stop that binding. Native Hermes metadata CAS is used; Paperclip lacks an established atomic conditional-name update, so pre-write comparison reduces but cannot eliminate an external edit race. Document that limitation.

Persist a creation intention before making a remote request. Unknown create outcomes must not be retried automatically or adopted by name. Resuming a known successful profile creation can finish Bot metadata/session setup. Missing records never cause cascading deletion.

Bot profile identity is a stable generated key, independent of its display name. Preserve existing metadata fields when changing the Bot title. Require applied.ui_meta and readback, not just a successful RPC envelope. An unavailable profile/session list is an error, never evidence of absence.

Do not copy secrets, memory, permissions or transcripts. Avatar translation, automatic deletion and global pause enforcement are outside this release. Execution wiring uses an operator-provided Paperclip secret reference and profile API-key environment reference; setting that key through the native management API is an explicit operation. Do not generate or persist plaintext credentials in bridge state.

Qualification is layered: deterministic engine tests; native HTTP/RPC contract simulations; real local transport tests; package and CLI smoke checks. These do not substitute for a disposable official-runtime integration test. Keep the owner installation unchanged and describe any unverified runtime behavior explicitly.
