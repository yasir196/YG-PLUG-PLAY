"""Static semantic validation for V5 workflows.

This layer validates graph/data-flow rules that JSON Schema cannot express.
It is deterministic and side-effect free.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


class WorkflowValidationError(ValueError):
    """Raised when a workflow is structurally valid but semantically unsafe."""


@dataclass(frozen=True)
class _Producer:
    node: str
    output: str
    contract: str


def validate_workflow(workflow: Mapping[str, Any]) -> None:
    nodes_list = workflow.get("nodes", [])
    ids = [str(node.get("id")) for node in nodes_list]
    duplicates = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
    if duplicates:
        _fail(f"duplicate node id(s): {', '.join(duplicates)}")

    nodes = {str(node["id"]): node for node in nodes_list}
    start = str(workflow.get("start", ""))
    if start not in nodes:
        _fail(f"start target does not exist: {start!r}")

    edges = _edges(nodes)
    _check_targets_exist(nodes, edges)
    _check_loop_targets(nodes)
    _check_approval_targets(nodes)
    _check_cycles_bounded(nodes, edges)
    _check_reachability(start, nodes, edges)

    producers = _producers(nodes)
    _check_selectors(nodes, producers)
    _check_contract_compatibility(nodes, producers)
    _check_required_inputs_reachable_on_every_path(start, nodes, edges, producers)


def _fail(message: str) -> None:
    raise WorkflowValidationError(message)


def _targets(node: Mapping[str, Any]) -> Iterable[str]:
    node_type = node.get("type")
    if node_type == "condition":
        yield str(node["true_next"])
        yield str(node["false_next"])
    elif node_type == "human-approval":
        for target in node.get("approval", {}).get("actions", {}).values():
            if target != "$self":
                yield str(target)
    elif node_type == "parallel":
        yield from (str(x) for x in node.get("branches", []))
        yield str(node["join"])
    else:
        next_target = node.get("next")
        if next_target and next_target != "$self":
            yield str(next_target)

    loop = node.get("loop_control")
    if loop:
        yield str(loop["on_exhausted"])
    failure = node.get("failure_policy")
    if failure:
        yield str(failure["on_exhausted"])


def _edges(nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, set[str]]:
    return {node_id: set(_targets(node)) for node_id, node in nodes.items()}


def _check_targets_exist(
    nodes: Mapping[str, Mapping[str, Any]], edges: Mapping[str, set[str]]
) -> None:
    for source, targets in edges.items():
        for target in targets:
            if target not in nodes:
                _fail(f"node {source!r} targets missing node {target!r}")


def _check_reachability(
    start: str, nodes: Mapping[str, Mapping[str, Any]], edges: Mapping[str, set[str]]
) -> None:
    seen: set[str] = set()
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(edges[current] - seen)
    unreachable = sorted(set(nodes) - seen)
    if unreachable:
        _fail(f"unreachable node(s): {', '.join(unreachable)}")


def _check_loop_targets(nodes: Mapping[str, Mapping[str, Any]]) -> None:
    for node_id, node in nodes.items():
        loop = node.get("loop_control")
        if loop and loop["on_exhausted"] not in nodes:
            _fail(f"node {node_id!r} on_exhausted target does not exist")
        failure = node.get("failure_policy")
        if failure and failure["on_exhausted"] not in nodes:
            _fail(f"node {node_id!r} failure on_exhausted target does not exist")


def _check_approval_targets(nodes: Mapping[str, Mapping[str, Any]]) -> None:
    for node_id, node in nodes.items():
        if node.get("type") != "human-approval":
            continue
        for action, target in node.get("approval", {}).get("actions", {}).items():
            if target != "$self" and target not in nodes:
                _fail(f"approval {node_id!r} action {action!r} targets missing node {target!r}")


def _strong_components(edges: Mapping[str, set[str]]) -> list[set[str]]:
    index = 0
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    result: list[set[str]] = []

    def visit(v: str) -> None:
        nonlocal index
        indices[v] = low[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)
        for w in edges[v]:
            if w not in indices:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], indices[w])
        if low[v] == indices[v]:
            component: set[str] = set()
            while True:
                w = stack.pop()
                on_stack.remove(w)
                component.add(w)
                if w == v:
                    break
            result.append(component)

    for vertex in edges:
        if vertex not in indices:
            visit(vertex)
    return result


def _check_cycles_bounded(
    nodes: Mapping[str, Mapping[str, Any]], edges: Mapping[str, set[str]]
) -> None:
    for component in _strong_components(edges):
        cyclic = len(component) > 1 or any(node in edges[node] for node in component)
        if not cyclic:
            continue
        bounded = any(
            nodes[node].get("loop_control") or nodes[node].get("failure_policy")
            for node in component
        )
        if not bounded:
            _fail(f"unbounded cycle detected: {', '.join(sorted(component))}")


def _producers(nodes: Mapping[str, Mapping[str, Any]]) -> dict[str, _Producer]:
    result: dict[str, _Producer] = {}
    for node_id, node in nodes.items():
        for output, spec in node.get("outputs", {}).items():
            result[f"{node_id}.{output}"] = _Producer(node_id, output, str(spec["contract"]))
        if node.get("type") == "map":
            result[f"{node_id}.failed-items"] = _Producer(
                node_id, "failed-items", "workflow.failed-item.collection"
            )
    return result


def _selector_refs(selector: Mapping[str, Any]) -> list[str]:
    if "from" in selector:
        value = str(selector["from"])
        return [] if value.startswith("$run.") else [value]
    return [str(x) for x in selector.get("among", [])]


def _check_selectors(
    nodes: Mapping[str, Mapping[str, Any]], producers: Mapping[str, _Producer]
) -> None:
    for node_id, node in nodes.items():
        for input_name, selector in node.get("inputs", {}).items():
            for ref in _selector_refs(selector):
                if ref not in producers:
                    _fail(f"node {node_id!r} input {input_name!r} has dangling from/reference {ref!r}")
        approval = node.get("approval", {})
        artifact = approval.get("artifact")
        if artifact:
            for ref in _selector_refs(artifact):
                if ref not in producers:
                    _fail(f"approval {node_id!r} artifact has dangling reference {ref!r}")


def _selector_contracts(
    selector: Mapping[str, Any], producers: Mapping[str, _Producer]
) -> set[str]:
    if "from" in selector:
        ref = str(selector["from"])
        return set() if ref.startswith("$run.") else {producers[ref].contract}
    if "latest" in selector:
        return {str(selector["latest"])}
    if "approved" in selector:
        return {str(selector["approved"])}
    return set()


def _check_contract_compatibility(
    nodes: Mapping[str, Mapping[str, Any]], producers: Mapping[str, _Producer]
) -> None:
    for node_id, node in nodes.items():
        for input_name, selector in node.get("inputs", {}).items():
            expected = selector.get("latest") or selector.get("approved")
            if not expected:
                continue
            actual = {producers[ref].contract for ref in _selector_refs(selector)}
            incompatible = actual - {str(expected)}
            if incompatible:
                _fail(
                    f"node {node_id!r} input {input_name!r} expects contract {expected!r} "
                    f"but selector can produce {sorted(incompatible)!r}"
                )


def _predecessors(edges: Mapping[str, set[str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for source, targets in edges.items():
        for target in targets:
            result[target].add(source)
    return result


def _ancestors(node_id: str, predecessors: Mapping[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque(predecessors.get(node_id, set()))
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(predecessors.get(current, set()) - seen)
    return seen


def _check_required_inputs_reachable_on_every_path(
    start: str,
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Mapping[str, set[str]],
    producers: Mapping[str, _Producer],
) -> None:
    predecessors = _predecessors(edges)
    for node_id, node in nodes.items():
        for input_name, selector in node.get("inputs", {}).items():
            if selector.get("optional", False):
                continue
            refs = _selector_refs(selector)
            if not refs:
                continue
            candidate_producers = {producers[ref].node for ref in refs}
            if not _all_paths_have_candidate(
                start, node_id, candidate_producers, edges, blocked=frozenset({node_id})
            ):
                _fail(
                    f"node {node_id!r} required input {input_name!r} is unreachable "
                    "on at least one path"
                )

            # A direct 'from' must specifically dominate the consumer. For latest/approved,
            # any candidate in the declared lineage is sufficient on each path.
            if "from" in selector:
                producer = next(iter(candidate_producers))
                if _parallel_sibling_producer_is_available(producer, node_id, nodes, edges):
                    continue
                if producer not in _ancestors(node_id, predecessors):
                    _fail(
                        f"node {node_id!r} required input {input_name!r} "
                        f"cannot be produced before use"
                    )


def _parallel_sibling_producer_is_available(
    producer: str,
    consumer: str,
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Mapping[str, set[str]],
) -> bool:
    """A completed parallel join makes every declared branch output available."""

    for node in nodes.values():
        if node.get("type") != "parallel":
            continue
        branches = {str(x) for x in node.get("branches", [])}
        join = str(node["join"])
        if producer not in branches:
            continue
        seen: set[str] = set()
        queue = deque([join])
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            if current == consumer:
                return True
            seen.add(current)
            queue.extend(edges.get(current, set()) - seen)
    return False


def _dataflow_edges(
    nodes: Mapping[str, Mapping[str, Any]], edges: Mapping[str, set[str]]
) -> dict[str, set[str]]:
    result = {node_id: set(targets) for node_id, targets in edges.items()}
    for node_id, node in nodes.items():
        if node.get("type") == "parallel":
            join = str(node["join"])
            branch_starts = {str(x) for x in node.get("branches", [])}
            for branch in branch_starts:
                result[branch].add(join)
            # For dataflow dominance, a join is reached only after every declared
            # parallel branch completes. Remove direct branch-to-join alternatives
            # that would make one sibling's output appear optional.
            for source in branch_starts:
                if join in result[source]:
                    result[source].discard(join)
            if branch_starts:
                synthetic = "__parallel_all__" + node_id
                result[synthetic] = {join}
                for branch in branch_starts:
                    result[branch].add(synthetic)
        if node.get("type") == "human-approval":
            actions = node.get("approval", {}).get("actions", {})
            for target in actions.values():
                if target == "$self":
                    result[node_id].add(node_id)
    return result


def _all_paths_have_candidate(
    start: str,
    target: str,
    candidates: set[str],
    edges: Mapping[str, set[str]],
    *,
    blocked: frozenset[str],
) -> bool:
    """Return false iff target is reachable from start while avoiding all candidates."""

    if start in candidates:
        return True
    queue = deque([start])
    seen: set[str] = set()
    while queue:
        current = queue.popleft()
        if current in seen or current in candidates:
            continue
        if current == target:
            return False
        seen.add(current)
        for nxt in edges[current]:
            if nxt not in blocked or nxt == target:
                queue.append(nxt)
    return True
