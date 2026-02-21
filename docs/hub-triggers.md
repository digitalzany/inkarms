# Hub Trigger Routes

Trigger routes let external systems (GitHub, CI pipelines, monitoring tools) fire an AI action by sending a POST request to the hub.

Each trigger is a named route declared in config. When the hub receives a request for that route, it renders a prompt from the request body, then runs an AI agent action in the background.

---

## Configuration

```yaml
hub:
  triggers:
    - name: github-pr
      prompt_template: |
        A pull request was opened in {body.repository.name}.
        Title: {body.pull_request.title}
        Author: {body.pull_request.user.login}
        Please summarise what this PR does.
      session_id: "github-reviews"
      reply_to: null          # No reply routing — response is logged
```

### `HubTriggerRoute` fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | required | Route name — used in the URL `/triggers/{name}` |
| `prompt_template` | `str` | required | Template string with `{body.*}`, `{headers.*}`, `{query.*}` placeholders |
| `session_id` | `str` | `"default"` | Session ID to run the AI action in |
| `reply_to` | `str \| null` | `null` | Where to send the response (not yet implemented — response is logged) |
| `shared_secret` | `str \| null` | `null` | If set, the request must include a valid HMAC-SHA256 signature |
| `secret_header` | `str` | `"X-Hub-Signature-256"` | Header name containing the signature |

---

## Sending a Trigger Request

```bash
curl -X POST http://127.0.0.1:18750/triggers/github-pr \
  -H "Content-Type: application/json" \
  -d '{
    "repository": {"name": "inkarms"},
    "pull_request": {
      "title": "Add hub daemon",
      "user": {"login": "alice"}
    }
  }'

# Response (202 Accepted — action fires in background):
# {"status": "accepted", "trigger": "github-pr"}
```

The response is `202 Accepted` immediately. The AI action runs in a background task. Errors in the action are logged to `hub.log`.

---

## Template Syntax

Placeholders are replaced with values from the request. Three root namespaces are available:

| Placeholder | Source |
|-------------|--------|
| `{body.x.y.z}` | JSON request body, dot-path traversal |
| `{headers.x-header-name}` | Request headers (lowercase names) |
| `{query.param}` | Query string parameters |

**Examples:**

```
{body.repository.name}          → "inkarms"
{body.pull_request.user.login}  → "alice"
{headers.x-github-event}        → "pull_request"
{query.action}                  → value of ?action=... query param
```

### Safety Design

**`str.format_map()` is NOT used** — it would allow format-string injection attacks (CWE-134). The resolver uses a strict regex that only matches explicit root namespaces (`body`, `headers`, `query`). Arbitrary `{variable}` patterns are left unchanged.

```python
# Safe — only {body.*}, {headers.*}, {query.*} are replaced
template = "Hello {body.name}! Your {unknown.thing} is safe."
# → "Hello Alice! Your {unknown.thing} is safe."
```

Path depth is capped at 5 segments. Deeper paths return an empty string.

---

## HMAC Signature Verification

Protect public-facing triggers by signing requests with a shared secret. This is the same scheme used by GitHub webhooks.

### Config

```yaml
hub:
  triggers:
    - name: github-pr
      prompt_template: "PR in {body.repository.name}: {body.pull_request.title}"
      shared_secret: "my-very-secret-value"
      secret_header: "X-Hub-Signature-256"  # default
```

### Signing a request (Python)

```python
import hashlib, hmac, json, requests

secret = "my-very-secret-value"
body = json.dumps({"repository": {"name": "inkarms"}, "action": "opened"}).encode()
sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

requests.post(
    "http://127.0.0.1:18750/triggers/github-pr",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Hub-Signature-256": sig,
    },
)
```

### Signing with shell

```bash
SECRET="my-very-secret-value"
BODY='{"repository":{"name":"inkarms"}}'
SIG="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

curl -X POST http://127.0.0.1:18750/triggers/github-pr \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"
```

If `shared_secret` is set and the signature is missing or invalid, the hub returns `401 Unauthorized`.

---

## Request Validation

Before any template rendering or AI execution, the hub validates:

1. **Route exists** — returns `404` if trigger name is not in config
2. **Body size** — returns `413` if body exceeds `trigger_max_body_bytes` (default: 1 MB)
3. **Content-Type** — returns `415` if `Content-Type` is not `application/json`
4. **JSON validity** — returns `400` on malformed JSON
5. **HMAC signature** — returns `401` if `shared_secret` is set and signature is invalid/missing

---

## Security Model

Trigger routes use `hub.webhook_tool_approval_mode` (default: `"disabled"`) to control what tools the AI agent can use during a trigger-fired action.

```yaml
hub:
  webhook_tool_approval_mode: disabled   # No tools (AI query only — safe default)
  # webhook_tool_approval_mode: auto     # All tools allowed (use with caution)
```

The background task runs in the same event loop as the hub — a long-running AI query will not block other requests, but very large tool outputs could affect memory.

---

## Worked Examples

### GitHub Pull Request Review

```yaml
hub:
  triggers:
    - name: github-pr
      prompt_template: |
        A pull request was opened.
        Repo: {body.repository.full_name}
        Title: {body.pull_request.title}
        Author: {body.pull_request.user.login}
        Description: {body.pull_request.body}
        Please write a one-paragraph review summary.
      session_id: pr-reviews
      shared_secret: "${GITHUB_WEBHOOK_SECRET}"
```

### CI Build Failure Alert

```yaml
hub:
  triggers:
    - name: ci-failure
      prompt_template: |
        CI build failed on branch {body.branch} in {body.repository}.
        Failed step: {body.step_name}
        Error: {body.error_message}
        Suggest three likely causes and fixes.
      session_id: ci-alerts
```

### Monitoring Alert

```yaml
hub:
  triggers:
    - name: alert
      prompt_template: |
        Alert fired: {body.alertname}
        Severity: {body.labels.severity}
        Summary: {body.annotations.summary}
        What is the most likely cause and immediate mitigation?
      session_id: ops
      shared_secret: "alertmanager-secret"
      secret_header: "X-Alertmanager-Token"
```
