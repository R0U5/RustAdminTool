"""UI design tokens for Rust Admin Tool (R.A.T.) - Plain UI version

This module centralises colour, spacing and radius definitions for a plain Tkinter UI.
Colors are simplified for a clean, normal appearance.
"""

# -- Colours ---------------------------------------------------------------
# Simple, clean colors for a plain UI
COLORS = {
    "bg_base": "#2b2b2b",           # Dark gray for main background
    "bg_elevated": "#323232",       # Slightly lighter for elevated elements
    "bg_surface": "#ffffff",        # White for surfaces/cards
    "bg_hover": "#3a3a3a",          # Hover state
    "bg_active": "#404040",         # Active/pressed state
    "border_subtle": "#4a4a4a",     # Subtle borders
    "border_default": "#5a5a5a",    # Default borders
    "border_focus": "#1f538d",      # Focused border (blue)
    "text_primary": "#ffffff",      # Primary text (white on dark bg)
    "text_secondary": "#b0b0b0",    # Secondary text
    "text_tertiary": "#808080",     # Tertiary text/disabled
    "accent": "#1f538d",            # Accent color (blue)
    "accent_hover": "#2b63a0",      # Accent hover
    "accent_light": "#e6f0ff",      # Accent light (for highlights)
    "success": "#28a745",           # Success green
    "success_subtle": "#d4edda",    # Success subtle background
    "warning": "#ffc107",           # Warning orange
    "warning_subtle": "#fff3cd",    # Warning subtle background
    "danger": "#dc3545",            # Danger red
    "danger_subtle": "#f8d7da",     # Danger subtle background
    "info": "#17a2b8",              # Info blue
    "info_subtle": "#d1ecf1",       # Info subtle background
}

# -- Spacing ---------------------------------------------------------------
# Values are expressed in pixels – these map directly to the original
# numeric string keys used throughout RAT.py so we keep the same naming.
SPACE = {
    "1": 4,   # 0.25rem (4px)
    "2": 8,   # 0.5rem
    "3": 12,  # 0.75rem
    "4": 16,  # 1rem
    "5": 20,  # 1.25rem
    "6": 24,  # 1.5rem
    "8": 32,  # 2rem
}

# -- Border radius ----------------------------------------------------------
RADIUS = {
    "sm": 4,
    "md": 8,
    "lg": 12,
    "xl": 16,
}