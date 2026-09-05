"""
Mairon desktop visual tokens.

Phase 10.2 establishes one named default theme rather than scattering literal
colours through the client. A future in-app theme editor can replace these
tokens without changing the application/Core boundary.
"""


MAIRON_THEME = {
    # Oliver-selected Mairon palette.
    "app_bg": "#1A1B2F",
    "surface": "#16213E",
    "surface_hover": "#552C4A",
    "accent": "#D44963",
    "border": "#343157",

    # Supporting text colours selected for readable contrast while keeping
    # the cool, muted Mairon palette.
    "text_primary": "#F4F1F6",
    "text_secondary": "#B6B3C7",
    "text_muted": "#7D7A95",

    # State colours remain deliberately restrained.
    "success": "#6CBF84",
    "warning": "#D6A85F",
    "danger": "#D96872",
}


FONT_PREFERENCES = (
    "Plus Jakarta Sans",
    "Inter",
    "Segoe UI",
)


CORNER_RADIUS = {
    "panel": 18,
    "composer": 20,
    "chip": 14,
}
