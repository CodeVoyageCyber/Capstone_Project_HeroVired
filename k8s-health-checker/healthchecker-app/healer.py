"""
Self-healing module for GratitudeApp pods — Sprint 3.

Monitors pods in the target namespace and automates recovery:
  - Detects pods stuck in CrashLoopBackOff or Error states and deletes them,
    allowing the parent Deployment/ReplicaSet to recreate a healthy replica.
  - Automatically cleans up pods stuck in "Evicted" state.
  - Detects unresponsive/unhealthy pods (e.g. failing readiness checks with
    high restart counts) and restarts them via deletion.
  - Enforces a per-workload cooldown period (45s) to prevent rapid deletion flapping.
  - Records a structured audit log of every healing action taken, exposed via
    the /api/healing-log endpoint.
  - Exposes Prometheus counter 'healthchecker_healing_actions_total'.
"""

from datetime import datetime, timezone
import logging
import os
import threading
import time
from typing import Any, Dict, List, Tuple

from kubernetes import client
from kubernetes.client.rest import ApiException
from prometheus_client import Counter

logger = logging.getLogger("healer")

# ── Prometheus Metric ─────────────────────────────────────────────────────────
HEALING_ACTIONS = Counter(
    "healthchecker_healing_actions_total",
    "Total number of self-healing actions performed",
    ["namespace", "action", "reason", "result"],
)

# ── Audit Log Storage ─────────────────────────────────────────────────────────
MAX_AUDIT_ENTRIES = 200
_healing_audit_log: List[Dict[str, Any]] = []
_audit_lock = threading.Lock()

# ── Workload Cooldown Tracker ─────────────────────────────────────────────────
# Prevents repeatedly deleting pods from the same deployment before K8s reconciles
_cooldown_tracker: Dict[str, float] = {}
COOLDOWN_SECONDS = int(os.environ.get("HEALING_COOLDOWN_SECONDS", "45"))


def record_audit(
    action: str,
    pod: str,
    namespace: str,
    reason: str,
    result: str,
    details: str = "",
) -> Dict[str, Any]:
    """Record an action in the structured audit log and increment Prometheus metric."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pod": pod,
        "namespace": namespace,
        "action": action,
        "reason": reason,
        "result": result,
        "details": details,
    }
    with _audit_lock:
        _healing_audit_log.insert(0, entry)
        if len(_healing_audit_log) > MAX_AUDIT_ENTRIES:
            _healing_audit_log.pop()

    try:
        HEALING_ACTIONS.labels(
            namespace=namespace, action=action, reason=reason, result=result
        ).inc()
    except Exception as exc:
        logger.warning("Failed to increment HEALING_ACTIONS metric: %s", exc)

    # Dispatch real-time Slack notification
    try:
        from slack_notifier import send_healing_notification

        send_healing_notification(
            action=action,
            pod=pod,
            namespace=namespace,
            reason=reason,
            result=result,
            details=details,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send Slack healing notification: %s", exc)

    logger.info("Self-healing action: %s", entry)
    return entry


def get_healing_audit_log(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve recent healing audit log records (most recent first)."""
    with _audit_lock:
        return list(_healing_audit_log[:limit])


def is_deployment_owned(pod) -> bool:
    """Check if the pod is managed by a ReplicaSet (backed by a Deployment)."""
    if not pod.metadata.owner_references:
        return False
    return any(
        owner.kind in ("ReplicaSet", "Deployment")
        for owner in pod.metadata.owner_references
    )


def get_pod_root_name(pod_name: str) -> str:
    """Extract deployment base prefix from a pod name (e.g. server-deployment-xxx-yyy -> server-deployment)."""
    parts = pod_name.split("-")
    if len(parts) >= 3:
        return "-".join(parts[:-2])
    return pod_name


def should_skip_due_to_cooldown(pod_name: str) -> bool:
    """Check if a pod from this workload was healed recently."""
    base_name = get_pod_root_name(pod_name)
    now = time.time()
    last_healed = _cooldown_tracker.get(base_name, 0)
    return (now - last_healed) < COOLDOWN_SECONDS


def mark_healed(pod_name: str):
    """Record timestamp of healing action for this workload."""
    base_name = get_pod_root_name(pod_name)
    _cooldown_tracker[base_name] = time.time()


def diagnose_pod(pod) -> Tuple[bool, str, str]:
    """
    Examine a pod's status.
    Returns: (needs_healing: bool, reason: str, details: str)
    """
    phase = pod.status.phase or ""
    status_reason = pod.status.reason or ""

    # 1. Evicted pods (cleanup required)
    if status_reason == "Evicted" or "Evicted" in (pod.status.message or ""):
        return True, "Evicted", f"Pod evicted: {pod.status.message or 'Node pressure'}"

    # Do not heal successfully completed jobs (e.g. database migrations)
    if phase == "Succeeded":
        return False, "", ""

    # 2. Check container states for CrashLoopBackOff or Error
    if pod.status.container_statuses:
        for cs in pod.status.container_statuses:
            waiting = cs.state.waiting
            if waiting and waiting.reason in (
                "CrashLoopBackOff",
                "Error",
                "CreateContainerConfigError",
            ):
                return (
                    True,
                    waiting.reason,
                    f"Container '{cs.name}' in {waiting.reason}: {waiting.message or 'Crash loop detected'}",
                )

            terminated = cs.state.terminated
            if terminated and terminated.reason in ("Error", "OOMKilled") and (cs.restart_count or 0) >= 3:
                return (
                    True,
                    terminated.reason,
                    f"Container '{cs.name}' terminated ({terminated.reason}) with {cs.restart_count} restarts",
                )

    # 3. Running pod but failing readiness check with elevated restarts
    if phase == "Running":
        restarts = sum(
            (cs.restart_count or 0) for cs in (pod.status.container_statuses or [])
        )
        ready_cond = False
        if pod.status.conditions:
            for cond in pod.status.conditions:
                if cond.type == "Ready" and cond.status == "True":
                    ready_cond = True
                    break
        if not ready_cond and restarts >= 5:
            return (
                True,
                "UnreadyHighRestarts",
                f"Pod Running but Ready=False with {restarts} restarts",
            )

    # 4. Failed phase
    if phase == "Failed":
        return True, "FailedPhase", f"Pod in Failed phase (reason: {status_reason})"

    return False, "", ""


def scan_and_heal(core: client.CoreV1Api, namespace: str = "default") -> List[Dict[str, Any]]:
    """
    Scan all pods in the namespace, detect unhealthy or evicted pods,
    and delete them to trigger self-healing recovery.
    """
    actions_taken: List[Dict[str, Any]] = []
    try:
        pods = core.list_namespaced_pod(namespace)
    except Exception as exc:
        logger.error("Failed to list pods during healing scan: %s", exc)
        return actions_taken

    for pod in pods.items:
        pod_name = pod.metadata.name
        needs_healing, reason, details = diagnose_pod(pod)

        if not needs_healing:
            continue

        # Evicted pods can always be cleaned up
        if reason == "Evicted":
            try:
                core.delete_namespaced_pod(name=pod_name, namespace=namespace)
                action = record_audit(
                    action="cleanup_evicted_pod",
                    pod=pod_name,
                    namespace=namespace,
                    reason=reason,
                    result="success",
                    details=details,
                )
                actions_taken.append(action)
            except ApiException as exc:
                action = record_audit(
                    action="cleanup_evicted_pod",
                    pod=pod_name,
                    namespace=namespace,
                    reason=reason,
                    result="failed",
                    details=f"API error: {exc.reason}",
                )
                actions_taken.append(action)
            continue

        # For running/failed/crashlooping pods, only delete if managed by a Deployment/ReplicaSet
        if not is_deployment_owned(pod):
            logger.debug("Skipping unmanaged pod %s (no Deployment/ReplicaSet owner)", pod_name)
            continue

        # Check cooldown to prevent rapid flap deletion
        if should_skip_due_to_cooldown(pod_name):
            logger.debug("Skipping %s due to workload cooldown", pod_name)
            continue

        # Delete the faulty pod; ReplicaSet will recreate a healthy one
        try:
            core.delete_namespaced_pod(name=pod_name, namespace=namespace)
            mark_healed(pod_name)
            action = record_audit(
                action="restart_deployment_pod",
                pod=pod_name,
                namespace=namespace,
                reason=reason,
                result="success",
                details=f"{details}. Deleted pod to let ReplicaSet reschedule.",
            )
            actions_taken.append(action)
        except ApiException as exc:
            action = record_audit(
                action="restart_deployment_pod",
                pod=pod_name,
                namespace=namespace,
                reason=reason,
                result="failed",
                details=f"API error: {exc.reason}",
            )
            actions_taken.append(action)

    return actions_taken
