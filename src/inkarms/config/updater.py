"""
Configuration updater for InkArms.

Fetches model lists from provider APIs and updates the local configuration.
"""

import logging
import os
from datetime import datetime
from typing import Any

import httpx
import yaml

from inkarms.config.providers import PROVIDERS, ModelInfo
from inkarms.secrets import SecretsManager
from inkarms.storage.paths import get_inkarms_home

logger = logging.getLogger(__name__)


async def fetch_and_update_models() -> None:
    """
    Fetch available models from provider APIs and update user configuration.

    This runs silently and best-effort. Failures are suppressed/logged.
    """
    try:
        # logger.info("Starting background model discovery...")
        updated_models = {}

        # Iterate over all providers
        # Note: We iterate over keys to avoid modification issues if PROVIDERS changes
        provider_ids = list(PROVIDERS.keys())

        for provider_id in provider_ids:
            provider = PROVIDERS[provider_id]

            # Skip if no API endpoint configured
            if not provider.api_models_endpoint or not provider.api_models_mapper:
                continue

            # Get API key
            api_key = _get_api_key(provider.env_var)
            if not api_key:
                continue
            try:
                # Fetch models
                fetched_models = await _fetch_provider_models(
                    provider.api_models_endpoint, provider.api_models_mapper, api_key
                )

                # Filter out models that are already known (in defaults or user config)
                known_ids = {m.id for m in provider.models}
                new_models = [m for m in fetched_models if m.id not in known_ids]

                if new_models:
                    updated_models[provider_id] = new_models
                    logger.info(f"Found {len(new_models)} new models for {provider_id}")
            except Exception as e:
                logger.debug(f"Failed to fetch models for {provider_id}: {e}")

        # If we found any new models, update configuration
        if updated_models:
            _update_user_config(updated_models)
    except Exception as e:
        logger.debug(f"Model update process failed: {e}")


def _get_api_key(env_var: str | None) -> str | None:
    """Get API key from environment or secrets."""
    if not env_var:
        return None

    # Check env var first
    key = os.environ.get(env_var)
    if key:
        return key

    # Check secrets manager
    try:
        secrets = SecretsManager()
        # Map env var to secret key (e.g. ANTHROPIC_API_KEY -> anthropic_api_key)
        secret_key = env_var.lower()
        return secrets.get(secret_key)
    except Exception:
        return None


async def _fetch_provider_models(endpoint: str, mapper: str, api_key: str) -> list[ModelInfo]:
    """Fetch and map models from a specific provider."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        if mapper == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            response = await client.get(endpoint, headers=headers)
            response.raise_for_status()
            return _map_anthropic_models(response.json())

        elif mapper == "google":
            # Google uses query param for key
            params = {"key": api_key}
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
            return _map_google_models(response.json())

        return []


def _map_anthropic_models(data: dict[str, Any]) -> list[ModelInfo]:
    """Map Anthropic API response to ModelInfo objects."""
    models = []
    # Response format: {"data": [{"id": "...", "display_name": "...", ...}]}
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


def _map_google_models(data: dict[str, Any]) -> list[ModelInfo]:
    """Map Google Gemini API response to ModelInfo objects."""
    models = []
    # Response format: {"models": [{"name": "models/...", "displayName": "...", ...}]}
    for item in data.get("models", []):
        name = item.get("name", "")
        # Remove "models/" prefix
        model_id = name.replace("models/", "") if name.startswith("models/") else name

        if not model_id or "gemini" not in model_id:
            continue

        models.append(
            ModelInfo(
                id=model_id,
                name=item.get("displayName", model_id),
                description=item.get("description", ""),
                context_window=item.get("inputTokenLimit", 32000),
            )
        )
    return models


def _update_user_config(new_models_map: dict[str, list[ModelInfo]]) -> None:
    """
    Merge fetched models into user configuration file.

    Args:
        new_models_map: Dictionary mapping provider_id to list of ModelInfo objects.
    """
    config_path = get_inkarms_home() / "providers.yaml"

    # Ensure directory exists
    if not config_path.parent.exists():
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create config directory {config_path.parent}: {e}")
            return

    # Load existing user config
    user_config = {}
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
        except Exception:
            # If invalid, start fresh or abort? Safest to abort to not lose user data
            logger.warning("Could not read providers.yaml, skipping update")
            return

    if "providers" not in user_config:
        user_config["providers"] = {}

    changes_made = False

    for provider_id, fetched_models in new_models_map.items():
        if provider_id not in user_config["providers"]:
            user_config["providers"][provider_id] = {}

        provider_section = user_config["providers"][provider_id]

        # Initialize models list if needed
        if "models" not in provider_section:
            provider_section["models"] = []

        current_models = provider_section["models"]
        existing_ids = {m["id"] for m in current_models if "id" in m}

        # Add ONLY new models
        for model in fetched_models:
            if model.id not in existing_ids:
                # Convert dataclass to dict
                model_dict = {
                    "id": model.id,
                    "name": model.name,
                    "description": model.description,
                    "context_window": model.context_window,
                }
                # Remove empty fields to keep YAML clean
                if not model_dict["description"]:
                    del model_dict["description"]

                current_models.append(model_dict)
                changes_made = True

    # Save back if changes were made
    if changes_made:
        # Add metadata comment
        if "_meta" not in user_config:
            user_config["_meta"] = {}
        user_config["_meta"]["last_updated"] = datetime.now().isoformat()

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(user_config, f, sort_keys=False, allow_unicode=True)
            logger.info("Updated providers.yaml with new models")
        except Exception as e:
            logger.error(f"Failed to write providers.yaml: {e}")
