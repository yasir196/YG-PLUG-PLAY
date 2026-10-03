# AGENTS.md — YG-PLUG-PLAY

Read this file before every task. It is the repository-level operating contract for coding agents.

## Authority

Architecture baseline: **`docs/ARCHITECTURE_V5.md` (frozen) + `docs/ERRATA_V5.md`**. If an older V5 example conflicts with Errata, Errata controls.

Do not create V6 for implementation details. Existing Senior Health / MasterProduction repositories are out of scope unless the user explicitly requests changes there.

## Golden rule

**Install features; do not rewrite the pipeline.**

Core owns security, orchestration, state, contracts, routing and audit. Niche owns versioned domain templates, prompts, rules and defaults. Plugin owns replaceable capabilities and its settings. Channel owns runtime configuration, projects, routing, plugin pins and credentials. Run owns an immutable execution snapshot and actual node-run history.

## Non-negotiable rules

1. Channel is the runtime workspace; Niche is a versioned template.
2. Plugins install centrally. Installation and Channel enablement are separate. No niche-level plugin assignment state.
3. Multiple plugin versions may coexist. Channels pin versions. Never silently migrate all Channels.
4. Active/paused runs keep frozen plugin/runtime versions; no mid-run hot swap.
5. Executable plugin code never runs in Core; use isolated worker subprocess/RPC.
6. v0 executable plugins are admin-approved trusted code. Trust is a Core/admin grant bound to `(plugin_id, version, package_sha256)`, never manifest self-declaration.
7. Same-user subprocess isolation is not a hostile-code sandbox; do not claim otherwise.
8. Workers receive a clean allowlisted environment, never Core DB path, master key, unrelated credentials or admin/OAuth tokens.
9. Mutable runtime data stays outside Git. Windows default: `%LOCALAPPDATA%\YG-PLUG-PLAY\`.
10. Secrets are encrypted at rest. Windows target prefers DPAPI CurrentUser; recovery material stays separate.
11. Prefer credential/reverse proxy over raw secrets. Credentials are domain-bound and auth never follows cross-domain redirects.
12. Proxy blocks private/loopback/link-local targets except explicit Core-owned internal paths. Localhost Core API requires authentication, Host validation and strict CORS.
13. Raw credential access is exceptional/high-risk, never the default.
14. Credential domains and derived network permissions must be consistent and visible during approval/re-approval.
15. Static ZIP validation never imports or executes plugin code.
16. Reject ZIP traversal, absolute/ambiguous paths, Windows reserved names, case/Unicode collisions, links, encrypted entries, nested archives and resource bombs.
17. Package SHA-256 is audited. Hash integrity is not publisher trust.
18. Each Python plugin version has its own environment. Production dependencies are exact/hash-pinned wheels. Use `uv` as planned environment/interpreter manager.
19. Core is the sole Core-SQLite writer. v0 uses one Core process; scheduler may run as a Core background task.
20. Plugin private data is scoped by immutable execution context. Never expose raw Core SQL.
21. Core owns Capability and Contract registries; domain-specific logic is not hard-coded into Core.
22. Generic standard contracts/capabilities belong to versioned `yg-standard-contracts`.
23. Prompt-driven domain capabilities use Core Prompt Executor and replaceable `text-generation` providers.
24. LLM routing is purpose-aware: exact purpose → variant → default. Route options → Channel plugin settings → plugin defaults.
25. Snapshot effective provider/model/options for every run/node.
26. Prompt Executor uses a sandboxed selected template engine and separates prompt-context rules from deterministic validators.
27. Provider requirements such as JSON schema, image input, web search, streaming and token counting are declared and route-validated.
28. Research/tool output is untrusted prompt content; delimit it and preserve system/rule authority.
29. Workflow Engine controls production. Event Bus handles side effects/notifications/analytics, not independent main-flow advancement.
30. Workflow nodes call capabilities, not concrete provider plugin IDs.
31. Conditions use a safe declarative evaluator such as JSONLogic; never Python `eval()`.
32. Every cycle is bounded by `loop_control` with explicit exhaustion behavior.
33. `from` resolves the latest successful generation of that node output in the current run. Human-edited generations count as generations of the same output.
34. Use defined `latest`/`approved` selectors. `approved` supports `among`/tag disambiguation. No magic artifact aliases.
35. `$run.*` is the run-input selector namespace. `$self` is the reserved stay-on-current-node transition.
36. Approval decisions are typed `approval.decision` artifacts. Revision can consume human feedback.
37. Human edit creates a new artifact generation with actor/diff audit; never overwrite history.
38. Map failure review requires declared failed-item data. Human retry is bounded.
39. Parallel terminal rejection/failure cancels remaining branches per policy while preserving incurred usage.
40. Partial collections explicitly declare and validate partial acceptance policy.
41. Minimal durable run/node/approval state exists from Phase 1a. Restart restores waiting approvals/pending work.
42. Re-run defaults to frozen snapshot. Re-run with current config is a separate operation with new snapshot/diff.
43. Large artifacts use handles/controlled paths, never base64 media over JSON-RPC. Validate size/hash/MIME.
44. Input artifacts are explicitly authorized; workers never get arbitrary project filesystem access.
45. Provider retry, fallback and node retry are separate. Respect `Retry-After` and exponential backoff. Fallback triggers are explicit.
46. Sensitive nodes may disable fallback or require approval after fallback.
47. Long provider jobs use durable provider IDs/polling/reconciliation; do not assume localhost webhooks.
48. Plugins report usage; Core calculates cost from a versioned pricing catalogue.
49. Before paid LLM Phase 2 work: per-run hard spend/usage cap, route `max_tokens` cap and dry-run/mock mode.
50. Rate limits/budgets may be credential-scoped as well as platform/channel/project/provider scoped.
51. Core events use durable outbox/at-least-once semantics. Plugin event guarantees are explicit/idempotent.
52. `core.*`, `project.*`, `channel.*`, `system.*` events are Core-only.
53. Permission grants are version-specific; new permissions require explicit re-approval before migration.
54. Stale health is unknown, not automatically unhealthy. Use TTL/preflight and prefer free checks.
55. Single-admin v0 admin implicitly satisfies all workflow approval roles.
56. Backups include retained packages, prompt artifacts, plugin data and wheelhouse required to reproduce retained runs; recovery key handling remains separate.
57. Audit state changes: actor, action, channel, plugin/version, package hash, before/after metadata, result and correlation ID; never secret values.
58. Pre-publish checks produce typed checklist output and gate publishing/success.
59. External binaries/export paths require approved Tool/Export Location models; never unrestricted PATH/process spawning.
60. Do not migrate existing production systems until the secure thin vertical slice is proven.

## Naming grammar

Canonical machine identifiers are lowercase.

- Plugin/Niche ID: kebab-case — `senior-health-gates`
- Capability: kebab-case with optional owner namespace — `text-generation`, `senior-health/medical-review`
- Contract: kebab/dotted semantic name with optional owner namespace — `project.brief`, `voice.request`
- Event: dot-separated namespace — `elevenlabs.voice-completed`
- Node ID / role ID / variant / credential name: kebab-case
- `yg` and `yg-*` are reserved first-party IDs.
- `core`, `system`, `project`, `channel` are reserved IDs/namespaces.
- A niche owns its namespace. A compatible `type: niche` plugin may register inside it only through explicit delegation/authorization.
- Conflicting namespaced capability/contract registration fails unless explicit registry version/provider rules permit coexistence.
- Never use underscore capability names where canonical kebab-case is required.
- Executable schema regexes are authoritative; documentation examples must conform.

## Source of truth

- Plugin manifest shape → `schemas/plugin.schema.json`
- Workflow shape → `schemas/workflow.schema.json`
- Effective trust → DB/admin grant bound to package SHA-256
- Package identity → semantic version + SHA-256
- Channel plugin pin/enablement → Channel assignment DB
- Routing → Channel Routing DB
- Settings → DB + settings schema version; defaults only in settings schema
- Secrets/OAuth → encrypted stores
- Prompts → versioned prompt registry/artifacts + Channel overrides
- Run configuration → immutable run snapshot
- Actual provider/model/options/usage → node-run history
- Artifacts → Artifact Store + DB metadata
- Scratch → ephemeral data-root job directories

## Never do this

- Never modify Senior Health / MasterProduction while implementing YG-PLUG-PLAY unless explicitly requested.
- Never rewrite Core for a feature that belongs in a plugin, prompt capability, contract or route.
- Never let a plugin self-approve trust or permissions.
- Never trust version identity without package SHA-256.
- Never import/execute plugin code during static validation.
- Never run executable plugin code inside Core.
- Never pass Core DB/master key/unrelated secrets to workers.
- Never claim same-user subprocesses are a hostile-code sandbox.
- Never store mutable production data inside Git.
- Never expose unrestricted filesystem, SQL, network, subprocess or secret access.
- Never inject credentials into unbound domains or forward auth across cross-domain redirects.
- Never use `eval()` for workflow conditions/templates/rules.
- Never hard-code Claude, Gemini, ElevenLabs, Muse, HeyGen, YouTube or another provider into niche/domain workflow logic.
- Never let plugin settings silently alter workflow routing.
- Never silently change plugin/niche/route/prompt/model during a run.
- Never delete package/runtime versions referenced by active or paused runs.
- Never overwrite artifact history after human edit/re-run.
- Never invent undefined aliases such as `approved-script`.
- Never allow unbounded cycles, retries, map retries or nested capability recursion.
- Never conflate provider retry, fallback and node retry.
- Never send large media as base64 JSON-RPC.
- Never allow a plugin to choose another Channel ID or arbitrary artifact path.
- Never log plaintext secrets, auth headers, cookies or tokens; redact encoded variants where feasible.
- Never mark success if a required pre-publish/compliance gate failed or was bypassed without audited override.
- Never start paid-provider integration without spend/token caps and mock/dry-run.
- Never bypass approvals, provenance, audit or budget checks for publishing/scheduling.
- Never create a new architecture version for a schema-level bug unless architecture itself changes.

## Phase discipline

Phase 0: schemas, semantic validators, DB/migrations, permission catalogue, auth skeleton, repository/service interfaces and fake Core SDK.

Phase 1a: one trusted end-to-end vertical slice using real interfaces, simple implementations, minimal durability and purpose-aware routing verification.

Phase 1b: ZIP/security/proxy/redaction/environment hardening.

Later phases add real providers/Prompt Executor depth, version migration, advanced durable workflow, publishing/operations and stronger sandboxing.

Preserve later-phase interfaces when needed, but do not prematurely implement whole later subsystems.

## Agent completion checklist

Before declaring completion:

1. Validate changed JSON/JSON Schema and run relevant tests.
2. Check naming grammar and reserved namespaces.
3. Check Channel scoping and frozen-run semantics.
4. Check permission/trust/credential boundaries.
5. Ensure no mutable runtime data was added under Git.
6. Ensure static validation imports no plugin code.
7. Check contracts/selectors for dangling references.
8. Check loops/retries/fallbacks are bounded and distinct.
9. Check audit/provenance for state-changing actions.
10. State what was implemented, intentionally deferred and any remaining limitation.


## Coding conventions

- Python: target Python 3.12+, type-hint public interfaces, keep modules small and dependency direction explicit.
- Prefer dataclasses/Pydantic-style boundary models and pure functions for validators; keep side effects behind service/repository interfaces.
- JSON/JSON Schema: Draft 2020-12, UTF-8, deterministic formatting, explicit `additionalProperties` policy, reusable definitions instead of duplicated regexes.
- Public IDs and schema examples must pass the canonical naming validators.
- Filesystem paths are `pathlib.Path` internally; never concatenate untrusted paths or rely on the process CWD for mutable data.
- No arbitrary shell strings. External process execution goes through the approved Tool/worker boundary with argument arrays.
- Never use `eval()`/`exec()` for workflow, templates, rules or plugin validation.
- Tests accompany schema/semantic behavior. Every security regression gets a negative test.
- Validation code must be deterministic and side-effect free: no imports from plugin packages, network calls, subprocesses or writes.
- Core code never imports niche/provider implementation modules. Depend on contracts/capabilities/interfaces.
- Workers never open Core SQLite directly. All supported state/artifact/secret access goes through scoped Core interfaces.
- Logging is structured and redacted. Never log secret values, Authorization headers, cookies, OAuth tokens or raw credential material.
- Workflows contain capability IDs only; concrete provider/plugin IDs belong in Channel routing.
- Keep Phase boundaries explicit: preserve future interfaces, but do not prematurely implement later-phase subsystems.
