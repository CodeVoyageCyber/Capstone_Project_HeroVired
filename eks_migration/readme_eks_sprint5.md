# Sprint 5 — Slack Notifications and Alertmanager on Amazon EKS

This guide deploys Sprint 5 notification code to the existing EKS health-checker
and configures Alertmanager to route alerts by severity. You can complete and
verify the feature in **mock mode** without Slack credentials; live Slack
delivery is optional.

> **Secret handling:** Never put a Slack webhook URL in Git, a committed
> manifest, a screenshot, or a command containing the literal URL. The
> repository Alertmanager manifest contains a placeholder, not a working
> configuration. Use the private local-file procedure below for live delivery.
> Treat webhook URLs as credentials and revoke any URL that has been exposed.

## Contents

1. [Prerequisites](#1-prerequisites)
2. [Sprint 5 components](#2-sprint-5-components)
3. [Deploy the updated health-checker](#3-deploy-the-updated-health-checker)
4. [Configure the health-checker notifier](#4-configure-the-health-checker-notifier)
5. [Configure Alertmanager](#5-configure-alertmanager)
6. [Verify notifications and alerts](#6-verify-notifications-and-alerts)
7. [Troubleshooting and cleanup](#7-troubleshooting-and-cleanup)
8. [Checklist](#8-checklist)

## 1. Prerequisites

Run commands in **Ubuntu/WSL** from the repository root:

```bash
cd /mnt/c/Users/CBhalla/Desktop/herovired/capstone_eks/Capstone_Project_HeroVired
aws eks update-kubeconfig --region us-east-1 --name gratitude-health-cluster
kubectl get nodes
kubectl get pods -n default
kubectl get pods -n monitoring
```

The EKS context, GratitudeApp, health-checker, and kube-prometheus-stack
(Prometheus, Grafana, and Alertmanager) must be healthy. This guide assumes
the Alertmanager service is `monitoring-kube-prometheus-alertmanager` and the
existing chart release is `monitoring`. Verify actual names first:

```bash
kubectl get svc -n monitoring
kubectl get alertmanager -n monitoring
```

If the monitoring stack is not installed, complete its existing EKS setup
before proceeding. Do not reinstall Helm or replace the monitoring release as
part of this sprint.

## 2. Sprint 5 components

| Component | Project location |
|---|---|
| Mock/live Slack notifier | `k8s-health-checker/healthchecker-app/slack_notifier.py` |
| Healing notifications and API endpoints | `k8s-health-checker/healthchecker-app/healer.py`, `main.py` |
| Health-checker Kubernetes Deployment | `k8s-health-checker/deploy/healthchecker/deployment.yaml` |
| Multi-severity Alertmanager configuration | `k8s-health-checker/deploy/alerts/alertmanager-config.yaml` |
| User-facing notification documentation | `docs/alerting-and-notifications.md` |

The notifier runs inside the health-checker container. `POST
/api/notify/slack` sends a manual test notification, and `GET
/api/notifications` returns the in-memory history of recent notifications.
This history resets when the health-checker pod restarts.

## 3. Deploy the updated health-checker

Build/push the EKS image if the image in ECR does not yet contain the Sprint 5
notifier code:

```bash
sed -i 's/\r$//' k8s-health-checker/scripts/00-build-and-push-healthchecker.sh
bash ./k8s-health-checker/scripts/00-build-and-push-healthchecker.sh
```

Check that the ECR image URI in the script output matches `image:` in
`k8s-health-checker/deploy/healthchecker/deployment.yaml`. The manifest should
use `imagePullPolicy: Always` for the mutable `latest` tag.

Apply the deployment and restart to fetch the pushed image:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
kubectl rollout restart deployment/health-checker-deployment -n default
kubectl rollout status deployment/health-checker-deployment -n default --timeout=180s
kubectl get pods -n default -l component=health-checker
```

If `latest` is already current, the image build/push can be omitted.

## 4. Configure the health-checker notifier

### Mock mode (recommended initial validation)

The deployment's empty `SLACK_WEBHOOK_URL` enables mock mode. No outgoing Slack
message is sent; notifications are recorded in the health-checker logs and
in-memory history.

Confirm the deployment still has an empty URL and test mock mode in
[Verify notifications and alerts](#6-verify-notifications-and-alerts).

### Optional live Slack mode

Create a Kubernetes Secret from a temporary private file in WSL. This avoids
putting the URL in shell history or a tracked project file:

```bash
umask 077
read -rsp "Slack incoming webhook URL: " SLACK_WEBHOOK_URL
printf 'SLACK_WEBHOOK_URL=%s\n' "$SLACK_WEBHOOK_URL" > /tmp/health-checker-slack.env
unset SLACK_WEBHOOK_URL

kubectl create secret generic health-checker-slack \
  --namespace default \
  --from-env-file=/tmp/health-checker-slack.env \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/health-checker-slack.env
```

Edit `k8s-health-checker/deploy/healthchecker/deployment.yaml`. Replace the
current `SLACK_WEBHOOK_URL` environment entry (`value: ""`) with:

```yaml
            - name: SLACK_WEBHOOK_URL
              valueFrom:
                secretKeyRef:
                  name: health-checker-slack
                  key: SLACK_WEBHOOK_URL
```

Apply the edited manifest and restart the pod:

```bash
kubectl apply -f k8s-health-checker/deploy/healthchecker/deployment.yaml
kubectl rollout restart deployment/health-checker-deployment -n default
kubectl rollout status deployment/health-checker-deployment -n default --timeout=180s
```

The manifest change references the Kubernetes Secret name only; do not add the
webhook value to the manifest. Restrict access to the Secret through AWS IAM
and Kubernetes RBAC. For environments requiring stronger at-rest/rotation
controls, use the organization's approved secret-management integration.

## 5. Configure Alertmanager

The project file `k8s-health-checker/deploy/alerts/alertmanager-config.yaml`
contains a sample routing config, but its URL is a placeholder. **Do not apply
that file unchanged.** First confirm which Secret the deployed Alertmanager
resource references:

```bash
kubectl get alertmanager -n monitoring -o yaml | grep -A3 -B2 configSecret
kubectl get secret -n monitoring
```

The project sample expects the Secret
`alertmanager-monitoring-kube-prometheus-alertmanager` with key
`alertmanager.yaml`. Continue only if that is the config Secret used by this
Alertmanager instance. Otherwise adapt the name/key to the actual release.
If Helm or the operator manages this Secret, use that release's supported
configuration path instead of directly applying a Secret that will be
reconciled or overwritten.

Make a private WSL copy of the sample. It is not a committed project file:

```bash
umask 077
cp k8s-health-checker/deploy/alerts/alertmanager-config.yaml /tmp/alertmanager-config.yaml
```

Edit `/tmp/alertmanager-config.yaml` and replace the placeholder URL only
when enabling live Slack. Keep all receiver names, routing, and valid
Alertmanager YAML intact. The copied file is a Kubernetes Secret manifest
whose `stringData.alertmanager.yaml` value is the Alertmanager configuration.
For local-only/mock testing, skip the Alertmanager Secret update entirely:
Alertmanager itself does not implement the health-checker's mock behavior,
and the placeholder is not a valid live Slack endpoint.

For live Slack delivery only, after replacing the placeholder with the real
webhook in the private copy, apply that Secret manifest:

```bash
kubectl apply -f /tmp/alertmanager-config.yaml
rm -f /tmp/alertmanager-config.yaml
```

The sample routes `critical`, `warning`, and `info` severities to the
corresponding Slack receivers. Applying a replacement config can affect all
Alertmanager notifications, so inspect the final local file before applying.
Do not print or paste the file content into logs or screenshots. If you chose
mock mode, remove the unused private copy without applying it:

```bash
rm -f /tmp/alertmanager-config.yaml
```

Check Alertmanager logs for a successful configuration reload or parse errors:

```bash
kubectl get pods -n monitoring
kubectl logs -n monitoring alertmanager-monitoring-kube-prometheus-alertmanager-0 \
  -c alertmanager --tail=50
```

If the pod name differs, use the Alertmanager pod listed by `kubectl get pods`.
Do not delete/restart Alertmanager solely to force a reload unless the logs
show reload failed and you have reviewed the impact.

## 6. Verify notifications and alerts

Start a health-checker port-forward in one WSL terminal; keep the terminal
open:

```bash
kubectl port-forward -n default svc/health-checker-cluster-ip-service 8000:8000
```

From a second WSL terminal, send a test message:

```bash
curl -s -X POST http://localhost:8000/api/notify/slack \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "EKS Sprint 5 test",
    "message": "Checking notification integration.",
    "severity": "warning",
    "fields": {
      "Environment": "EKS test",
      "Cluster": "gratitude-health-cluster"
    }
  }' | python3 -m json.tool
```

In mock mode, expect a successful simulated result. Check the pod log and
notification history:

```bash
kubectl logs -n default deployment/health-checker-deployment --tail=50
curl -s http://localhost:8000/api/notifications | python3 -m json.tool
```

For optional end-to-end Alertmanager routing verification, use an
**non-HPA-managed** test Deployment in a non-production environment. Scaling
`entries-deployment` to zero can trigger the project's degraded-deployment
alert; first record its current replica count, then restore that exact count
after observing the alert. Run the scale/restore commands in the same terminal:

```bash
ORIGINAL_REPLICAS=$(kubectl get deployment entries-deployment -n default \
  -o jsonpath='{.spec.replicas}')
echo "Recorded replicas: $ORIGINAL_REPLICAS"
kubectl scale deployment entries-deployment --replicas=0 -n default
```

Allow the Prometheus rule's evaluation/`for` period to elapse, then check the
Alertmanager UI via a local-only port-forward:

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-alertmanager 9093:9093
```

Open `http://localhost:9093` and inspect active alerts/routing. In the
terminal where `ORIGINAL_REPLICAS` was recorded, restore that count:

```bash
kubectl scale deployment entries-deployment --replicas="$ORIGINAL_REPLICAS" -n default
kubectl rollout status deployment/entries-deployment -n default
```

Do not perform this test if `entries-deployment` is already degraded, if it is
serving users, or if you cannot restore its prior replica count. An alert can
be validated from Alertmanager without requiring a real Slack delivery;
mock mode applies only to health-checker notifications.

## 7. Troubleshooting and cleanup

### Health-checker reports mock delivery

That is expected when `SLACK_WEBHOOK_URL` is unset. For live delivery, verify
the pod uses the Secret reference, the Secret exists, and the pod was
restarted. Never print the Secret value:

```bash
kubectl describe secret health-checker-slack -n default
kubectl describe deployment health-checker-deployment -n default
kubectl logs -n default deployment/health-checker-deployment --tail=50
```

`describe secret` reports metadata/key names, not the credential value.

### Alertmanager reports configuration errors

Check the Alertmanager logs, Secret name/key, YAML indentation, and whether
the installed Alertmanager version supports the config options in the sample.
Do not overwrite the existing monitoring configuration until you have a
known-good replacement.

### Remove the optional health-checker Slack Secret

Only do this after reverting the Deployment to mock mode:

```bash
kubectl delete secret health-checker-slack -n default
```

Do not delete the Alertmanager config Secret to disable Slack; that Secret may
contain the active Alertmanager configuration. Restore a reviewed safe config
instead.

## 8. Checklist

- [ ] Health-checker Sprint 5 image is running in EKS.
- [ ] Mock test succeeds and is visible in logs/history, or a Secret-backed
      live webhook is configured without committing it.
- [ ] Alertmanager's actual config Secret was verified before updating.
- [ ] No placeholder/real webhook value was committed or included in output.
- [ ] Optional degraded-deployment test was restored to its original replica
      count.
