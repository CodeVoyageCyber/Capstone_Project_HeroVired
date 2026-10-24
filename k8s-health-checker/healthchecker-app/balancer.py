"""
Resource Balancing and Node Scaling Module — Sprint 4.

Monitors pod distribution across cluster nodes and computes cluster balance
metrics to ensure optimal workload distribution and cost efficiency:
  - Tracks per-node pod counts and node capacities.
  - Detects workload skew across nodes for multi-replica GratitudeApp deployments.
  - Exposes balance metrics via Prometheus gauges.
  - Exposes /api/node-balancing endpoint for real-time visibility.
"""

from collections import defaultdict
import logging
from typing import Any, Dict, List

from kubernetes import client
from prometheus_client import Gauge

logger = logging.getLogger("balancer")

# ── Prometheus Gauges ─────────────────────────────────────────────────────────
NODE_POD_COUNT = Gauge(
    "healthchecker_node_pod_count",
    "Number of pods scheduled on a specific node",
    ["node"],
)
NODE_CPU_CAPACITY = Gauge(
    "healthchecker_node_cpu_capacity_cores",
    "Total allocatable CPU cores for a node",
    ["node"],
)
CLUSTER_BALANCE_RATIO = Gauge(
    "healthchecker_cluster_balance_ratio",
    "Ratio of min/max pod count across nodes (1.0 = perfect balance)",
)


def get_node_balance_report(
    core: client.CoreV1Api,
    namespace: str = "default",
) -> Dict[str, Any]:
    """
    Inspect all nodes and pods in the cluster, calculate distribution,
    and update Prometheus metrics.
    """
    nodes_info = []
    node_names = set()

    try:
        nodes = core.list_node()
        for node in nodes.items:
            n_name = node.metadata.name
            node_names.add(n_name)
            ready = "Unknown"
            for condition in (node.status.conditions or []):
                if condition.type == "Ready":
                    ready = condition.status

            cpu_alloc = node.status.allocatable.get("cpu", "0") if node.status.allocatable else "0"
            mem_alloc = node.status.allocatable.get("memory", "0") if node.status.allocatable else "0"

            # Parse CPU to float if possible
            try:
                cpu_val = float(cpu_alloc)
            except ValueError:
                cpu_val = 1.0

            NODE_CPU_CAPACITY.labels(node=n_name).set(cpu_val)

            nodes_info.append({
                "name": n_name,
                "ready": ready,
                "cpu_allocatable": cpu_alloc,
                "memory_allocatable": mem_alloc,
            })
    except Exception as exc:
        logger.error("Failed to list nodes for balancing report: %s", exc)

    # Count pods per node and per deployment
    pods_per_node: Dict[str, int] = defaultdict(int)
    workload_distribution: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_pods = 0

    try:
        pods = core.list_namespaced_pod(namespace)
        for pod in pods.items:
            pod_node = pod.spec.node_name or "Unassigned"
            pods_per_node[pod_node] += 1
            total_pods += 1

            # Determine deployment root name
            pod_name = pod.metadata.name
            parts = pod_name.split("-")
            root_name = "-".join(parts[:-2]) if len(parts) >= 3 else pod_name
            workload_distribution[root_name][pod_node] += 1
    except Exception as exc:
        logger.error("Failed to list pods for balancing report: %s", exc)

    # Clear and update node pod count gauge
    NODE_POD_COUNT.clear()
    for n_name in node_names:
        count = pods_per_node.get(n_name, 0)
        NODE_POD_COUNT.labels(node=n_name).set(count)

    # Compute balance ratio across active nodes
    counts = [pods_per_node.get(n, 0) for n in node_names] if node_names else [0]
    min_count = min(counts) if counts else 0
    max_count = max(counts) if counts else 0

    if max_count == 0 or len(node_names) <= 1:
        balance_ratio = 1.0  # Single-node cluster is inherently balanced with itself
        status = "balanced"
    else:
        balance_ratio = round(min_count / max_count, 2)
        status = "balanced" if balance_ratio >= 0.6 else "imbalanced"

    CLUSTER_BALANCE_RATIO.set(balance_ratio)

    return {
        "node_count": len(node_names),
        "total_pods_in_namespace": total_pods,
        "cluster_balance_ratio": balance_ratio,
        "status": status,
        "nodes": [
            {
                **n,
                "pod_count": pods_per_node.get(n["name"], 0),
            }
            for n in nodes_info
        ],
        "workload_distribution": {k: dict(v) for k, v in workload_distribution.items()},
    }
