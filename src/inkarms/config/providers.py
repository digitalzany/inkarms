"""
Centralized configuration for AI providers and models.

This module acts as the single source of truth for supported providers,
models, context windows, and other provider-specific metadata.

It loads defaults from src/inkarms/config/defaults/providers.yaml and
merges overrides from ~/.inkarms/providers.yaml.
"""

import yaml

from pathlib import Path
from pydantic import BaseModel, model_validator

from inkarms.config.merger import deep_merge
from inkarms.storage.paths import get_inkarms_home


class ModelInfo(BaseModel):
    """Information about a specific AI model."""

    id: str
    name: str
    description: str = ""
    context_window: int = 128_000
    cost_per_m_in: float = 0.0
    cost_per_m_out: float = 0.0
    recommended: bool = False
    deprecated: bool = False


class ProviderInfo(BaseModel):
    """Information about an AI provider."""

    id: str
    name: str
    models: list[ModelInfo]
    description: str = ""
    env_var: str | None = None
    setup_instructions: str = ""
    default_model: str | None = None
    default_context_window: int = 32000
    is_local: bool = False
    api_models_endpoint: str | None = None
    api_models_mapper: str | None = None

    @model_validator(mode="after")
    def validate_model_context_window(self):
        for model in self.models:
            model.context_window = model.context_window or self.default_context_window
        return self


# Cache for providers data
_CACHED_PROVIDERS: dict[str, ProviderInfo] | None = None


def load_providers_config() -> dict[str, ProviderInfo]:
    """
    Load providers configuration from defaults and user overrides.

    Returns:
        Dictionary mapping provider IDs to ProviderInfo objects.
    """
    # 1. Load base defaults from package
    base_config_path = Path(__file__).parent / "defaults" / "providers.yaml"
    base_data = {}
    if base_config_path.exists():
        try:
            with open(base_config_path, encoding="utf-8") as f:
                content = yaml.safe_load(f)
                if content and "providers" in content:
                    base_data = content["providers"]
        except Exception as e:
            # Fallback (should typically log this)
            print(f"Error loading base providers config: {e}")

    # 2. Load user overrides from ~/.inkarms/providers.yaml
    user_config_path = get_inkarms_home() / "providers.yaml"
    user_data = {}
    if user_config_path.exists():
        try:
            with open(user_config_path, encoding="utf-8") as f:
                content = yaml.safe_load(f)
                if content and "providers" in content:
                    user_data = content["providers"]
        except Exception:
            # Ignore user config errors, fallback to defaults
            pass

    # 3. Merge configurations
    # deep_merge handles merging dictionaries and replacing lists by default.
    # To append to lists (like models), users would need to use "+models" key,
    # but our deep_merge implementation supports that.
    merged_data = deep_merge(base_data, user_data)

    # 4. Convert to objects
    providers = {}
    for provider_id, p_data in merged_data.items():
        # Parse models
        models = []
        if "models" in p_data:
            for m_data in p_data["models"]:
                models.append(ModelInfo(**m_data))

        # Create ProviderInfo
        # Filter out 'models' from kwargs to avoid double passing
        p_kwargs = {k: v for k, v in p_data.items() if k != "models"}

        providers[provider_id] = ProviderInfo(models=models, **p_kwargs)

    return providers


def _get_providers() -> dict[str, ProviderInfo]:
    """Get providers, loading if not already cached."""
    global _CACHED_PROVIDERS
    if _CACHED_PROVIDERS is None:
        _CACHED_PROVIDERS = load_providers_config()
    return _CACHED_PROVIDERS


# Lazy proxy for PROVIDERS to maintain compatibility while loading dynamically
class ProvidersProxy(dict):
    def __init__(self):
        pass

    def _ensure_loaded(self):
        if not _CACHED_PROVIDERS:
            _get_providers()

    def __getitem__(self, key):
        self._ensure_loaded()
        providers = _CACHED_PROVIDERS
        assert providers is not None
        return providers[key]

    def __iter__(self):
        self._ensure_loaded()
        providers = _CACHED_PROVIDERS
        assert providers is not None
        return iter(providers)

    def __len__(self):
        self._ensure_loaded()
        providers = _CACHED_PROVIDERS
        assert providers is not None
        return len(providers)

    def items(self):
        self._ensure_loaded()
        providers = _CACHED_PROVIDERS
        assert providers is not None
        return providers.items()

    def keys(self):
        self._ensure_loaded()
        providers = _CACHED_PROVIDERS
        assert providers is not None
        return providers.keys()

    def values(self):
        self._ensure_loaded()
        providers = _CACHED_PROVIDERS
        assert providers is not None
        return providers.values()

    def get(self, key, default=None):
        self._ensure_loaded()
        providers = _CACHED_PROVIDERS
        assert providers is not None
        return providers.get(key, default)

    def __contains__(self, key):
        self._ensure_loaded()
        providers = _CACHED_PROVIDERS
        assert providers is not None
        return key in providers


# Export PROVIDERS as a proxy that loads on first access
PROVIDERS = ProvidersProxy()


# Encodings for different model families (used by tiktoken)
ENCODING_MAP: dict[str, str] = {
    "anthropic": "cl100k_base",
    "openai": "cl100k_base",
    "google": "cl100k_base",  # Approximation
    "github_copilot": "cl100k_base",
    "ollama": "cl100k_base",  # Approximation
    "default": "cl100k_base",
}


# Context windows helper
def get_context_window(model_id: str) -> int:
    """Get context window for a model ID (provider/model or just model)."""
    providers = _get_providers()

    # Try exact match (e.g. "anthropic/claude-sonnet-4...")
    if "/" in model_id:
        provider_id, specific_model = model_id.split("/", 1)
        if provider_id in providers:
            for m in providers[provider_id].models:
                if m.id == specific_model:
                    return m.context_window

    # Try model ID match across all providers
    for p in providers.values():
        for m in p.models:
            if m.id == model_id:
                return m.context_window

    return 128_000  # Default


# Derived mapping for context windows (compatibility wrapper)
# This behaves like a dict but queries the loaded providers on access
class ContextWindowMap(dict):
    def __getitem__(self, key):
        if key == "default":
            return 128_000
        return get_context_window(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default if default is not None else 128_000

    def __contains__(self, key):
        if key == "default":
            return True
        # Check if we can find it
        providers = _get_providers()
        for p in providers.values():
            for m in p.models:
                if m.id == key or f"{p.id}/{m.id}" == key:
                    return True
        return False


MODEL_CONTEXT_WINDOWS = ContextWindowMap()


def get_default_model() -> str:
    """Get the system-wide default model identifier."""
    providers = _get_providers()
    if "anthropic" in providers:
        return f"anthropic/{providers['anthropic'].default_model}"
    # Fallback to first available
    if providers:
        first_p = next(iter(providers.values()))
        return f"{first_p.id}/{first_p.default_model}"

    return "anthropic/claude-sonnet-4-20250514"


def get_provider_choices() -> list[tuple[str, str, str]]:
    """Get a list of providers for selection menus (id, name, description)."""
    providers = _get_providers()
    return [(p.id, p.name, p.description) for p in providers.values()]


def get_model_choices(provider_id: str) -> list[tuple[str, str, str]]:
    """Get a list of models for a provider for selection menus (id, name, description)."""
    providers = _get_providers()
    if provider_id not in providers:
        return [("default", "Default", "")]

    return [
        (m.id, m.name, m.description) for m in providers[provider_id].models if not m.deprecated
    ]


def get_model_info(model_identifier: str) -> ModelInfo | None:
    """Get model info from a full identifier (provider/model) or just model ID."""
    providers = _get_providers()
    parts = model_identifier.split("/")
    if len(parts) == 2:
        provider_id, model_id = parts
        if provider_id in providers:
            for model in providers[provider_id].models:
                if model.id == model_id:
                    return model
    else:
        # Try to find model ID across all providers
        model_id = model_identifier
        for provider in providers.values():
            for model in provider.models:
                if model.id == model_id:
                    return model
    return None
