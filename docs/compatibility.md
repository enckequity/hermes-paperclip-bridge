# Native interface evidence

The bridge uses native public interfaces without modifying either product. Source inspection establishes the intended contract. Fixture tests establish bridge behavior under that contract. Neither proves a successful live deployment of both products.

| Interface | Pinned source | Checks |
| --- | --- | --- |
| Profile RPC | [methods_profiles.py](https://github.com/NousResearch/hermes-agent/blob/d923a5eb/tui_gateway/methods_profiles.py) | Installation ID, credential isolation, metadata revision and readback |
| Canonical Bot Chat | [Desktop flow](https://github.com/NousResearch/hermes-agent/blob/d923a5eb/apps/desktop/src/plugins/hermes-bots/canonical-chat.ts), [sessions](https://github.com/NousResearch/hermes-agent/blob/d923a5eb/tui_gateway/methods_session.py) | Exact title, durable ID, canonical root; no prompt |
| Dashboard auth | [ticket route](https://github.com/NousResearch/hermes-agent/blob/d923a5eb/hermes_cli/dashboard_auth/routes.py), [WebSocket](https://github.com/NousResearch/hermes-agent/blob/d923a5eb/hermes_cli/web_server_chat.py) | Ticket subprotocol or explicit loopback session token |
| Execution API | [api_server.py](https://github.com/NousResearch/hermes-agent/blob/d923a5eb/gateway/platforms/api_server.py) | Profile route, authenticated capabilities |
| Credential lifecycle | [config_env.py](https://github.com/NousResearch/hermes-agent/blob/d923a5eb/hermes_cli/web_routers/config_env.py) | Explicit environment-supplied key and native confirmation |
| Agent CRUD | [agents.ts](https://github.com/paperclipai/paperclip/blob/bba6a45f0d364cfd962ac59b3bdf2426a8222adb/server/src/routes/agents.ts), [validator](https://github.com/paperclipai/paperclip/blob/bba6a45f0d364cfd962ac59b3bdf2426a8222adb/packages/shared/src/validators/agent.ts) | Company/agent identity, name-only PATCH, disabled scheduling on import, paused readback |
| Gateway execution | [execute.ts](https://github.com/paperclipai/paperclip/blob/bba6a45f0d364cfd962ac59b3bdf2426a8222adb/packages/adapters/hermes/src/gateway/server/execute.ts) | Explicit profile URL and issue sessions |

Before production use, qualify a disposable official-runtime pair: provision/import, rename from each UI, create a conflict, interrupt/resume reconciliation, wire a unique execution key, and complete a low-cost Paperclip issue. Verify the intended profile executes and its canonical Bot Chat remains unchanged. This live qualification is outstanding for 0.1.0.
