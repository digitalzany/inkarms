"""
Background model discovery for InkArms.

Fetches the live model list from each configured provider and merges any
newly-discovered models into ``~/.inkarms/providers.yaml``.  The process
runs silently on startup; every failure is logged at DEBUG level so it
never interrupts the user.

Adding support for a new HTTP provider
---------------------------------------
1. Subclass ``_HttpFetcher`` and implement ``_build_headers``,
   optionally ``_build_params``, and ``_map_response``.
2. Add one entry to ``_HTTP_FETCHERS``.
3. Set ``api_models_endpoint`` and ``api_models_mapper`` for the provider
   in ``src/inkarms/config/defaults/providers.yaml``.

Adding support for a new local provider
-----------------------------------------
1. Subclass ``_LocalFetcher`` and implement ``fetch``.
2. Add one entry to ``_LOCAL_FETCHERS``.
3. Set ``api_models_mapper`` (and ``is_local: true``) for the provider
   in ``src/inkarms/config/defaults/providers.yaml``.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx
import yaml

from inkarms.config.providers import PROVIDERS, ModelInfo, ProviderInfo
from inkarms.secrets import SecretsManager
from inkarms.storage.paths import get_inkarms_home

logger = logging.getLogger(__name__)


class _HttpFetcher(ABC):
    """Base class for fetching models from a remote provider REST API."""

    async def fetch(self, endpoint: str, api_key: str) -> list[ModelInfo]:
        """GET *endpoint*, authenticate with *api_key*, return mapped models."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                endpoint,
                headers=self._build_headers(api_key),
                params=self._build_params(api_key),
            )
            response.raise_for_status()
            return self._map_response(response.json())

    @abstractmethod
    def _build_headers(self, api_key: str) -> dict[str, str]:
        """Return request headers (auth, content-type, …)."""

    def _build_params(self, api_key: str) -> dict[str, str]:  # noqa: ARG002
        """Return query-string parameters.  Override when the API uses them for auth."""
        return {}

    @abstractmethod
    def _map_response(self, data: dict[str, Any]) -> list[ModelInfo]:
        """Parse the raw JSON response into a list of ModelInfo objects."""


class _AnthropicFetcher(_HttpFetcher):
    def _build_headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _map_response(self, data: dict[str, Any]) -> list[ModelInfo]:
        # Response: {"data": [{"id": "...", "display_name": "...", "created_at": "...", "type": "model"}]}
        models = []
        for item in data.get("data", []):
            if item.get("type") != "model":
                continue
            model_id = item.get("id")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=item.get("display_name", model_id),
                    description=f"Released {item.get('created_at', '')[:10]}",
                )
            )
        return models


class _GeminiFetcher(_HttpFetcher):
    def _build_headers(self, api_key: str) -> dict[str, str]:  # noqa: ARG002
        return {}

    def _build_params(self, api_key: str) -> dict[str, str]:
        # Google uses a query-string key instead of a header
        return {"key": api_key}

    def _map_response(self, data: dict[str, Any]) -> list[ModelInfo]:
        # Response: {"models": [{"name": "models/gemini-…", "displayName": "…", …}]}
        models = []
        for item in data.get("models", []):
            raw_name = item.get("name", "")
            model_id = raw_name.removeprefix("models/")
            if not model_id or "gemini" not in model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=item.get("displayName", model_id),
                    description=item.get("description", ""),
                    context_window=item.get("inputTokenLimit", 32_000),
                )
            )
        return models


class _OpenAIFetcher(_HttpFetcher):
    # Prefixes that identify non-chat models (image, audio, embeddings, legacy).
    # New chat model families are included automatically without any code change.
    _EXCLUDED_PREFIXES: tuple[str, ...] = (
        "dall-e",
        "whisper",
        "tts",
        "text-embedding",
        "text-moderation",
        "omni-moderation",
        "babbage",
        "davinci",
        "cushman",
    )

    def _build_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def _map_response(self, data: dict[str, Any]) -> list[ModelInfo]:
        # Response: {"data": [{"id": "gpt-4o", "object": "model", "owned_by": "openai", …}]}
        models = []
        for item in data.get("data", []):
            model_id = item.get("id", "")
            if not model_id:
                continue
            if any(model_id.startswith(prefix) for prefix in self._EXCLUDED_PREFIXES):
                continue
            models.append(ModelInfo(id=model_id, name=model_id))
        return models


# Registry: mapper name → fetcher instance.
# To support a new HTTP provider, add one entry here.
_HTTP_FETCHERS: dict[str, _HttpFetcher] = {
    "anthropic": _AnthropicFetcher(),
    "gemini": _GeminiFetcher(),
    "openai": _OpenAIFetcher(),
}


class _LocalFetcher(ABC):
    """Base class for fetching models from a locally-running service."""

    @abstractmethod
    def fetch(self) -> list[ModelInfo]:
        """Return all models available from the local service."""


class _OllamaFetcher(_LocalFetcher):
    def fetch(self) -> list[ModelInfo]:
        try:
            import ollama  # optional dependency — imported lazily
        except ImportError:
            logger.debug("ollama package not installed; skipping local model discovery")
            return []

        try:
            raw_models = ollama.list().get("models", [])
        except Exception as exc:
            logger.debug("ollama.list() failed: %s", exc)
            return []

        return [
            ModelInfo(
                id=m.get("model", "ollama-model"),
                name=m.get("model", "ollama-model"),
                description=f"Modified at {m.get('modified_at', 'unknown')}",
            )
            for m in raw_models
        ]


# Registry: mapper name → fetcher instance.
# To support a new local provider, add one entry here.
_LOCAL_FETCHERS: dict[str, _LocalFetcher] = {
    "ollama": _OllamaFetcher(),
}


async def fetch_and_update_models() -> None:
    """Fetch available models from all configured providers and persist new ones.

    Runs silently and best-effort — every failure is suppressed so this never
    interrupts the user.
    """
    try:
        new_models: dict[str, list[ModelInfo]] = {}

        for provider_id, provider in PROVIDERS.items():
            if provider.is_local:
                models = _fetch_local_models(provider_id, provider)
            else:
                models = await _fetch_remote_models(provider_id, provider)

            if models:
                new_models[provider_id] = models

        if new_models:
            _update_user_config(new_models)

    except Exception as exc:
        logger.debug("Model update process failed: %s", exc)


async def _fetch_remote_models(
    provider_id: str, provider: ProviderInfo
) -> list[ModelInfo]:
    """Return models discovered from a remote API that aren't already known."""
    if not provider.api_models_endpoint or not provider.api_models_mapper:
        return []

    fetcher = _HTTP_FETCHERS.get(provider.api_models_mapper)
    if fetcher is None:
        logger.debug(
            "No HTTP fetcher registered for mapper %r (provider: %s)",
            provider.api_models_mapper,
            provider_id,
        )
        return []

    api_key = _get_api_key(provider.env_var, provider_id)
    if not api_key:
        return []

    try:
        all_models = await fetcher.fetch(provider.api_models_endpoint, api_key)
        known_ids = {m.id for m in provider.models}
        new_models = [m for m in all_models if m.id not in known_ids]
        if new_models:
            logger.info("Found %d new model(s) for %s", len(new_models), provider_id)
        return new_models
    except Exception as exc:
        logger.debug("Failed to fetch models for %s: %s", provider_id, exc)
        return []


def _fetch_local_models(provider_id: str, provider: ProviderInfo) -> list[ModelInfo]:
    """Return models discovered from a local service."""
    mapper = provider.api_models_mapper or provider_id
    fetcher = _LOCAL_FETCHERS.get(mapper)
    if fetcher is None:
        logger.debug(
            "No local fetcher registered for mapper %r (provider: %s)",
            mapper,
            provider_id,
        )
        return []

    try:
        return fetcher.fetch()
    except Exception as exc:
        logger.debug("Failed to fetch local models for %s: %s", provider_id, exc)
        return []


def _get_api_key(env_var: str | None, provider_id: str | None = None) -> str | None:
    """Return the API key from the environment or the secrets store.

    Lookup order:
    1. Environment variable (e.g. ``ANTHROPIC_API_KEY``).
    2. Secrets store keyed by provider ID (e.g. ``"anthropic"`` — how the
       config wizard persists keys via ``SecretsManager().set(provider, key)``).
    3. Secrets store keyed by the lowercase env-var name as a last resort.
    """
    if not env_var:
        return None

    value = os.environ.get(env_var)
    if value:
        return value

    try:
        secrets = SecretsManager()
        if provider_id:
            value = secrets.get(provider_id)
            if value:
                return value
        return secrets.get(env_var.lower())
    except Exception:
        return None


def _update_user_config(new_models_map: dict[str, list[ModelInfo]]) -> None:
    """Merge newly-discovered models into ``~/.inkarms/providers.yaml``.

    Only models whose ``id`` is not yet present in the file are appended;
    existing entries are never modified or removed.
    """
    config_path = get_inkarms_home() / "providers.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    user_config: dict[str, Any] = {}
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8") as fh:
                user_config = yaml.safe_load(fh) or {}
        except Exception:
            logger.warning(
                "Could not read %s — skipping model update to avoid data loss", config_path
            )
            return

    user_config.setdefault("providers", {})
    changes = False

    for provider_id, models in new_models_map.items():
        provider_section = user_config["providers"].setdefault(provider_id, {})
        existing = provider_section.setdefault("models", [])
        existing_ids = {m["id"] for m in existing if "id" in m}

        for model in models:
            if model.id in existing_ids:
                continue
            entry: dict[str, Any] = {"id": model.id, "name": model.name}
            if model.description:
                entry["description"] = model.description
            if model.context_window:
                entry["context_window"] = model.context_window
            existing.append(entry)
            changes = True

    if not changes:
        return

    user_config.setdefault("_meta", {})["last_updated"] = datetime.now().isoformat()
    try:
        with config_path.open("w", encoding="utf-8") as fh:
            yaml.dump(user_config, fh, sort_keys=False, allow_unicode=True)
        logger.info("Updated %s with new models", config_path)
        # Invalidate the in-process providers cache so the wizard and
        # any other callers immediately see the newly discovered models.
        from inkarms.config.providers import clear_providers_cache
        clear_providers_cache()
    except Exception as exc:
        logger.error("Failed to write %s: %s", config_path, exc)
