"""Platform adapter implementations."""

from inkarms.platforms.adapters.cli import CLIAdapter
from inkarms.platforms.adapters.telegram import TelegramAdapter
from inkarms.platforms.adapters.slack import SlackAdapter
from inkarms.platforms.adapters.discord import DiscordAdapter

__all__ = [
    "CLIAdapter",
    "TelegramAdapter",
    "SlackAdapter",
    "DiscordAdapter",
]
