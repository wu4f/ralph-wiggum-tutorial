"""Build a bounded code-map graph from detected execution flows."""
from __future__ import annotations

from typing import Any


JSONDict = dict[str, Any]


def build_execution_graph(flows: list[JSONDict]) -> JSONDict:
    """Combine flow steps and connections into one undirected display graph.

    The graph intentionally omits execution *direction*: the quiz asks the
    student to recover the order of execution, so revealing arrows here would
    give away the answer. Nodes are the union of all flow steps; edges are the
    union of consecutive-step connections across every flow.
    """
    nodes_by_id: dict[str, JSONDict] = {}
    edges_by_id: dict[str, JSONDict] = {}

    for flow in flows:
        for step in flow['steps']:
            nodes_by_id.setdefault(step['id'], {
                'id': step['id'],
                'label': step['label'],
                'path': step['path'],
                'kind': step['kind'],
            })
        for edge in flow['edges']:
            edge_id = f"{edge['sourceId']}::{edge['targetId']}"
            reverse_id = f"{edge['targetId']}::{edge['sourceId']}"
            if edge_id in edges_by_id or reverse_id in edges_by_id:
                continue
            edges_by_id[edge_id] = {
                'id': edge_id,
                'sourceId': edge['sourceId'],
                'targetId': edge['targetId'],
                'label': edge['label'],
            }

    return {
        'nodes': list(nodes_by_id.values()),
        'edges': list(edges_by_id.values()),
    }
