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
    - SessionMapper: Maps platform users to session IDs
"""

from inkarms.platforms.models import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    PlatformUser,
)
from inkarms.platforms.protocol import PlatformAdapter

__all__ = [
    "PlatformAdapter",
    "PlatformType",
    "PlatformUser",
    "PlatformCapabilities",
    "IncomingMessage",
    "OutgoingMessage",
]
