"""
Slack Notification Module — Sprint 5.

Provides real-time Slack alerting via Incoming Webhooks for:
  - Critical infrastructure alerts (Node NotReady, Degraded Deployments)
  - Self-healing actions (Pod restarts, CrashLoopBackOff remediations, Evicted pod purges)
  - Manual test notifications

Supports both live Slack delivery and a local mock/dry-run mode when
SLACK_WEBHOOK_URL is unset, logging structured payloads for auditability.
"""

from datetime import datetime, timezone
import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

logger = logging.getLogger("slack_notifier")

# Environment configuration
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#devops-alerts").strip()

# In-memory history of dispatched notifications (up to 100 entries)
MAX_NOTIFICATION_HISTORY = 100
_notification_history: List[Dict[str, Any]] = []
_history_lock = threading.Lock()

# Severity color scheme
SEVERITY_COLORS = {
    "critical": "#E01E5A",  # Red
    "warning": "#ECB22E",   # Amber / Yellow
    "info": "#2EB67D",      # Green
    "healing": "#36C5F0",   # Blue
}

SEVERITY_ICONS = {
    "critical": "🚨",
    "warning": "⚠️",
    "info": "ℹ️",
    "healing": "🛠️",
}


def record_notification(entry: Dict[str, Any]):
    """Record a dispatched notification in memory."""
    with _history_lock:
        _notification_history.insert(0, entry)
        if len(_notification_history) > MAX_NOTIFICATION_HISTORY:
            _notification_history.pop()


def get_notification_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve history of dispatched notifications."""
    with _history_lock:
        return list(_notification_history[:limit])


def send_slack_message(
    title: str,
    message: str,
    severity: str = "info",
    fields: Optional[Dict[str, str]] = None,
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a formatted Block Kit notification to a Slack webhook.
    Falls back to mock/simulated delivery if no webhook is configured.
    """
    url = webhook_url or SLACK_WEBHOOK_URL
    color = SEVERITY_COLORS.get(severity.lower(), "#2EB67D")
    icon = SEVERITY_ICONS.get(severity.lower(), "📢")
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build Slack Attachment with fields
    attachment_fields = []
    if fields:
        for k, v in fields.items():
            attachment_fields.append({"title": k, "value": str(v), "short": True})

    payload = {
        "channel": SLACK_CHANNEL,
        "attachments": [
            {
                "fallback": f"[{severity.upper()}] {title}: {message}",
                "color": color,
                "pretext": f"{icon} *GratitudeApp Alert Notification*",
                "title": title,
                "text": message,
                "fields": attachment_fields,
                "footer": "GratitudeApp Health Checker | Kubernetes Self-Healing",
                "ts": int(datetime.now(timezone.utc).timestamp()),
            }
        ],
    }

    audit_entry = {
        "timestamp": timestamp,
        "title": title,
        "message": message,
        "severity": severity,
        "fields": fields or {},
        "target_channel": SLACK_CHANNEL,
    }

    # If no webhook URL is configured or set to mock, simulate delivery
    if not url or url.lower() in ("mock", "simulate", "disabled"):
        audit_entry["status"] = "simulated"
        audit_entry["delivered"] = True
        audit_entry["details"] = "Delivered to mock notifier (SLACK_WEBHOOK_URL not configured)"
        record_notification(audit_entry)
        logger.info("[MOCK SLACK] %s %s: %s | fields=%s", icon, title, message, fields)
        return audit_entry

    # Deliver to real Slack webhook
    try:
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            resp_body = response.read().decode("utf-8")
            audit_entry["status"] = "success"
            audit_entry["delivered"] = True
            audit_entry["response"] = resp_body
            record_notification(audit_entry)
            logger.info("Slack notification dispatched successfully: %s", title)
            return audit_entry
    except urllib.error.URLError as exc:
        audit_entry["status"] = "failed"
        audit_entry["delivered"] = False
        audit_entry["error"] = str(exc)
        record_notification(audit_entry)
        logger.error("Failed to post notification to Slack: %s", exc)
        return audit_entry


def send_healing_notification(
    action: str,
    pod: str,
    namespace: str,
    reason: str,
    result: str,
    details: str = "",
) -> Dict[str, Any]:
    """Convenience helper to format and send self-healing alerts."""
    severity = "healing" if result == "success" else "critical"
    title = f"Self-Healing Action: {action.replace('_', ' ').title()}"
    message = f"Pod *{pod}* in namespace `{namespace}` was remediated due to *{reason}*."

    fields = {
        "Action": action,
        "Target Pod": pod,
        "Namespace": namespace,
        "Trigger Reason": reason,
        "Remediation Result": result.upper(),
        "Details": details[:200] if details else "ReplicaSet reconciling replica.",
    }

    return send_slack_message(
        title=title,
        message=message,
        severity=severity,
        fields=fields,
    )
