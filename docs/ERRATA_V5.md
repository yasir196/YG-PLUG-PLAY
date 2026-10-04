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
