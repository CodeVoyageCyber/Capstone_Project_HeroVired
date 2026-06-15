"""
Kubernetes API client helper for the health-checker.

Loads in-cluster config when running as a pod (via its
ServiceAccount), and falls back to the local kubeconfig
(~/.kube/config or $KUBECONFIG) for local development.
"""

from kubernetes import client, config


def get_clients():
    """Return (CoreV1Api, AppsV1Api) clients."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    return client.CoreV1Api(), client.AppsV1Api()


def list_nodes(core: client.CoreV1Api):
    """Return a list of node names and their Ready status."""
    nodes = core.list_node()
    result = []
    for node in nodes.items:
        ready = "Unknown"
        for condition in node.status.conditions:
            if condition.type == "Ready":
                ready = condition.status
        result.append({"name": node.metadata.name, "ready": ready})
    return result


def list_pods(core: client.CoreV1Api, namespace: str = "default"):
    """Return pod name, phase, restart count, and node for a namespace."""
    pods = core.list_namespaced_pod(namespace)
    result = []
    for pod in pods.items:
        restarts = sum(
            (cs.restart_count or 0) for cs in (pod.status.container_statuses or [])
        )
        result.append(
            {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "restarts": restarts,
                "node": pod.spec.node_name,
            }
        )
    return result


def list_deployments(apps: client.AppsV1Api, namespace: str = "default"):
    """Return deployment name, desired vs available replica counts."""
    deployments = apps.list_namespaced_deployment(namespace)
    result = []
    for dep in deployments.items:
        result.append(
            {
                "name": dep.metadata.name,
                "namespace": dep.metadata.namespace,
                "desired": dep.spec.replicas,
                "available": dep.status.available_replicas or 0,
                "ready": dep.status.ready_replicas or 0,
            }
        )
    return result
