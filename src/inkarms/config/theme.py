from prompt_toolkit.styles import Style

THEME_STYLES = {
    # Branding
    "brand": "bold #00d4ff",
    "tagline": "italic #666666",
    # Status bar
    "status-bar": "bg:#1a1a2e #666666",
    "status-provider": "bg:#1a1a2e #00d4ff",
    "status-model": "bg:#1a1a2e #ffffff",
    "status-session": "bg:#1a1a2e #00ff88",
    "status-tokens": "bg:#1a1a2e #888888",
    "status-cost": "bg:#1a1a2e #ffaa00",
    # Menu
    "title": "bold #00d4ff",
    "subtitle": "#888888",
    "menu-item": "#fcfcfc",
    "menu-selected": "bold #00d4ff",
    "menu-desc": "#a9a9a9",
    # Chat
    "header": "bold #00d4ff",
    "user": "bold #00d4ff",
    "assistant": "#00ff88",
    "user-input": "#c9c9c9",
    # General
    "info": "#c9c9c9",
    "success": "#00ff88",
    "warning": "#ffaa00",
    "error": "#ff6b6b",
    "prompt": "bold #e94560",
    "hint": "#a9a9a9",
    "hint-dim": "#3a3a3a",
    "frame": "#333333",
    # Completion menu
    "completion-menu": "bg:#1a1a2e #ffffff",
    "completion-menu.completion": "bg:#1a1a2e #ffffff",
    "completion-menu.completion.current": "bg:#0f3460 #00d4ff bold",
    "completion-menu.meta.completion": "bg:#1a1a2e #666666",
    "completion-menu.meta.completion.current": "bg:#0f3460 #888888",
}

STYLE = Style.from_dict(THEME_STYLES)

LOGO = """
     █ █▄ █ █▄▀ ▄▀█ █▀█ █▀▄▀█ █▀
     █ █ ▀█ █ █ █▀█ █▀▄ █ ▀ █ ▄█
"""
