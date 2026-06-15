"""
Kubernetes API client helper.

Loads in-cluster config when running as a pod (via its ServiceAccount),
and falls back to the local kubeconfig (~/.kube/config or $KUBECONFIG)
for local development.
"""

from kubernetes import client, config


def get_k8s_client() -> client.CoreV1Api:
    """Return a configured CoreV1Api client."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()

    return client.CoreV1Api()


def list_nodes(api: client.CoreV1Api):
    """Return a list of node names and their Ready status."""
    nodes = api.list_node()
    result = []
    for node in nodes.items:
        ready = "Unknown"
        for condition in node.status.conditions:
            if condition.type == "Ready":
                ready = condition.status
        result.append({"name": node.metadata.name, "ready": ready})
    return result


def list_pods(api: client.CoreV1Api, namespace: str = ""):
    """Return a list of pods with their phase/status.

    If namespace is empty, pods are listed across all namespaces.
    """
    if namespace:
        pods = api.list_namespaced_pod(namespace)
    else:
        pods = api.list_pod_for_all_namespaces()

    result = []
    for pod in pods.items:
        result.append(
            {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "phase": pod.status.phase,
                "node": pod.spec.node_name,
            }
        )
    return result
