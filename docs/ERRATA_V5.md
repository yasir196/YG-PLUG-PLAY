# YG-PLUG-PLAY V5 Errata

**Status:** Canonical companion to `docs/ARCHITECTURE_V5.md`.  
**Rule:** V5 remains frozen. These corrections clarify V5; they do not create V6.

Where this file conflicts with an older V5 example, this errata controls.

## E1 — Niche namespace registration and delegation

A Niche owns its namespace. A `type: niche` plugin that is compatible with that Niche may register capabilities/contracts inside that Niche namespace. A Niche may also explicitly delegate its namespace to specific compatible plugins.

Delegation grants registration authority only; it does not transfer namespace ownership. Registration still passes Core registry validation. Conflicting active registrations for the same namespaced identity must fail unless an explicit multi-provider/version rule allows coexistence.

## E2 — Trust grant package identity

Executable trust is an admin/platform grant bound to the exact package identity:

```text
(plugin_id, plugin_version, package_sha256)
```

A version string alone is never sufficient. Changing package bytes invalidates the old trust grant even when the semantic version is unchanged.

## E3 — Approval decision artifact and revision feedback

Every human approval action publishes a typed `approval.decision` artifact containing at least the action, actor, target artifact/generation, timestamp, and optional comment/feedback.

A revision node may accept the latest approval decision as optional feedback:

```json
{
  "feedback": {
    "latest": "approval.decision",
    "optional": true
  }
}
```

This lets human revision feedback enter the workflow without inventing an implicit side channel.

## E4 — Reserved self-transition

The reserved transition target is:

```text
$self
```

It replaces the older illustrative value `stay`. Human edit actions that remain on the current approval node target `$self`.

## E5 — Map failed-items output

Every map node implicitly publishes a `failed-items` output representing items that exhausted the map's current automatic attempt policy.

Its standard contract is:

```text
workflow.failed-item.collection
```

The output exists even when empty, so failure-review nodes can reference it without requiring every workflow author to redeclare the output.

## E6 — Pre-publish checklist must gate success

`pre-publish-check` publishes a typed checklist artifact, for example:

```text
publish.checklist
```

The workflow must route that checklist through a condition and/or human override gate before publishing or `end-success`. A computed checklist may never be ignored.

Canonical shape:

```text
pre-publish-check
  -> pre-publish-decision
       PASS -> publish/end-success
       FAIL -> review/reject/override path
```

## E7 — Human-edited generation lineage

A human edit creates a new immutable artifact generation but remains in the same logical node-output lineage as the artifact being edited.

Therefore normal `from`/`latest` resolution can see the edited generation. The original generation remains immutable and the edit actor/diff is audited.

## E8 — One artifact-data path syntax

Conditions and `items_from` use the same path language. Paths address the **unwrapped artifact data** exposed under the workflow input name.

Examples:

```text
review.passed
requests.items
checklist.passed
```

Do not write envelope-dependent paths such as `inputs.requests.items` unless `inputs` is itself an explicitly named data field. Contract/version/artifact metadata remains outside this data-path namespace.

## E9 — Reserved first-party prefix

`yg` and the `yg-*` prefix are reserved for first-party platform packages/IDs. Third-party Plugin/Niche IDs must not use them.

## E10 — Single-admin role semantics

In single-admin v0 mode, the admin implicitly satisfies every workflow approval role. The workflow still records the role requirement and the approval audit record; no duplicate role assignment setup is required.

## E11 — Phase 2 paid-call safety

Before Phase 2 makes any paid LLM/provider call, Core must provide:

- a hard per-run spend/usage cap;
- route-level `max_tokens` or equivalent provider upper bound;
- dry-run/mock mode;
- conservative preflight that stops before the paid call when the hard cap would be exceeded.

These controls are Phase 2 entry requirements even though the broader budget/operations system is expanded later.

## E12 — Approval action semantic kind

Every human-approval action is an object with an explicit semantic `kind` and transition `next`. Allowed kinds are `approve`, `reject`, `request-revision`, and `edit`. Core behavior is determined by `kind`, never by the action key/name. An `edit` action may target `$self` and retains E4/E7 immutable-edit behavior.

Phase 1a requires this format. Legacy string actions such as `"approve": "next-node"` are rejected at workflow validation/install time; there is no implicit action-name migration.

## E13 — Per-action approval comment requirement

Approval comment requirements are declarative per action through optional `requires_comment: boolean`. Missing means `false`; Core must not infer a default from `kind`. When `requires_comment` is true, a missing, empty, or whitespace-only comment is rejected before any decision artifact, queue, Run, edit, approval publication, or transition mutation. Section 35 revision and reject actions set it to true; `retry-failed` explicitly sets it to false.

API mapping distinguishes approval validation from runtime faults: invalid approval decisions use `ApprovalValidationError` and map to HTTP 422; a missing approval queue maps to HTTP 404; unrelated runtime faults are not reclassified as validation errors.

## E14 — Phase-1a execution mode and deferred resource packaging

Phase-1a is supported from an editable checkout (`uv sync --dev`). Running Core
or the dashboard from an installed wheel is not a Phase-1a deliverable and is not
a T1.19/T1.20 acceptance criterion.

Evidence: CI #305 (commit `ffde3fc`) built the wheel, verified its 15 required
dashboard/core members, installed it into a fresh venv outside the repository and
failed at import with `FileNotFoundError` for
`contracts/standard/schemas/project.brief.schema.json`. This is a real
installed-distribution defect, not an irrelevant failure.

Confirmed runtime dependencies on repository-level resources:

- `contracts/standard/` — `core/workspace/service.py` (read at import time)
- `niches/demo/` — `core/workspace/defaults.py` (demo workflow and routes)
- `schemas/` — `tools/yg/cli.py`; caller-supplied paths in
  `core/plugin_registry/installer.py` and `registries.py`

Resource packaging is deferred to dedicated work, which must choose between
package-data/package-dir mapping and relocation using tests and evidence. That
work re-enables the installed-wheel smoke step in CI. Until then the
wheel-contents check remains active and import-time resource reads must not be
added.

## Canonical corrections to V5 examples

Apply these substitutions when implementing V5 examples:

- legacy `"edit": "stay"` → `"edit": {"kind": "edit", "next": "$self"}`
- all approval actions require explicit `{kind, next}` objects; action names carry no semantics
- revision nodes may include optional latest `approval.decision` feedback
- `generate-images.failed-items` is the map node's implicit failed-items output
- `items_from: "inputs.requests.items"` → `items_from: "requests.items"`
- pre-publish check declares `publish.checklist` and is followed by a gating condition/override path
- trust lookups use `(plugin_id, plugin_version, package_sha256)`
- human-edited artifacts remain in the original logical node-output lineage
- `yg-*` is reserved
- single-admin v0 admin satisfies all approval roles
- Phase 2 begins with hard spend/token caps and dry-run/mock support

## Implementation rule

Schemas and semantic validators must encode these corrections wherever JSON Schema can express them. Cross-package authority, namespace delegation, graph semantics, trust lookup, lineage, and pre-publish path guarantees that cannot be fully expressed in JSON Schema must be enforced by Core semantic validation and tests.
