from prompt_toolkit.styles import Style

THEME_STYLES = {
    # Branding
    "brand": "bold #00d4ff",
    "tagline": "italic #a9a9a9",
    # Status bar
    "status-bar": "#666666",
    "status-provider": "#00d4ff",
    "status-model": "#ffffff",
    "status-session": "#00ff88",
    "status-tokens": "#888888",
    "status-cost": "#ffaa00",
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
    "assistant-panel": "dim #00ff88",
    "assistant-text": "#c9c9c9",
    "user-input": "#c9c9c9",
    # General
    "info": "#c9c9c9",
    "success": "#00ff88",
    "warning": "#ffaa00",
    "error": "#ff6b6b",
    "prompt": "bold #e94560",
    "hint": "#a9a9a9",
    "hint-dim": "#666666",
    "frame": "#666666",
    # Completion menu
    "completion-menu": "#ffffff",
    "completion-menu.completion": "#ffffff",
    "completion-menu.completion.current": "#00d4ff bold",
    "completion-menu.meta.completion": "#666666",
    "completion-menu.meta.completion.current": "#888888",
}

STYLE = Style.from_dict(THEME_STYLES)

LOGO = """
▄▄▄▄▄ ▄▄▄    ▄▄▄ ▄▄▄   ▄▄▄   ▄▄▄▄   ▄▄▄▄▄▄▄   ▄▄▄      ▄▄▄  ▄▄▄▄▄▄▄ 
 ███  ████▄  ███ ███ ▄███▀ ▄██▀▀██▄ ███▀▀███▄ ████▄  ▄████ █████▀▀▀ 
 ███  ███▀██▄███ ███████   ███  ███ ███▄▄███▀ ███▀████▀███  ▀████▄  
 ███  ███  ▀████ ███▀███▄  ███▀▀███ ███▀▀██▄  ███  ▀▀  ███    ▀████ 
▄███▄ ███    ███ ███  ▀███ ███  ███ ███  ▀███ ███      ███ ███████▀ 
"""
