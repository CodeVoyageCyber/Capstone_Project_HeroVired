"""
Kubernetes Cluster Health Checker and Auto-Healing — main FastAPI app.

Sprint 1 scope:
  - /healthz        liveness check for the app itself
  - /api/nodes      list cluster nodes and their Ready status (proves
                    Kubernetes API access works)
  - /api/pods       list pods across all namespaces (or a given
                    namespace via ?namespace=)

Later sprints will add monitoring metrics, self-healing endpoints,
alerting integration, and dashboard data.
"""

from fastapi import FastAPI, HTTPException, Query

from k8s_client import get_k8s_client, list_nodes, list_pods

app = FastAPI(
    title="K8s Cluster Health Checker",
    description="Automated health monitoring and self-healing for Kubernetes clusters",
    version="0.1.0",
)


@app.get("/healthz")
def healthz():
    """Basic liveness probe."""
    return {"status": "ok"}


@app.get("/api/nodes")
def get_nodes():
    """List all nodes in the cluster and their Ready status."""
    try:
        api = get_k8s_client()
        return {"nodes": list_nodes(api)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/pods")
def get_pods(namespace: str = Query("", description="Optional namespace filter")):
    """List pods, optionally filtered by namespace."""
    try:
        api = get_k8s_client()
        return {"pods": list_pods(api, namespace)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
