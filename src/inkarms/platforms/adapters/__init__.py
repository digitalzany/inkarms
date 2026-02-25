"""Platform adapter implementations and bootstrap helpers."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from inkarms.platforms.adapters.discord import DiscordAdapter
from inkarms.platforms.adapters.protocol import PlatformAdapter
from inkarms.platforms.adapters.slack import SlackAdapter
from inkarms.platforms.adapters.telegram import TelegramAdapter

ADAPTER_CLASSES = [TelegramAdapter, SlackAdapter, DiscordAdapter]

__all__ = [
    "DiscordAdapter",
    "SlackAdapter",
    "TelegramAdapter",
    "create_adapters",
    "get_platform_metadata",
]

logger = logging.getLogger(__name__)


def get_platform_metadata() -> list[tuple[str, str, list]]:
    """Return (platform_key, display_name, wizard_fields) for all registered adapters."""
    return [(cls.PLATFORM_KEY, cls.DISPLAY_NAME, cls.WIZARD_FIELDS) for cls in ADAPTER_CLASSES]


def _get_config_value(config_dict: dict[str, Any], key: str, env_var: str) -> str | None:
    """Return config value, resolving ``${ENV_VAR}`` syntax to env, falling back to env_var."""
    value = config_dict.get(key)
    if value and isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.getenv(env_name)
    return value or os.getenv(env_var)


def _load_platform_secrets() -> None:
    """Load platform tokens from SecretsManager into env vars (if not already set)."""
    try:
        from inkarms.secrets import SecretsManager  # noqa: PLC0415

        secrets = SecretsManager()
        for cls in ADAPTER_CLASSES:
            for field in cls.WIZARD_FIELDS:
                if not field.is_secret:
                    continue
                secret_name = f"{cls.PLATFORM_KEY}_{field.key}"
                env_var = f"{cls.PLATFORM_KEY.upper()}_{field.key.upper()}"
                if not os.environ.get(env_var) and secrets.exists(secret_name):
                    value = secrets.get(secret_name)
                    if value:
                        os.environ[env_var] = value
    except Exception:
        logger.debug("Could not load platform secrets from SecretsManager")


def _try_create_adapter(
    name: str,
    import_path: str,
    class_name: str,
    pip_package: str,
    warn_callback: Callable[[str], None],
    **kwargs: Any,
) -> PlatformAdapter | None:
    """Try to import and instantiate a platform adapter.

    Args:
        name: Human-readable platform name (for warning messages).
        import_path: Module path to import.
        class_name: Adapter class name within the module.
        pip_package: ``pip install`` hint shown on ImportError.
        warn_callback: Called with warning text instead of using Rich/console directly.
        **kwargs: Passed to the adapter constructor.

    Returns:
        Adapter instance, or None on ImportError.
    """
    try:
        import importlib

        module = importlib.import_module(import_path)
        adapter_cls = getattr(module, class_name)
        return adapter_cls(**kwargs)
    except ImportError as exc:
        warn_callback(f"{name} adapter not available: {exc} — install with: pip install {pip_package}")
        return None


def create_adapters(
    config: Any,
    warn_callback: Callable[[str], None] | None = None,
) -> list[PlatformAdapter]:
    """Create enabled platform adapters from configuration.

    Extracted from ``cli/commands/platforms.py`` so both the CLI foreground
    mode and the hub daemon can share the same bootstrap logic.

    Args:
        config: Loaded ``Config`` object.
        warn_callback: Called with warning text when a platform is misconfigured
            or its dependency is missing.  Defaults to ``logger.warning``.

    Returns:
        List of constructed (but not yet started) adapters.
    """
    if warn_callback is None:
        warn_callback = logger.warning

    _load_platform_secrets()
    adapters: list[PlatformAdapter] = []

    # Telegram
    if config.platforms.telegram.enable:
        bot_token = _get_config_value(
            config.platforms.telegram.model_dump(), "bot_token", "TELEGRAM_BOT_TOKEN"
        )
        if bot_token:
            adapter = _try_create_adapter(
                "Telegram",
                "inkarms.platforms.adapters.telegram",
                "TelegramAdapter",
                "python-telegram-bot",
                warn_callback=warn_callback,
                bot_token=bot_token,
                allowed_users=config.platforms.telegram.allowed_users,
                parse_mode=config.platforms.telegram.parse_mode,
                polling_interval=config.platforms.telegram.polling_interval,
            )
            if adapter:
                adapters.append(adapter)
        else:
            warn_callback("Telegram enabled but bot_token not configured")

    # Slack
    if config.platforms.slack.enable:
        bot_token = _get_config_value(
            config.platforms.slack.model_dump(), "bot_token", "SLACK_BOT_TOKEN"
        )
        app_token = _get_config_value(
            config.platforms.slack.model_dump(), "app_token", "SLACK_APP_TOKEN"
        )
        if bot_token and app_token:
            adapter = _try_create_adapter(
                "Slack",
                "inkarms.platforms.adapters.slack",
                "SlackAdapter",
                "slack-sdk",
                warn_callback=warn_callback,
                bot_token=bot_token,
                app_token=app_token,
                allowed_channels=config.platforms.slack.allowed_channels,
            )
            if adapter:
                adapters.append(adapter)
        else:
            warn_callback("Slack enabled but bot_token/app_token not configured")

    # Discord
    if config.platforms.discord.enable:
        bot_token = _get_config_value(
            config.platforms.discord.model_dump(), "bot_token", "DISCORD_BOT_TOKEN"
        )
        if bot_token:
            adapter = _try_create_adapter(
                "Discord",
                "inkarms.platforms.adapters.discord",
                "DiscordAdapter",
                "discord.py",
                warn_callback=warn_callback,
                bot_token=bot_token,
                allowed_guilds=config.platforms.discord.allowed_guilds,
                allowed_channels=config.platforms.discord.allowed_channels,
                command_prefix=config.platforms.discord.command_prefix,
            )
            if adapter:
                adapters.append(adapter)
        else:
            warn_callback("Discord enabled but bot_token not configured")

    return adapters
