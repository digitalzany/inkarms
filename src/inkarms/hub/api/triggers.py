"""
Hub webhook trigger ingress.

POST /triggers/{name}

Fires an AI agent action when an external system POSTs to a named trigger
route. Routes are defined in hub.triggers config list (HubTriggerRoute).

Security:
- Body size limit enforced before parsing (trigger_max_body_bytes, default 1 MB)
- Content-Type: application/json required
- HMAC-SHA256 signature verified if trigger.shared_secret is set
  (header: X-Hub-Signature-256 or trigger.secret_header)
  Prefix "sha256=" stripped before compare_digest to guarantee equal-length
  comparison (constant-time safety).

Template rendering:
- Safe dot-path resolver only — str.format_map() is NOT used
  (format string injection risk; see OWASP CWE-134)
- Placeholders: {body.x.y}, {headers.x}, {query.x}
- Max path depth: 5 segments
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from inkarms.config.loader import get_config

router = APIRouter()
logger = logging.getLogger(__name__)

# Maximum dot-path depth: prevents excessively deep traversal
_MAX_PATH_DEPTH = 5


# ---------------------------------------------------------------------------
# Template rendering — safe dot-path resolver
# ---------------------------------------------------------------------------


def render_template(template: str, body: dict, headers: dict, query: dict) -> str:
    """Replace {body.x.y}, {headers.x}, {query.x} placeholders safely.

    Only resolves explicit root namespaces (body, headers, query).
    Does not use str.format_map to prevent format-string injection.
    """
    context = {"body": body, "headers": headers, "query": query}

    def _replacer(m: re.Match[str]) -> str:
        root = m.group(1)
        path_str = m.group(2)
        parts = path_str.split(".")
        if len(parts) > _MAX_PATH_DEPTH:
            return ""
        obj: Any = context.get(root, {})
        for key in parts:
            if not isinstance(obj, dict):
                return ""
            obj = obj.get(key, "")
        return str(obj)

    # Strict pattern: requires explicit root (body|headers|query) to avoid
    # accidental matches on {arbitrary.thing}.
    # Allow hyphens in keys to support HTTP header names (e.g. x-event-type).
    return re.sub(
        r"\{(body|headers|query)\.([a-zA-Z0-9_.\-]+)\}",
        _replacer,
        template,
    )


# ---------------------------------------------------------------------------
# HMAC verification
# ---------------------------------------------------------------------------


def _verify_signature(
    body_bytes: bytes,
    shared_secret: str,
    provided_header: str,
) -> bool:
    """Verify HMAC-SHA256 signature from a webhook trigger request.

    Accepts header values with or without the "sha256=" prefix.
    Uses hmac.compare_digest for constant-time comparison.
    """
    # Strip "sha256=" prefix so both sides are plain hex digests
    provided = provided_header.removeprefix("sha256=")
    expected = hmac.new(
        shared_secret.encode(),
        body_bytes,
        hashlib.sha256,  # pass callable, not string, for forward compatibility
    ).hexdigest()
    return hmac.compare_digest(expected, provided)


# ---------------------------------------------------------------------------
# Trigger handler
# ---------------------------------------------------------------------------


@router.post("/triggers/{name}")
async def handle_trigger(name: str, request: Request) -> Response:
    """Fire an AI action based on a named trigger route."""
    config = get_config()

    # --- Find trigger route ---
    route = next(
        (t for t in config.hub.triggers if t.name == name),
        None,
    )
    if route is None:
        raise HTTPException(status_code=404, detail=f"Trigger {name!r} not found")

    # --- Body size limit (read raw bytes, before any parsing) ---
    max_bytes = config.hub.trigger_max_body_bytes
    body_bytes = await request.body()
    if len(body_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Request body exceeds {max_bytes} bytes",
        )

    # --- Content-Type check ---
    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    if content_type != "application/json":
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be application/json",
        )

    # --- Parse body ---
    try:
        body: dict = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    # --- HMAC signature verification ---
    if route.shared_secret:
        sig_header = request.headers.get(route.secret_header, "")
        if not sig_header:
            raise HTTPException(
                status_code=401,
                detail=f"Missing signature header: {route.secret_header}",
            )
        if not _verify_signature(body_bytes, route.shared_secret, sig_header):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # --- Render prompt template ---
    headers_dict = dict(request.headers)
    query_dict = dict(request.query_params)
    prompt = render_template(route.prompt_template, body, headers_dict, query_dict)

    if not prompt.strip():
        raise HTTPException(
            status_code=400,
            detail="Rendered prompt is empty — check prompt_template placeholders",
        )

    # --- Fire AI action (non-blocking background task) ---
    import asyncio
    asyncio.create_task(
        _fire_trigger_action(
            route=route,
            prompt=prompt,
            config=config,
        ),
        name=f"trigger-{name}",
    )

    return Response(
        content=json.dumps({"status": "accepted", "trigger": name}),
        media_type="application/json",
        status_code=202,
    )


async def _fire_trigger_action(route: Any, prompt: str, config: Any) -> None:
    """Run the AI action for a trigger in the background."""
    from inkarms.audit import get_audit_logger
    from inkarms.platforms.processor import MessageProcessor
    from inkarms.platforms.sessions import PlatformSessionStore

    logger.info("Trigger %r firing AI action (session=%s)", route.name, route.session_id)

    try:
        session_store = PlatformSessionStore()
        processor = MessageProcessor(
            tool_approval_callback=lambda _tc, _t: (
                config.hub.webhook_tool_approval_mode == "auto"
            ),
            session_store=session_store,
        )

        response = await processor.process(
            query=prompt,
            session_id=route.session_id,
        )

        logger.info(
            "Trigger %r completed (cost=%.4f tokens=%d)",
            route.name,
            response.cost,
            response.input_tokens + response.output_tokens,
        )

        get_audit_logger().log_hub_trigger_fired(
            trigger_name=route.name,
            result=response.content[:200] if response.content else "",
        )

    except Exception as exc:  # noqa: BLE001
        logger.error("Trigger %r action failed: %s", route.name, exc, exc_info=True)
