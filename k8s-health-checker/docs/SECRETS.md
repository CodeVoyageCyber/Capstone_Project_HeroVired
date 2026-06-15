# Secrets Configuration

Before running `scripts/02-deploy-gratitudeapp.sh`, review and update
these two files in `gratitude-k8s/`:

## 1. `gratitude-k8s/database-secret.yml`

Contains the Postgres password (base64-encoded). The default is
`postgres` (base64: `cG9zdGdyZXM=`), which is fine for a short-lived
demo cluster but should be changed for anything longer-lived.

To generate a new value:

```bash
echo -n "<new-password>" | base64
```

Then update the `PGPASSWORD` field with the output.

## 2. `gratitude-k8s/openai-api-secret.yml`

GratitudeApp's AI features call the OpenAI API. Replace the
placeholder with a real key:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: openai-api
type: Opaque
stringData:
  OPENAI_API_KEY: "sk-...your-real-key..."
```

If you don't have an OpenAI key, you can leave the placeholder — the
AI-related endpoints will simply fail/return errors, but the rest of
the app (entries, moods, stats, files, dashboard) will work normally.
This does not block the health-checker or monitoring sprints.

## Notes

- Both files are tracked in git for convenience in this learning
  project. For a real deployment, move secret values out of git
  (e.g. use a `.gitignore`'d override, AWS Secrets Manager + External
  Secrets Operator, or `kubectl create secret` directly).
- `files-service` S3/IRSA configuration is intentionally **not** set
  up yet (see README "Known Limitations"). The files-service pod may
  show errors related to S3 access until that's configured.
