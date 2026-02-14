"""Multi-platform messaging integration for InkArms.

This module provides a platform adapter protocol and implementations for various
messaging platforms including Telegram, Slack, Discord, WhatsApp, iMessage, Signal,
Microsoft Teams, and WeChat.

Architecture:
    Platform Adapters → Message Router → Message Processor → Core Components

Key Components:
    - PlatformAdapter: Abstract protocol for platform implementations
    - MessageRouter: Routes messages between platforms and processor
    - MessageProcessor: Platform-agnostic message processing
    - SessionMapper: Maps platform channels to session IDs
    - PlatformSessionStore: Per-channel SessionManager cache
"""

from inkarms.models.platforms import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    PlatformUser,
)
from inkarms.platforms.adapters.protocol import PlatformAdapter
from inkarms.platforms.sessions import PlatformSessionStore

__all__ = [
    "IncomingMessage",
    "OutgoingMessage",
    "PlatformAdapter",
    "PlatformCapabilities",
    "PlatformSessionStore",
    "PlatformType",
    "PlatformUser",
]
