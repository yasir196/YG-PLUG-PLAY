# YG-PLUG-PLAY --- Frozen Architecture & Production Blueprint v5

**Status:** Phase-0 architecture freeze candidate\
**Supersedes:** v1, v2, v3 and v4\
**Plugin API:** `v0 experimental`\
**Initial deployment:** Windows local-first, single-machine\
**Executable plugin trust:** Admin-approved trusted code only in v0\
**Primary principle:** **Install features; do not rewrite the
pipeline.**

> v5 closes the six Phase-0 blockers found in the v4 review, fixes the
> official workflow approval path, and adds the missing
> production-facing capability families without forcing all of them into
> the first implementation. After this document, architecture should be
> treated as frozen for Phase 0 unless implementation proves a blocker.

------------------------------------------------------------------------

# 1. Architecture Freeze Decision

Phase 0 may begin after adopting this specification.

The six pre-code blockers are resolved as follows:

1.  Separate naming grammars are defined for IDs, capabilities,
    contracts and events.
2.  Trust is an admin/platform grant, never self-declared authority from
    a manifest.
3.  LLM routing is purpose-aware, so Research, Script, SEO and Medical
    Review can use different providers/models.
4.  Manual-review and final-approval both publish approved script
    generations; downstream uses an approved selector.
5.  Minimal durable execution is part of Phase 1a, so waiting approvals
    survive Core restarts.
6.  Code/install directories and mutable application data are physically
    separated.

Remaining advanced features are roadmap items and should not delay the
first working vertical slice.

------------------------------------------------------------------------

# 2. Canonical Product Model

``` text
YG-PLUG-PLAY
│
├── Core
│   ├── API/Auth
│   ├── Channels/Projects/Runs
│   ├── Plugin Installer/Registry
│   ├── Trust/Permissions
│   ├── Worker Runtime
│   ├── Prompt Executor
│   ├── Contract/Capability Registries
│   ├── Workflow Engine
│   ├── Purpose-aware Router
│   ├── Secrets/Credential Proxy
│   ├── Artifact Store
│   ├── Plugin Data
│   ├── Jobs/Provider Jobs
│   ├── External Tool Registry
│   ├── Publishing/Triggers
│   ├── Cost/Quota/Budgets
│   ├── Events/Notifications
│   └── Audit/Observability
│
├── yg-standard-contracts
├── Niche Template Library
├── Central Plugin Library
└── Channels
    └── Projects
        └── Runs
```

**Niche = template. Channel = runtime workspace. Project = content unit.
Run = one execution attempt/version.**

------------------------------------------------------------------------

# 3. Naming Grammars --- Canonical

Different registry objects intentionally use different grammars.

## 3.1 Plugin and Niche IDs

Kebab-case only:

``` regex
^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$
```

Valid:

``` text
claude
senior-health
capcut-export
```

Invalid:

``` text
SeniorHealth
senior_health
project.brief
```

## 3.2 Capability IDs

Optional owner namespace + kebab-case capability:

``` regex
^(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*/)?[a-z][a-z0-9]*(?:-[a-z0-9]+)*$
```

Examples:

``` text
text-generation
deep-research
script-generation
image-generation
senior-health/medical-review
```

## 3.3 Contract IDs

Optional owner namespace, with dot-separated semantic parts:

``` regex
^(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*/)?[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)*$
```

Examples:

``` text
project.brief
voice.request
audio.asset
image.request.collection
senior-health/medical-review
video.performance
```

Contract version is separate:

``` json
{"contract": "script", "version": "^1.0"}
```

## 3.4 Event IDs

Dot-separated namespace:

``` regex
^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+$
```

Examples:

``` text
elevenlabs.voice-completed
core.run-started
project.published
```

Reserved event namespaces:

``` text
core.*
system.*
project.*
channel.*
```

Only Core may emit reserved events.

------------------------------------------------------------------------

# 4. Namespace Ownership

A Namespace Registry prevents collisions.

Rules:

-   Niche ID owns its domain namespace.
-   Plugin ID owns its plugin namespace.
-   Plugin and Niche IDs cannot collide.
-   Reserved IDs include `core`, `system`, `project`, `channel`, `yg`.
-   Installation fails on ownership conflict.
-   Standard global contracts/capabilities are owned by the first-party
    `yg-standard-contracts` package.

------------------------------------------------------------------------

# 5. Trust Is a Platform Grant

A plugin **cannot make itself trusted** by writing `"trust": "trusted"`.

Manifest may request:

``` json
{"requested_trust": "trusted"}
```

but the authoritative trust level is stored by Core after administrator
approval.

Canonical state:

``` text
plugin_trust_grants
```

Example:

``` json
{
  "plugin_id": "claude",
  "plugin_version": "1.2.0",
  "trust_level": "trusted",
  "granted_by": "admin-user-id",
  "granted_at": "2026-10-04T00:00:00Z"
}
```

## v0 trust policy

  ------------------------------------------------------------------------
  Package                   External source allowed? Execution
  --------------------- ---------------------------- ---------------------
  Python executable     Yes, but only after explicit Trusted only
  plugin                       trusted-code approval 

  Config-only plugin      Yes, after schema/resource No plugin Python
                                          validation executes

  Niche template        Yes, after static validation Declarative only
  ------------------------------------------------------------------------

Config-only packages are safer but are still treated as untrusted
**data** until validated. Templates/rules cannot execute arbitrary
Python.

Future restricted/untrusted execution requires an OS/container sandbox
and is not claimed in v0.

------------------------------------------------------------------------

# 6. Windows-First Deployment and Directory Separation

Code and mutable data must not share the repository/install tree.

## Install/code directory

Example:

``` text
C:\Program Files\YG-PLUG-PLAY\
```

or developer checkout:

``` text
D:\dev\YG-PLUG-PLAY\
```

Contains application code and immutable shipped resources only.

## Default mutable data directory

``` text
%LOCALAPPDATA%\YG-PLUG-PLAY\
```

Example layout:

``` text
%LOCALAPPDATA%\YG-PLUG-PLAY\
├── db\
├── packages\
├── artifacts\
├── plugin-data\
├── runtime\
│   ├── envs\
│   └── scratch\
├── prompts\
├── wheelhouse\
├── exports\
├── backups\
└── logs\
```

The data root is configurable.

Core startup checks/warns if the DB/data root appears inside a
cloud-synced folder such as OneDrive/Dropbox. SQLite DB is not
intentionally placed in a synced folder.

Git ignores runtime/data paths in developer mode.

------------------------------------------------------------------------

# 7. Windows Runtime Rules

v0 Windows implementation should use:

-   DPAPI CurrentUser for protecting the local master-key material;
-   separate recovery key/export procedure;
-   Job Objects with `KILL_ON_JOB_CLOSE` where feasible;
-   retry/backoff for antivirus/file-lock interference;
-   Unicode path tests including Urdu filenames;
-   short generated IDs/paths and long-path-aware APIs;
-   optional `prevent_sleep_while_running` setting using the appropriate
    Windows execution-state API.

The trusted-code limitation still applies: DPAPI CurrentUser does not
create a malicious-same-user sandbox.

------------------------------------------------------------------------

# 8. Channel, Project, Brief and Run

A Channel owns:

-   pinned Niche/version;
-   Projects;
-   plugin assignments/version pins;
-   routing;
-   settings/secrets;
-   workflow;
-   prompt overrides;
-   budgets/quotas;
-   publishing/account links.

A Project is one content-production unit.

Every Project has a typed Project Brief.

Every Project can have multiple Runs.

Every Run owns its own frozen Run Snapshot.

------------------------------------------------------------------------

# 9. Project Brief and Niche Brief Forms

Base contract:

``` json
{
  "contract": "project.brief",
  "version": "1.0.0",
  "data": {
    "title": "",
    "topic": "",
    "goal": "",
    "language": "en",
    "metadata": {}
  }
}
```

A Niche may ship a `brief_form_schema` that extends UI fields without
changing Core.

Example Senior Health fields may include target audience/topic metadata,
but Core does not hard-code them.

------------------------------------------------------------------------

# 10. Run Snapshot

Snapshot records at least:

-   workflow version;
-   Channel routing map;
-   plugin/version pins;
-   Niche/version;
-   effective non-secret settings;
-   prompt/rule artifact IDs and hashes;
-   provider/model options;
-   standard-contract package version;
-   project brief artifact;
-   approved permission/trust state IDs.

Actual provider/model/options for every executed node are additionally
recorded in `workflow_node_runs`, because fallback may change them
during execution.

------------------------------------------------------------------------

# 11. Standard Contracts

`yg-standard-contracts` owns generic cross-plugin
contracts/capabilities.

Examples:

``` text
project.brief
text-generation.request
text-generation.result
research
script
image.request
image.request.collection
image.asset
audio.asset
voice.request
timeline
publish.request
publish.result
video.performance
```

Core understands schema registration/validation, not content-domain
meaning.

------------------------------------------------------------------------

# 12. Prompt-Driven Capabilities

Domain logic can stay in MD/JSON.

Example:

``` json
{
  "capability": "senior-health/medical-review",
  "executor": "prompt",
  "prompt": "prompts/medical-review.md",
  "rules": [
    {"type": "prompt-context", "path": "rules/medical-context.md"},
    {"type": "validator", "path": "rules/medical-output.json"}
  ],
  "uses": {
    "capability": "text-generation",
    "purpose": "senior-health/medical-review"
  },
  "requirements": {
    "supports_json_schema": true
  },
  "input": {"contract": "script", "version": "^1.0"},
  "output": {
    "contract": "senior-health/medical-review",
    "version": "^1.0"
  }
}
```

------------------------------------------------------------------------

# 13. Purpose-Aware LLM Routing --- Critical Rule

Generic provider capability routing must preserve per-task
provider/model choice.

A prompt-driven capability calls:

``` text
text-generation
```

with a **purpose** equal to the calling/domain capability unless
explicitly overridden.

Examples:

``` text
deep-research          → purpose=deep-research
script-generation      → purpose=script-generation
seo-generation         → purpose=seo-generation
senior-health/medical-review → purpose=senior-health/medical-review
```

Channel routes may therefore be:

``` json
[
  {
    "capability": "text-generation",
    "purpose": "deep-research",
    "primary_plugin_id": "gemini",
    "options": {
      "model": "research-model",
      "temperature": 0.2
    }
  },
  {
    "capability": "text-generation",
    "purpose": "script-generation",
    "primary_plugin_id": "claude",
    "options": {
      "model": "strong-writing-model",
      "temperature": 0.7,
      "max_tokens": 8000
    }
  },
  {
    "capability": "text-generation",
    "purpose": "seo-generation",
    "primary_plugin_id": "gemini",
    "options": {
      "model": "fast-model",
      "temperature": 0.3
    }
  }
]
```

## Resolution order

``` text
(capability, exact purpose)
→ (capability, variant)
→ (capability, default)
→ route missing error
```

Purpose takes priority over generic variant/default.

## Effective provider options

``` text
node/prompt-capability explicit allowed overrides
→ route options
→ plugin Channel settings
→ plugin defaults
```

Security/policy caps may only narrow these values.

The exact effective options are recorded per node run.

------------------------------------------------------------------------

# 14. Routing UI --- Two Layers

For prompt-driven tasks, UI must make both decisions visible:

``` text
SCRIPT GENERATION
Domain capability provider:
  senior-health/script-generation → Senior Health Script Prompt package

LLM execution:
  text-generation / purpose=script-generation
  → Claude
  → model X
  fallback → Gemini model Y
```

This avoids confusing domain behavior with infrastructure provider
selection.

------------------------------------------------------------------------

# 15. Provider Feature Flags

Provider capability declarations expose supported features:

``` json
{
  "capability": "text-generation",
  "features": {
    "supports_json_schema": true,
    "supports_image_input": true,
    "supports_web_search": false,
    "supports_streaming": true,
    "supports_token_count": true,
    "max_context_tokens": 200000
  }
}
```

Route validation checks required features before saving/starting.

------------------------------------------------------------------------

# 16. Text Generation Contract

Request supports:

``` json
{
  "messages": [],
  "response_schema": null,
  "tools": [],
  "max_tokens": 4000,
  "temperature": 0.2,
  "attachments": [],
  "metadata": {}
}
```

Tools may include:

``` text
web-search
```

Attachments may contain artifact handles for multimodal tasks.

Result:

``` json
{
  "text": "",
  "json": null,
  "citations": [],
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0
  },
  "finish_reason": ""
}
```

------------------------------------------------------------------------

# 17. Template Engine

v0 chooses **Jinja2 `SandboxedEnvironment`** with a deliberately small
allowlist of filters/functions.

Forbidden:

-   arbitrary attribute traversal;
-   arbitrary imports;
-   filesystem calls;
-   shell/process calls;
-   dynamic Python execution.

Template context is explicit and typed.

------------------------------------------------------------------------

# 18. Rule Types

Two rule classes are official.

## Prompt-context rules

Declarative text/data injected into a dedicated prompt section.

Examples:

-   style instructions;
-   compliance guidance;
-   niche facts;
-   output expectations.

## Validator rules

Deterministic post-output checks.

Supported v0 validators may include:

``` text
JSON Schema
JSONLogic
regex
required fields
word-count/range
banned terms
required terms/disclaimer
```

Validator failure follows node policy; it does not silently pass.

------------------------------------------------------------------------

# 19. Structured Output Repair

If provider returns invalid JSON/structured output:

``` text
Validate
↓
If invalid:
  repair prompt with validation errors
↓
Maximum 1–2 repair attempts
↓
Then node failure policy
```

Repair attempts are separate from provider fallback attempts and are
recorded/costed.

------------------------------------------------------------------------

# 20. Research, Web Content and Prompt Injection

Research content is treated as untrusted external data.

Prompt Executor:

-   keeps system/rule instructions separate from retrieved content;
-   wraps retrieved material in explicit delimiters/data blocks;
-   tells model not to follow instructions found in retrieved content;
-   preserves citations/source metadata where available.

This is defense-in-depth, not a perfect prompt-injection guarantee.

------------------------------------------------------------------------

# 21. Long Generation Pattern

Long outputs may use:

1.  section-wise generation, preferred where a workflow can define
    sections;
2.  controlled continuation when provider finish reason indicates
    length.

Every continuation is linked to the same logical node generation and
captured in usage/cost.

------------------------------------------------------------------------

# 22. Token Counting

Provider may expose:

``` text
count-tokens
```

or `supports_token_count`.

If unavailable, Core uses conservative provider/model estimator.

Budget preflight treats configured `max_tokens` as output upper bound.

------------------------------------------------------------------------

# 23. LLM Result Cache

Optional cache key includes:

``` text
rendered prompt hash
input artifact hashes
provider
model
effective options
tool configuration
response schema
```

Cache is opt-in per capability/node because freshness-sensitive research
should not blindly reuse stale results.

Cache hit is recorded in node run and cost accounting.

------------------------------------------------------------------------

# 24. Credentials and Network Permissions

Credential binding is authoritative for credential injection.

Example:

``` json
{
  "credentials": [
    {
      "name": "api-key",
      "mode": "proxy",
      "inject": {"type": "header", "name": "xi-api-key"},
      "allowed_domains": ["api.elevenlabs.io"]
    }
  ]
}
```

To remove duplication:

-   `credentials[].allowed_domains` automatically grants only the
    network destinations needed **for that credential-bound proxy
    path**.
-   Extra unauthenticated/CDN domains are separately requested via
    `network.domains:<domain>`.
-   `credential.use:<name>` is derived from an approved credential
    binding and does not need to be duplicated in manifest permissions.
-   `credential.raw:<name>` remains an exceptional explicit permission.

------------------------------------------------------------------------

# 25. SDK Reverse Proxy

Per-worker authenticated local reverse proxy supports:

-   ordinary HTTP;
-   streaming HTTP/SSE pass-through;
-   configurable route/provider response limits;
-   credential injection only on bound domains;
-   signed/CDN download URLs without credential forwarding when network
    domain is approved.

Cross-domain redirects never carry the original credential.

## WebSocket

v0 does **not** require generic provider WebSocket proxying.

If a provider feature such as realtime TTS requires WebSocket, the
plugin declares that requirement and the feature is marked unsupported
until a dedicated authenticated WS proxy is implemented. Normal
non-realtime TTS remains usable.

------------------------------------------------------------------------

# 26. SSRF and Core API

Proxy blocks loopback/private/link-local/reserved upstreams by default.

Core FastAPI:

-   binds to `127.0.0.1` by default;
-   authenticates private endpoints;
-   validates Host;
-   uses strict CORS;
-   uses CSRF protection;
-   does not treat localhost as authentication.

Worker RPC/proxy tokens are not browser/admin API tokens.

------------------------------------------------------------------------

# 27. Provider Jobs

Long-running remote jobs are first-class.

Examples:

``` text
avatar generation
video generation
long render
provider-side batch job
```

Canonical lifecycle:

``` text
submit
→ provider_job_id stored
→ polling schedule
→ running/waiting
→ completed/failed/cancelled
→ result imported
```

`provider_jobs` records:

-   provider/plugin/version;
-   Channel/Project/Run/node;
-   external job ID;
-   status;
-   next poll time;
-   attempts;
-   result metadata;
-   usage;
-   cancellation state.

Local-first v0 prefers polling. Webhooks can be added later where
deployable.

Core restart reloads outstanding provider jobs and resumes polling.

------------------------------------------------------------------------

# 28. Worker Concurrency

Worker identity is scoped to:

``` text
plugin + version + Channel
```

v0 default:

-   worker process handles one active capability call at a time unless
    plugin explicitly declares async-safe concurrency;
-   Core can maintain a small worker pool per tuple when needed;
-   pool/concurrency has hard limits;
-   map concurrency is a scheduler limit, not a promise that one process
    handles four calls simultaneously.

No worker serves two Channels.

------------------------------------------------------------------------

# 29. Artifact Inputs and Windows Hardlinks

Large inputs use scratch-relative handles.

Preferred materialization order:

1.  safe hardlink when same volume and artifact is immutable;
2.  otherwise copy.

Because hardlinks share content, Core records input hash before
execution and verifies it afterward. If worker mutates an input, job
fails and artifact integrity incident is logged.

Workers should be instructed to treat `inputs/` as immutable; OS
read-only flags alone are not treated as security.

Outputs always go to `outputs/`.

------------------------------------------------------------------------

# 30. Artifact Selector Semantics

## `$run` namespace

Reserved selector namespace for immutable run inputs:

``` json
{"from": "$run.project-brief"}
```

Other future `$run.*` entries must be explicitly registered.

## `from`

``` json
{"from": "medical-review.review"}
```

means:

> latest successful generation of that node output in the current Run.

This is important for repeated loop nodes.

## `latest`

``` json
{
  "latest": "script",
  "among": ["script.script", "revision.script"]
}
```

returns the latest successful matching generation.

## `approved`

``` json
{"approved": "script"}
```

returns the latest approval decision in this Run whose approved artifact
satisfies contract `script`.

This is the canonical downstream selector after multiple possible
approval gates.

------------------------------------------------------------------------

# 31. Human Editing

Human approval may include an `edit` action.

Editing:

``` text
open artifact
→ user edits
→ Core creates NEW artifact generation
→ original remains immutable
→ actor=human
→ diff stored
→ approval can target edited generation
```

Example:

``` json
{
  "actions": {
    "approve": {"kind": "approve", "next": "media-planning"},
    "edit": {"kind": "edit", "next": "$self"},
    "request-revision": {"kind": "request-revision", "next": "revision"},
    "reject": {"kind": "reject", "next": "end-rejected"}
  }
}
```

Artifact review UI must support at least:

-   script text/diff;
-   image grid;
-   audio player;-   basic timeline metadata/preview as implementation matures.

------------------------------------------------------------------------

# 32. Loop Counters and Human Reset

Automatic loop counters must not block explicit human-requested
revision.

Example:

``` json
{
  "loop_control": {
    "counter": "medical-auto-revisions",
    "max_attempts": 3,
    "on_exhausted": "manual-review",
    "reset_on": ["human-request-revision"]
  }
}
```

Alternative implementations may track automatic and human revision
counters separately. The key rule is: a human request for revision must
be able to execute at least one new revision rather than instantly
re-triggering exhaustion.

------------------------------------------------------------------------

# 33. Minimal Durable Execution Is Phase 1a

Phase 1a stores durable state for:

``` text
Run
node state
waiting approval
next node
loop counters
terminal state
```

Core restart must reload:

-   running-but-interrupted nodes as recoverable/failed according to
    node policy;
-   waiting approvals unchanged;
-   pending nodes;
-   outstanding provider jobs once provider jobs are implemented.

Phase 3 adds advanced durability:

-   map item reconciliation;
-   parallel branch reconciliation;
-   idempotency recovery;
-   partial item re-run.

------------------------------------------------------------------------

# 34. Approval Nodes --- Corrected

Both automatic-success and manual-review approval paths publish an
approved script.

Example manual approval:

``` json
{
  "id": "manual-review",
  "type": "human-approval",
  "inputs": {
    "script": {
      "latest": "script",
      "among": ["script.script", "revision.script"]
    },
    "review": {"from": "medical-review.review"}
  },
  "approval": {
    "roles": ["channel-manager"],
    "artifact": {
      "latest": "script",
      "among": ["script.script", "revision.script"]
    },
    "actions": {
      "approve": {"kind": "approve", "next": "media-planning"},
      "edit": {"kind": "edit", "next": "$self"},
      "request-revision": {"kind": "request-revision", "next": "revision"},
      "reject": {"kind": "reject", "next": "end-rejected"}
    },
    "timeout_hours": 120,
    "on_timeout": {
      "action": "notify-and-wait",
      "notify_roles": ["admin"]
    }
  },
  "outputs": {
    "approved-script": {
      "contract": "script",
      "version": "^1.0"
    }
  }
}
```

Final approval publishes the same typed output.

Downstream does **not** refer to one approval node by name:

``` json
{
  "script": {"approved": "script"}
}
```

Therefore both paths work.

------------------------------------------------------------------------

# 35. Corrected Core Workflow Skeleton

``` json
{
  "id": "main-production",
  "version": 10,
  "start": "research",
  "nodes": [
    {
      "id": "research",
      "type": "capability",
      "capability": "deep-research",
      "inputs": {
        "brief": {"from": "$run.project-brief"}
      },
      "outputs": {
        "research": {"contract": "research", "version": "^1.0"}
      },
      "next": "script"
    },
    {
      "id": "script",
      "type": "capability",
      "capability": "script-generation",
      "inputs": {
        "brief": {"from": "$run.project-brief"},
        "research": {"from": "research.research"}
      },
      "outputs": {
        "script": {"contract": "script", "version": "^1.0"}
      },
      "next": "medical-review"
    },
    {
      "id": "medical-review",
      "type": "capability",
      "capability": "senior-health/medical-review",
      "inputs": {
        "script": {
          "latest": "script",
          "among": ["script.script", "revision.script"]
        }
      },
      "outputs": {
        "review": {
          "contract": "senior-health/medical-review",
          "version": "^1.0"
        }
      },
      "next": "review-decision"
    },
    {
      "id": "review-decision",
      "type": "condition",
      "inputs": {
        "review": {"from": "medical-review.review"}
      },
      "expression": {
        "==": [{"var": "review.passed"}, true]
      },
      "true_next": "final-approval",
      "false_next": "revision"
    },
    {
      "id": "revision",
      "type": "capability",
      "capability": "script-revision",
      "inputs": {
        "script": {
          "latest": "script",
          "among": ["script.script", "revision.script"]
        },
        "review": {"from": "medical-review.review"}
      },
      "outputs": {
        "script": {"contract": "script", "version": "^1.0"}
      },
      "loop_control": {
        "counter": "medical-auto-revisions",
        "max_attempts": 3,
        "on_exhausted": "manual-review",
        "reset_on": ["human-request-revision"]
      },
      "next": "medical-review"
    },
    {
      "id": "manual-review",
      "type": "human-approval",
      "inputs": {
        "script": {
          "latest": "script",
          "among": ["script.script", "revision.script"]
        },
        "review": {"from": "medical-review.review"}
      },
      "approval": {
        "roles": ["channel-manager"],
        "artifact": {
          "latest": "script",
          "among": ["script.script", "revision.script"]
        },
        "actions": {
          "approve": {"kind": "approve", "next": "media-planning"},
          "edit": {"kind": "edit", "next": "$self"},
          "request-revision": {"kind": "request-revision", "next": "revision"},
          "reject": {"kind": "reject", "next": "end-rejected"}
        }
      },
      "outputs": {
        "approved-script": {"contract": "script", "version": "^1.0"}
      }
    },
    {
      "id": "final-approval",
      "type": "human-approval",
      "inputs": {
        "script": {
          "latest": "script",
          "among": ["script.script", "revision.script"]
        }
      },
      "approval": {
        "roles": ["channel-manager", "producer"],
        "artifact": {
          "latest": "script",
          "among": ["script.script", "revision.script"]
        },
        "actions": {
          "approve": {"kind": "approve", "next": "media-planning"},
          "edit": {"kind": "edit", "next": "$self"},
          "request-revision": {"kind": "request-revision", "next": "revision"},
          "reject": {"kind": "reject", "next": "end-rejected"}
        }
      },
      "outputs": {
        "approved-script": {"contract": "script", "version": "^1.0"}
      }
    },
    {
      "id": "media-planning",
      "type": "capability",
      "capability": "media-planning",
      "inputs": {
        "script": {"approved": "script"}
      },
      "outputs": {
        "image-requests": {
          "contract": "image.request.collection",
          "version": "^1.0"
        },
        "voice-request": {
          "contract": "voice.request",
          "version": "^1.0"
        }
      },
      "next": "media-stage"
    },
    {
      "id": "media-stage",
      "type": "parallel",
      "branches": ["generate-images", "generate-voice"],
      "join": "media-join"
    },
    {
      "id": "generate-images",
      "type": "map",
      "inputs": {
        "requests": {"from": "media-planning.image-requests"}
      },
      "items_from": "inputs.requests.items",
      "capability": "image-generation",
      "concurrency": 4,
      "failure_policy": {
        "mode": "retry-failed-items",
        "max_attempts": 3,
        "on_exhausted": "media-failure-review"
      },
      "outputs": {
        "images": {
          "contract": "image.asset",
          "version": "^1.0",
          "collection": {
            "allow_partial": true,
            "min_success_ratio": 0.95
          }
        }
      }
    },
    {
      "id": "generate-voice",
      "type": "capability",
      "capability": "voice-generation",
      "inputs": {
        "request": {"from": "media-planning.voice-request"}
      },
      "outputs": {
        "audio": {"contract": "audio.asset", "version": "^1.0"}
      }
    },
    {
      "id": "media-failure-review",
      "type": "human-approval",
      "inputs": {
        "failed-items": {"from": "generate-images.failed-items"},
        "successful-items": {"from": "generate-images.images"}
      },
      "branch_context": "generate-images",
      "approval": {
        "roles": ["producer", "channel-manager"],
        "actions": {
          "retry-failed": {"kind": "request-revision", "next": "generate-images"},
          "accept-partial": {"kind": "approve", "next": "media-join"},
          "reject": {"kind": "reject", "next": "end-rejected"}
        }
      }
    },
    {
      "id": "media-join",
      "type": "join",
      "branches": ["generate-images", "generate-voice"],
      "policy": {
        "require": "all-successful-or-approved-partial",
        "on_terminal_reject": "cancel-other-branches"
      },
      "next": "timeline"
    },
    {
      "id": "timeline",
      "type": "capability",
      "capability": "timeline-build",
      "inputs": {
        "script": {"approved": "script"},
        "images": {"from": "generate-images.images"},
        "audio": {"from": "generate-voice.audio"}
      },
      "outputs": {
        "timeline": {"contract": "timeline", "version": "^1.0"}
      },
      "next": "pre-publish-check"
    },
    {
      "id": "pre-publish-check",
      "type": "capability",
      "capability": "pre-publish-check",
      "inputs": {
        "timeline": {"from": "timeline.timeline"},
        "brief": {"from": "$run.project-brief"}
      },
      "next": "end-success"
    },
    {
      "id": "end-success",
      "type": "end",
      "status": "success"
    },
    {
      "id": "end-rejected",
      "type": "end",
      "status": "rejected"
    }
  ]
}
```

Phase 1a implements only the linear/condition/approval/bounded-cycle
subset. `parallel/map/join` are Phase 3 target semantics.

------------------------------------------------------------------------

# 36. Parallel/Map Semantics

When Phase 3 arrives:

-   map item attempt counters are item-scoped;
-   `retry-failed` creates another attempt only for failed items and is
    itself bounded;
-   failure-review receives failed item artifacts/errors;
-   branch context remains attached when routing through review nodes;
-   terminal rejection cancels cancellable sibling branches;
-   already-incurred provider usage remains recorded;
-   non-cancellable remote jobs may finish but their results are marked
    unused unless explicitly recovered.

Collection contracts can specify:

``` json
{
  "allow_partial": true,
  "min_items": 1,
  "min_success_ratio": 0.95
}
```

Downstream static validation checks whether partial collections are
acceptable.

------------------------------------------------------------------------

# 37. Route Retry/Fallback

Route contains provider retry and fallback triggers.

Rate limit:

-   respects `Retry-After`;
-   exponential backoff;
-   jitter;
-   bounded attempts.

Fallback normally triggers only for technical failures:

``` text
timeout
provider-unavailable
rate-limit exhausted
network failure
```

Not automatically for:

``` text
semantic rejection
validator failure
medical/policy failure
```

Sensitive nodes may require approval after fallback.

------------------------------------------------------------------------

# 38. Health Preflight

Health state has TTL.

`unknown` may execute after lightweight preflight.

Preflight policy prefers free/local checks.

A paid provider call is not made merely to turn `unknown` into `healthy`
unless explicitly configured.

Successful real calls refresh health.

------------------------------------------------------------------------

# 39. Publishing Capability

Production roadmap includes a generic:

``` text
publishing
```

or provider-specific compatible capabilities such as:

``` text
youtube-publish
```

Standard publishing request may contain:

``` text
video artifact
title
description
tags
thumbnail
privacy status
scheduled publish time
playlist
synthetic/altered-content disclosure fields
niche-required disclaimers/checklist result
```

Publishing result records remote content ID/URL/status.

OAuth/account credentials are Channel-scoped.

Pre-publish checks run before publish and can be supplied by
Niche/config plugins.

------------------------------------------------------------------------

# 40. Quota Units and Multi-Unit Budgets

Budgeting is not USD-only.

Supported units include:

``` text
currency
tokens
credits
characters
seconds/minutes
provider quota units
API requests
```

Example: YouTube API quota is tracked as credential-scoped provider
quota units rather than pretending it is a dollar cost.

Provider quota costs are configurable/versioned because external
providers can change them.

------------------------------------------------------------------------

# 41. Triggers and Scheduling

Workflow Engine remains the production orchestrator.

Events do not directly become hidden production pipelines.

Runs may be created by explicit Trigger records:

``` text
manual
schedule
batch
external-approved trigger
```

Examples:

``` text
daily analytics sync
weekly content batch
scheduled publish
periodic comments fetch
```

Trigger creates an auditable Run/Job using a defined workflow/version.

------------------------------------------------------------------------

# 42. Batch Projects and Content Calendar

Platform roadmap includes:

-   import/create many briefs;
-   create many Projects;
-   queue runs with concurrency limits;
-   content calendar;
-   scheduled publish date;
-   batch pause/cancel;
-   per-item status.

Duplicate-topic detection can warn using previous Channel
Projects/artifacts.

------------------------------------------------------------------------

# 43. External Tool Registry

Local tools are not accessed through arbitrary PATH/shell.

Core owns Tool Registry.

Example approved tools:

``` text
ffmpeg
ffprobe
capcut-handoff-helper
```

Plugin/capability requests:

``` text
process.spawn:ffmpeg
```

Core resolves an approved binary path and enforces:

-   argument policy where possible;
-   timeout;
-   working directory;
-   resource/job association;
-   logs;
-   no arbitrary shell string.

------------------------------------------------------------------------

# 44. Named Export Locations

Scratch is not enough for final handoffs.

Admin can define named export roots:

``` text
capcut-drafts
youtube-ready
archive
```

Permission:

``` text
filesystem.export:capcut-drafts
```

Plugins never receive arbitrary unrestricted filesystem paths through
normal APIs.

Core performs/mediates export.

------------------------------------------------------------------------

# 45. Notifications

Notification is a capability/service family.

Initial useful providers:

``` text
Windows toast
email plugin
Telegram plugin
```

Approval queue can notify:

``` text
approval requested
approval reminder
provider job failed
run completed
publish completed/failed
```

Notification delivery does not decide production order.

------------------------------------------------------------------------

# 46. Analytics Feedback Loop

Published content can produce:

``` text
video.performance
```

Artifacts/contracts containing:

-   views;
-   CTR;
-   watch time;
-   AVD;
-   retention;
-   comments/engagement;
-   publication metadata.

Future topic/thumbnail/content decision plugins consume these typed
artifacts through explicit workflows, not hidden event side effects.

------------------------------------------------------------------------

# 47. Dry-Run / Mock Mode

Workflow run mode:

``` text
live
dry-run
mock
```

Dry/mock can:

-   validate graph/routes;
-   estimate cost/quota;
-   use mock provider outputs;
-   avoid paid network calls;
-   exercise Prompt Executor/contracts.

This is mandatory for developer testing before production provider
calls.

------------------------------------------------------------------------

# 48. Prompt Evaluation

Prompt changes are versioned production changes.

Prompt Evaluation tool should compare old/new prompt versions against
sample briefs:

-   output;
-   validator score;
-   human rating;
-   token/cost estimate;
-   structured diff.

Promotion of a prompt version to Channel default is auditable.

------------------------------------------------------------------------

# 49. Core Updates

Core update lifecycle:

``` text
check compatibility
→ backup DB/config
→ verify package/signature policy
→ run Core DB migration
→ validate installed plugin_api compatibility
→ switch version
→ health/startup check
→ rollback if safe
```

Core update and plugin update are separate lifecycle systems.

------------------------------------------------------------------------

# 50. Channel Export/Import

Channel export may include:

-   Channel config;
-   pinned Niche;
-   workflow/routing;
-   plugin assignments;
-   prompts;
-   selected artifacts/projects;
-   optionally encrypted credential references or re-link instructions.

Secrets are excluded by default.

Import validates plugin/niche availability and shows unresolved
dependencies.

------------------------------------------------------------------------

# 51. Observability and Network Loss

Operational dashboard should expose:

-   failure rate by provider/capability;
-   latency;
-   cost/quota;
-   worker crashes;
-   provider job status;
-   disk use;
-   queue depth.

Logs have rotation/retention.

Network failures can transition retryable jobs to:

``` text
waiting-for-network
```

rather than immediately treating every outage as permanent failure.

------------------------------------------------------------------------

# 52. Asset Provenance

Generated media metadata records:

-   provider;
-   plugin/version;
-   model;
-   creation timestamp;
-   prompt/input hash;
-   source artifacts;
-   known license/terms metadata or policy reference;
-   synthetic/generated flag.

This supports publishing disclosures, monetization review and audit.

------------------------------------------------------------------------

# 53. AI Disclosure / Pre-Publish Checklist

A pre-publish capability can evaluate:

-   altered/synthetic media disclosure requirements;
-   niche disclaimers;
-   title/description requirements;
-   missing thumbnail;
-   required metadata;
-   policy checklist.

It produces a typed checklist artifact.

Publishing can require checklist PASS or human override with audit.

------------------------------------------------------------------------

# 54. Phase Plan --- Frozen

## Phase 0 --- Schemas and foundations

Build:

-   repository skeleton;
-   separate data-root abstraction;
-   naming validators;
-   plugin schema;
-   workflow schema;
-   contract/capability schema;
-   Core DB schema;
-   `yg-standard-contracts`;
-   Channel/Project/Run models;
-   trust-grant model;
-   purpose-aware route schema;
-   Demo Niche + Demo Provider;
-   Prompt Executor interfaces.

## Phase 1a --- Fast vertical slice + minimal durability

The Demo must deliberately test the largest architectural assumption:

``` text
Demo config-only Niche prompt capability
        ↓
Prompt Executor
        ↓
text-generation / purpose=demo-writing
        ↓
Demo text-generation provider
```

Implement:

-   central install;
-   trusted executable approval;
-   config-only package;
-   enable/configure;
-   project brief;
-   purpose-aware route;
-   Prompt Executor minimal implementation;
-   worker RPC;
-   scoped artifacts;
-   basic Secrets interface;
-   basic Core API auth;
-   linear workflow;
-   condition;
-   bounded cycle;
-   human approval;
-   **durable Run/node/approval state**;
-   logs/SSE progress;
-   Run Snapshot.

This brings the Prompt Executor forward from old Phase 2 because it is
the central product hypothesis.

## Phase 1b --- Security hardening

Add:

-   full ZIP hardening;
-   credential-domain binding;
-   authenticated SDK proxy;
-   SSRF/redirect protection;
-   environment hardening tests;
-   redaction;
-   dependency/uv/wheel enforcement;
-   Host/CORS/CSRF hardening tests.

Minimal single-version upgrade permission re-approval may be implemented
here if upgrades are introduced. Full side-by-side lifecycle remains
Phase 4.

## Phase 2 --- Real LLM/provider features

Add:

-   Claude/Gemini text-generation providers;
-   provider feature flags;
-   route model/options;
-   web-search tool contract;
-   multimodal attachments;
-   JSON repair;
-   token counting;
-   LLM cache;
-   prompt evaluation;
-   real niche prompt/rule packages.

## Phase 3 --- Media/durable production

Add:

-   map/parallel/join;
-   item reconciliation;
-   cancel/partial rerun;
-   provider jobs/polling;
-   image/voice/avatar;
-   External Tool Registry;
-   ffmpeg;
-   export locations;
-   artifact review UI.

## Phase 4 --- Lifecycle/versioning

Add:

-   side-by-side plugin versions;
-   version permission re-approval;
-   migration/rollback observation;
-   job drain;
-   settings/private-data migrations;
-   Niche upgrade diff;
-   Channel clone/archive/delete;
-   Channel export/import.

## Phase 5 --- Publishing and operations

Add:

-   YouTube OAuth/publishing;
-   pre-publish checklist;
-   triggers/schedules;
-   batch projects/content calendar;
-   notifications;
-   analytics feedback;
-   multi-unit budgets/quotas;
-   observability;
-   backup/restore;
-   Core updater.

## Phase 6 --- Restricted/untrusted plugin security

Evaluate stronger Windows sandboxing/container deployment.

Only after implementation evidence:

``` text
Plugin API v0 → v1
```

------------------------------------------------------------------------

# 55. Phase 0 Exit Criteria

Phase 0 is complete only when:

1.  naming validators accept every official example and reject
    incompatible forms;
2.  trust is DB/admin-owned, not manifest-owned;
3.  purpose-aware routing schema can express Gemini Research + Claude
    Script + Gemini SEO simultaneously;
4.  workflow schema supports `$run`, `from`, `latest`, `approved`;
5.  manual and final approval can both feed the same downstream approved
    selector;
6.  Run/node/approval persistence model exists;
7.  data root is outside code/repo by default;
8.  Prompt Executor interfaces are represented in schemas/contracts;
9.  Demo config-only prompt capability validates against plugin schema;
10. DB migrations create the minimum Phase-1a state.

------------------------------------------------------------------------

# 56. Phase 1a Acceptance

Must pass:

1.  Create Channel, Project and Project Brief.
2.  Install config-only Demo Niche capability without executing package
    Python.
3.  Install trusted Demo text-generation provider disabled.
4.  Admin grants trust before executable enable.
5.  Purpose route selects Demo provider/model/options.
6.  Prompt Executor renders and calls provider.
7.  Static package validation never imports plugin code.
8.  Marker-file test proves validation executes nothing.
9.  Invalid ZIP/path traversal/oversize rejected.
10. Unauthorized RPC rejected.
11. Worker environment contains no Core DB/master key/unrelated secrets.
12. Cross-Channel access through supported interfaces rejected.
13. Worker crash/timeout does not crash Core.
14. Run/node state survives Core restart.
15. Waiting human approval survives Core restart.
16. Approved artifact selector resumes correct downstream node.
17. Run Snapshot records workflow/routing/pins/prompt/options.
18. SSE/log progress visible.
19. Data root is outside repository/install tree.
20. Unicode/Urdu paths are covered by Windows tests.
------------------------------------------------------------------------

# 57. Core DB Logical Tables

``` text
users
roles
user_roles
sessions

channels
niches
niche_versions
namespace_registry

projects
project_briefs
workflow_runs
run_snapshots
workflow_node_runs
workflow_map_items

plugins
plugin_versions
plugin_trust_grants
plugin_permission_grants
channel_plugin_assignments
plugin_settings
plugin_health
plugin_runtime_envs

capabilities
capability_variants
contracts
contract_versions
plugin_capabilities

workflows
workflow_versions
channel_routes
approval_queue
approval_decisions

artifacts
artifact_generations
artifact_links
asset_provenance

prompts
prompt_versions
prompt_overrides
niche_resources
llm_cache

encrypted_secrets
secret_bindings
credential_bindings
oauth_connections

jobs
provider_jobs
triggers
notifications

export_locations
external_tools

usage_records
pricing_catalogue
budgets
budget_reservations
rate_limits
rate_limit_state

publishing_records
analytics_records

event_outbox
event_deliveries
dead_letters

audit_log
schema_migrations
backups
```

------------------------------------------------------------------------

# 58. Source-of-Truth Matrix

  Concern                      Source of truth
  ---------------------------- ---------------------------------------------
  Plugin/Niche naming          canonical naming grammars
  Plugin manifest              validated `plugin.json`
  Trust                        Core DB admin trust grant
  Permissions                  versioned Core DB grants
  Credential domains           approved credential binding
  Package bytes                immutable package store + SHA-256
  Python deps                  lock + approved wheelhouse/runtime registry
  Mutable data root            Core installation config
  Channel niche                Channel DB pin
  Project brief                versioned brief artifact
  Run config                   `run_snapshots`
  Workflow                     versioned DB workflow
  Routing                      Channel purpose-aware route DB
  Effective provider options   node-run record
  Prompts/rules                content-addressed prompt/resource registry
  Standard contracts           `yg-standard-contracts`
  Capabilities                 Capability Registry
  Plugin private data          Channel/plugin/major-version data store
  Approval result              `approval_decisions` + artifact generation
  Artifacts                    Artifact Store + DB
  Human edits                  artifact generations/diffs
  Provider remote jobs         `provider_jobs`
  External tools               Tool Registry
  Export roots                 approved `export_locations`
  Cost/quota                   raw usage + pricing/quota catalogue
  Schedules                    `triggers`
  Publishing                   publishing records/provider result
  Provenance                   asset provenance records
  Events                       durable event/outbox tables
  Audit                        append-oriented audit log

------------------------------------------------------------------------

# 59. Repository vs Data Layout

Repository/install:

``` text
YG-PLUG-PLAY/
├── core/
├── contracts/
│   └── standard/
├── schemas/
├── dashboard/
├── tools/
├── tests/
├── docs/
├── pyproject.toml
└── README.md
```

Mutable data, by default outside repository:

``` text
%LOCALAPPDATA%\YG-PLUG-PLAY\
├── db\
├── packages\
│   ├── plugins\
│   └── niches\
├── artifacts\
├── plugin-data\
├── prompts\
├── runtime\
│   ├── envs\
│   └── scratch\
├── wheelhouse\
├── exports\
├── backups\
└── logs\
```

------------------------------------------------------------------------

# 60. Immediate Phase-0 Deliverables

``` text
docs/ARCHITECTURE_V5.md

schemas/plugin.schema.json
schemas/workflow.schema.json
schemas/settings.schema.json
schemas/capability.schema.json
schemas/contract.schema.json
schemas/brief-form.schema.json

contracts/standard/

core/config/
core/database/
core/auth/
core/channels/
core/projects/
core/runs/
core/jobs/
core/plugin_installer/
core/plugin_registry/
core/plugin_runtime/
core/trust/
core/permissions/
core/settings/
core/secrets/
core/credential_proxy/
core/capability_registry/
core/contract_registry/
core/prompt_executor/
core/routing/
core/workflow/
core/artifact_store/
core/plugin_data/
core/events/
core/audit/

dashboard/
tools/yg/

niches/demo/
plugins/demo-text-provider/

tests/schemas/
tests/contracts/
tests/security/
tests/integration/
```

The existing Senior Health production repository remains untouched
during this prototype.

------------------------------------------------------------------------

# 61. Non-Negotiable Rules --- v5 Freeze

1.  v0 executable plugins require an admin trusted-code grant.
2.  Manifest cannot self-authorize trust.
3.  Config-only packages execute no plugin Python.
4.  Windows is the initial local-first target.
5.  Mutable data is outside code/repository by default.
6.  Public names follow type-specific canonical grammars.
7.  Core remains domain-agnostic.
8.  Generic contracts live in `yg-standard-contracts`.
9.  Domain logic may live in MD/JSON prompt-driven capabilities.
10. Prompt Executor is a first-class Phase-1a component.
11. LLM routing is purpose-aware.
12. Research, Script, SEO and Medical Review may use different
    providers/models in the same Channel.
13. Effective model/options are frozen and recorded per node execution.
14. Trust, permissions and routes are Core DB state.
15. Credentials are bound to domains.
16. Credential-bound domains do not need duplicate generic network
    declarations.
17. Cross-domain redirects never receive bound credentials.
18. SDK proxy supports HTTP/SSE streaming; generic WS proxy is not a v0
    requirement.
19. Private/loopback upstream SSRF is blocked by default.
20. Core localhost API is authenticated.
21. Provider feature requirements are route-validated.
22. Prompt templates use sandboxed Jinja2 with a small allowlist.
23. Prompt-context rules and deterministic validator rules are separate
    concepts.
24. Web/research content is treated as untrusted prompt data.
25. Structured-output repair is bounded and separate from provider
    fallback.
26. Run starts from a typed Project Brief.
27. Snapshot belongs to Run.
28. `$run`, `from`, `latest` and `approved` selector semantics are
    explicit.
29. `from` means latest successful generation of that node output.
30. Both manual and normal approvals publish typed approved artifacts.
31. Human edits create immutable new artifact generations and preserve
    diffs.
32. Human-requested revision cannot be blocked by an exhausted automatic
    loop counter.
33. Minimal durable Run/node/approval state exists in Phase 1a.
34. Map/parallel advanced reconciliation remains Phase 3.
35. Large files use scoped artifact paths, not JSON blobs.
36. Provider remote jobs are persisted and pollable.
37. Workers never serve multiple Channels.
38. External binaries are invoked through Tool Registry, not arbitrary
    shell/PATH.
39. Final exports use approved named export locations.
40. Publishing is a typed capability and requires pre-publish policy
    checks where configured.
41. Triggers create auditable Runs; events do not secretly orchestrate
    production.
42. Budgets support dollars, credits, characters, quota units and other
    provider units.
43. Generated assets record provenance.
44. Dry-run/mock mode is supported for paid-workflow testing.
45. Prompt changes can be evaluated/versioned before promotion.
46. Core itself has a backup/migration/update lifecycle.
47. Network outages can wait/retry rather than always hard-fail.
48. Phase 0 ends with schemas and interfaces, not production-provider
    complexity.
49. Phase 1a must prove the Prompt Executor with a config-only domain
    capability and replaceable text provider.
50. Plugin API stays `v0 experimental` until implementation evidence
    justifies v1.
51. After this v5 freeze, architecture changes require an
    implementation-discovered blocker or an explicit new product
    requirement.
52. **Install features; do not rewrite the pipeline.**