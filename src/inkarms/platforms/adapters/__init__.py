"""Platform adapter implementations."""

from inkarms.platforms.adapters.discord import DiscordAdapter
from inkarms.platforms.adapters.slack import SlackAdapter
from inkarms.platforms.adapters.telegram import TelegramAdapter

__all__ = [
    "DiscordAdapter",
    "SlackAdapter",
    "TelegramAdapter",
]
