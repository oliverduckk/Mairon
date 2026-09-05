from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from application_service import (
    ApplicationTurn,
    MaironApplication,
)
from core.desktop_agent_client import (
    ping_desktop_agent,
)
from mairon_theme import (
    CORNER_RADIUS,
    FONT_PREFERENCES,
    MAIRON_THEME,
)
from voice.gui_voice import (
    VoiceRuntime,
)
from windows_app_identity import (
    ensure_single_instance_or_activate,
    set_windows_app_identity,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

AGENT_SCRIPT = (
    PROJECT_ROOT
    / "src"
    / "desktop_agent.py"
)

APP_ICON_PATH = (
    PROJECT_ROOT
    / "assets"
    / "mairon.ico"
)

CREATE_NO_WINDOW = getattr(
    subprocess,
    "CREATE_NO_WINDOW",
    0,
)

GWL_EXSTYLE = -20

WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36

DWMWCP_ROUND = 2

# COLORREF values are encoded as 0x00BBGGRR.
MAIRON_DWM_CAPTION_COLOR = 0x002F1B1A   # #1A1B2F
MAIRON_DWM_TEXT_COLOR = 0x006349D4      # #D44963
MAIRON_DWM_BORDER_COLOR = 0x00573134    # #343157


def _pick_font_family(
    root: tk.Tk,
) -> str:
    """
    Prefer the agreed Mairon typefaces when installed, with a native Windows
    fallback so the client remains usable on a clean machine.
    """

    try:
        installed = {
            name.casefold(): name
            for name in tkfont.families(
                root
            )
        }

    except Exception:
        installed = {}

    for candidate in FONT_PREFERENCES:
        value = installed.get(
            candidate.casefold()
        )

        if value:
            return value

    return "Segoe UI"


def _rounded_rectangle(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    radius: int,
    fill: str,
    outline: str,
    width: int = 1,
    tags=None,
):
    """
    Draw a rounded rectangle using native Canvas primitives.
    """

    radius = max(
        1,
        min(
            int(
                radius
            ),
            int(
                (x2 - x1)
                / 2
            ),
            int(
                (y2 - y1)
                / 2
            ),
        ),
    )

    diameter = (
        radius
        * 2
    )

    canvas.create_rectangle(
        x1 + radius,
        y1,
        x2 - radius,
        y2,
        fill=fill,
        outline="",
        tags=tags,
    )

    canvas.create_rectangle(
        x1,
        y1 + radius,
        x2,
        y2 - radius,
        fill=fill,
        outline="",
        tags=tags,
    )

    for left, top, start in (
        (
            x1,
            y1,
            90,
        ),
        (
            x2 - diameter,
            y1,
            0,
        ),
        (
            x2 - diameter,
            y2 - diameter,
            270,
        ),
        (
            x1,
            y2 - diameter,
            180,
        ),
    ):
        canvas.create_arc(
            left,
            top,
            left + diameter,
            top + diameter,
            start=start,
            extent=90,
            style="pieslice",
            fill=fill,
            outline="",
            tags=tags,
        )

    if (
        outline
        and width > 0
    ):
        canvas.create_arc(
            x1,
            y1,
            x1 + diameter,
            y1 + diameter,
            start=90,
            extent=90,
            style="arc",
            outline=outline,
            width=width,
            tags=tags,
        )

        canvas.create_arc(
            x2 - diameter,
            y1,
            x2,
            y1 + diameter,
            start=0,
            extent=90,
            style="arc",
            outline=outline,
            width=width,
            tags=tags,
        )

        canvas.create_arc(
            x2 - diameter,
            y2 - diameter,
            x2,
            y2,
            start=270,
            extent=90,
            style="arc",
            outline=outline,
            width=width,
            tags=tags,
        )

        canvas.create_arc(
            x1,
            y2 - diameter,
            x1 + diameter,
            y2,
            start=180,
            extent=90,
            style="arc",
            outline=outline,
            width=width,
            tags=tags,
        )

        canvas.create_line(
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            fill=outline,
            width=width,
            tags=tags,
        )

        canvas.create_line(
            x1 + radius,
            y2,
            x2 - radius,
            y2,
            fill=outline,
            width=width,
            tags=tags,
        )

        canvas.create_line(
            x1,
            y1 + radius,
            x1,
            y2 - radius,
            fill=outline,
            width=width,
            tags=tags,
        )

        canvas.create_line(
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            fill=outline,
            width=width,
            tags=tags,
        )


class RoundedPanel(
    tk.Canvas
):
    """
    Rounded visual container with a normal Tk Frame mounted inside it.
    """

    def __init__(
        self,
        parent,
        *,
        height: int,
        fill: str,
        outline: str,
        radius: int,
        padding: int = 1,
    ):
        parent_bg = str(
            parent.cget(
                "bg"
            )
        )

        super().__init__(
            parent,
            height=height,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
        )

        self._fill = fill
        self._outline = outline
        self._radius = radius
        self._padding = max(
            0,
            int(
                padding
            ),
        )

        self.inner = tk.Frame(
            self,
            bg=fill,
        )

        self._window = (
            self.create_window(
                0,
                0,
                anchor="nw",
                window=self.inner,
            )
        )

        self.bind(
            "<Configure>",
            self._redraw,
        )

    def _redraw(
        self,
        event,
    ):
        width = max(
            2,
            int(
                event.width
            ),
        )

        height = max(
            2,
            int(
                event.height
            ),
        )

        self.delete(
            "rounded_shape"
        )

        _rounded_rectangle(
            self,
            1,
            1,
            width - 2,
            height - 2,
            radius=self._radius,
            fill=self._fill,
            outline=self._outline,
            width=1,
            tags="rounded_shape",
        )

        self.tag_lower(
            "rounded_shape"
        )

        inset = (
            self._padding
            + 10
        )

        self.coords(
            self._window,
            inset,
            inset,
        )

        self.itemconfigure(
            self._window,
            width=max(
                1,
                width
                - (
                    inset
                    * 2
                ),
            ),
            height=max(
                1,
                height
                - (
                    inset
                    * 2
                ),
            ),
        )


class RoundedIconButton(
    tk.Canvas
):
    """
    Small rounded composer/title action button drawn with Canvas so the
    visible hit target and the visual shape are genuinely rounded.
    """

    def __init__(
        self,
        parent,
        *,
        text: str,
        command=None,
        width: int = 44,
        height: int = 44,
        radius: int = 14,
        bg: str,
        fg: str,
        hover_bg: str,
        border: str,
        font_family: str,
        font_size: int = 13,
        enabled: bool = True,
    ):
        parent_bg = str(
            parent.cget(
                "bg"
            )
        )

        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            cursor=(
                "hand2"
                if enabled
                else "arrow"
            ),
        )

        self._button_text = str(
            text
            or ""
        )

        self._command = command
        self._width = int(
            width
        )
        self._height = int(
            height
        )
        self._radius = int(
            radius
        )

        self._normal_bg = bg
        self._hover_bg = hover_bg
        self._fg = fg
        self._border = border

        self._font = (
            font_family,
            font_size,
            "bold",
        )

        self._enabled = bool(
            enabled
        )

        self.bind(
            "<Enter>",
            self._on_enter,
        )

        self.bind(
            "<Leave>",
            self._on_leave,
        )

        self.bind(
            "<Button-1>",
            self._on_click,
        )

        self._draw(
            self._normal_bg
        )

    def _draw(
        self,
        fill: str,
    ) -> None:
        self.delete(
            "all"
        )

        _rounded_rectangle(
            self,
            1,
            1,
            self._width - 2,
            self._height - 2,
            radius=self._radius,
            fill=fill,
            outline=self._border,
            width=1,
        )

        self.create_text(
            self._width // 2,
            self._height // 2,
            text=self._button_text,
            fill=(
                self._fg
                if self._enabled
                else MAIRON_THEME[
                    "text_muted"
                ]
            ),
            font=self._font,
        )

    def _on_enter(
        self,
        event,
    ) -> None:
        if self._enabled:
            self._draw(
                self._hover_bg
            )

    def _on_leave(
        self,
        event,
    ) -> None:
        self._draw(
            self._normal_bg
        )

    def _on_click(
        self,
        event,
    ) -> None:
        if (
            self._enabled
            and callable(
                self._command
            )
        ):
            self._command()

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        self._enabled = bool(
            enabled
        )

        self.configure(
            cursor=(
                "hand2"
                if self._enabled
                else "arrow"
            ),
        )

        self._draw(
            self._normal_bg
        )

    def set_palette(
        self,
        *,
        bg=None,
        fg=None,
        hover_bg=None,
        border=None,
    ) -> None:
        if bg is not None:
            self._normal_bg = str(
                bg
            )

        if fg is not None:
            self._fg = str(
                fg
            )

        if hover_bg is not None:
            self._hover_bg = str(
                hover_bg
            )

        if border is not None:
            self._border = str(
                border
            )

        self._draw(
            self._normal_bg
        )


class RoundedMessageBubble(
    tk.Canvas
):
    """
    Responsive rounded chat bubble.

    The bubble stores its natural desired width, but clamps itself to the
    currently available chat-row width so long replies cannot disappear under
    the edge of a resized/narrow window.
    """

    def __init__(
        self,
        parent,
        *,
        speaker: str,
        text: str,
        fill: str,
        outline: str,
        speaker_color: str,
        text_color: str,
        font_family: str,
        max_width: int = 650,
        min_width: int = 190,
        radius: int = 18,
    ):
        parent_bg = str(
            parent.cget(
                "bg"
            )
        )

        self._speaker = str(
            speaker
            or ""
        )

        self._message = str(
            text
            or ""
        )

        self._fill = fill
        self._outline = outline
        self._radius = radius
        self._max_width = int(
            max_width
        )
        self._min_width = int(
            min_width
        )

        self._speaker_font = tkfont.Font(
            family=font_family,
            size=9,
            weight="bold",
        )

        self._message_font = tkfont.Font(
            family=font_family,
            size=11,
            weight="normal",
        )

        longest_line = max(
            (
                self._message_font.measure(
                    line
                )
                for line in (
                    self._message.splitlines()
                    or [
                        self._message
                    ]
                )
            ),
            default=0,
        )

        speaker_width = (
            self._speaker_font.measure(
                self._speaker
            )
        )

        content_width = max(
            longest_line,
            speaker_width,
            self._min_width - 34,
        )

        self._desired_width = min(
            self._max_width,
            max(
                self._min_width,
                content_width + 38,
            ),
        )

        super().__init__(
            parent,
            width=self._desired_width,
            height=80,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
        )

        self._bubble_width = (
            self._desired_width
        )

        self.inner = tk.Frame(
            self,
            bg=fill,
        )

        self._window = (
            self.create_window(
                18,
                14,
                anchor="nw",
                window=self.inner,
                width=max(
                    1,
                    self._bubble_width - 36,
                ),
            )
        )

        self.speaker_label = tk.Label(
            self.inner,
            text=self._speaker,
            bg=fill,
            fg=speaker_color,
            anchor="w",
            justify="left",
            font=self._speaker_font,
        )

        self.speaker_label.pack(
            anchor="w",
            fill="x",
        )

        self.message_label = tk.Label(
            self.inner,
            text=self._message,
            bg=fill,
            fg=text_color,
            anchor="w",
            justify="left",
            wraplength=max(
                130,
                self._bubble_width - 36,
            ),
            font=self._message_font,
        )

        self.message_label.pack(
            anchor="w",
            fill="x",
            pady=(
                5,
                0,
            ),
        )

        self.inner.bind(
            "<Configure>",
            self._sync_height,
        )

        self.bind(
            "<Configure>",
            self._redraw,
        )

        self.after_idle(
            self._sync_height
        )

    def fit_to_width(
        self,
        available_width: int,
    ) -> None:
        """
        Clamp the bubble to the live row width and reflow its text.
        """

        available = max(
            220,
            int(
                available_width
            )
            - 16,
        )

        new_width = min(
            self._desired_width,
            available,
        )

        new_width = max(
            min(
                self._min_width,
                available,
            ),
            new_width,
        )

        if new_width == self._bubble_width:
            return

        self._bubble_width = (
            new_width
        )

        self.configure(
            width=new_width
        )

        inner_width = max(
            1,
            new_width - 36,
        )

        self.itemconfigure(
            self._window,
            width=inner_width,
        )

        self.message_label.configure(
            wraplength=max(
                130,
                inner_width,
            ),
        )

        self.after_idle(
            self._sync_height
        )

    def _sync_height(
        self,
        event=None,
    ) -> None:
        self.update_idletasks()

        requested = (
            self.inner.winfo_reqheight()
            + 28
        )

        if int(
            float(
                self.cget(
                    "height"
                )
            )
        ) != requested:
            self.configure(
                height=requested
            )

        self._redraw()

    def _redraw(
        self,
        event=None,
    ) -> None:
        width = max(
            2,
            int(
                self.winfo_width()
                or self._bubble_width
            ),
        )

        height = max(
            2,
            int(
                self.winfo_height()
            ),
        )

        self.delete(
            "bubble_shape"
        )

        _rounded_rectangle(
            self,
            1,
            1,
            width - 2,
            height - 2,
            radius=self._radius,
            fill=self._fill,
            outline=self._outline,
            width=1,
            tags="bubble_shape",
        )

        self.tag_lower(
            "bubble_shape"
        )


class ThemedScrollbar(
    tk.Canvas
):
    """
    Minimal Mairon vertical scrollbar.

    Tk's native Windows scrollbar ignores most dark-theme colour options, so
    this small Canvas control owns its own track/thumb rendering and forwards
    drag position to the conversation Canvas.
    """

    def __init__(
        self,
        parent,
        *,
        command,
        theme: dict,
        width: int = 12,
    ):
        super().__init__(
            parent,
            width=width,
            bg=theme[
                "app_bg"
            ],
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )

        self.command = command
        self.theme = theme
        self._first = 0.0
        self._last = 1.0
        self._drag_offset = 0.0
        self._hovering = False

        self.bind(
            "<Configure>",
            self._redraw,
        )

        self.bind(
            "<Enter>",
            self._on_enter,
        )

        self.bind(
            "<Leave>",
            self._on_leave,
        )

        self.bind(
            "<Button-1>",
            self._on_press,
        )

        self.bind(
            "<B1-Motion>",
            self._on_drag,
        )

    def set(
        self,
        first,
        last,
    ) -> None:
        try:
            self._first = max(
                0.0,
                min(
                    1.0,
                    float(
                        first
                    ),
                ),
            )

            self._last = max(
                self._first,
                min(
                    1.0,
                    float(
                        last
                    ),
                ),
            )

        except Exception:
            self._first = 0.0
            self._last = 1.0

        self._redraw()

    def _geometry(
        self,
    ):
        height = max(
            1,
            int(
                self.winfo_height()
            ),
        )

        width = max(
            1,
            int(
                self.winfo_width()
            ),
        )

        pad_y = 6
        track_height = max(
            1,
            height - (
                pad_y
                * 2
            ),
        )

        visible_fraction = max(
            0.0,
            min(
                1.0,
                self._last
                - self._first,
            ),
        )

        thumb_height = max(
            34,
            int(
                track_height
                * visible_fraction
            ),
        )

        thumb_height = min(
            track_height,
            thumb_height,
        )

        movable = max(
            0,
            track_height
            - thumb_height,
        )

        denominator = max(
            1e-9,
            1.0
            - visible_fraction,
        )

        relative = (
            self._first
            / denominator
            if movable > 0
            else 0.0
        )

        top = (
            pad_y
            + int(
                movable
                * max(
                    0.0,
                    min(
                        1.0,
                        relative
                    ),
                )
            )
        )

        bottom = (
            top
            + thumb_height
        )

        return {
            "width": width,
            "height": height,
            "pad_y": pad_y,
            "track_height": track_height,
            "thumb_height": thumb_height,
            "movable": movable,
            "top": top,
            "bottom": bottom,
            "visible_fraction": visible_fraction,
        }

    def _redraw(
        self,
        event=None,
    ) -> None:
        self.delete(
            "all"
        )

        geo = (
            self._geometry()
        )

        width = geo[
            "width"
        ]

        height = geo[
            "height"
        ]

        track_x = max(
            3,
            width // 2
            - 2,
        )

        self.create_rectangle(
            track_x,
            6,
            track_x + 3,
            max(
                6,
                height - 6,
            ),
            fill=self.theme[
                "surface"
            ],
            outline="",
        )

        # Hide the thumb when the entire conversation already fits.
        if geo[
            "visible_fraction"
        ] >= 0.999:
            return

        fill = (
            self.theme[
                "surface_hover"
            ]
            if self._hovering
            else self.theme[
                "border"
            ]
        )

        _rounded_rectangle(
            self,
            2,
            geo[
                "top"
            ],
            max(
                4,
                width - 2,
            ),
            geo[
                "bottom"
            ],
            radius=5,
            fill=fill,
            outline="",
            width=0,
        )

    def _on_enter(
        self,
        event,
    ) -> None:
        self._hovering = True
        self._redraw()

    def _on_leave(
        self,
        event,
    ) -> None:
        self._hovering = False
        self._redraw()

    def _on_press(
        self,
        event,
    ) -> None:
        geo = (
            self._geometry()
        )

        if geo[
            "visible_fraction"
        ] >= 0.999:
            return

        y = float(
            event.y
        )

        if (
            geo[
                "top"
            ]
            <= y
            <= geo[
                "bottom"
            ]
        ):
            self._drag_offset = (
                y
                - geo[
                    "top"
                ]
            )

        else:
            self._drag_offset = (
                geo[
                    "thumb_height"
                ]
                / 2
            )

            self._move_thumb_to(
                y
            )

    def _on_drag(
        self,
        event,
    ) -> None:
        self._move_thumb_to(
            float(
                event.y
            )
        )

    def _move_thumb_to(
        self,
        y: float,
    ) -> None:
        geo = (
            self._geometry()
        )

        movable = geo[
            "movable"
        ]

        if movable <= 0:
            return

        desired_top = (
            y
            - self._drag_offset
        )

        desired_top = max(
            geo[
                "pad_y"
            ],
            min(
                geo[
                    "pad_y"
                ]
                + movable,
                desired_top,
            ),
        )

        fraction = (
            (
                desired_top
                - geo[
                    "pad_y"
                ]
            )
            / movable
        )

        scroll_fraction = (
            fraction
            * max(
                0.0,
                1.0
                - geo[
                    "visible_fraction"
                ],
            )
        )

        try:
            self.command(
                scroll_fraction
            )

        except Exception:
            pass


class ScrollableChat(
    tk.Frame
):
    """
    Scrollable message surface built from real widgets.

    Mouse-wheel handling is filtered by pointer position rather than relying
    on the bare Canvas to receive events. This means scrolling still works
    while the pointer is over a message bubble or one of its child labels.
    """

    def __init__(
        self,
        parent,
        *,
        theme: dict,
        font_family: str,
    ):
        super().__init__(
            parent,
            bg=theme[
                "app_bg"
            ],
        )

        self.theme = theme
        self.font_family = (
            font_family
        )

        self._stick_to_bottom = True

        self.canvas = tk.Canvas(
            self,
            bg=theme[
                "app_bg"
            ],
            highlightthickness=0,
            bd=0,
            yscrollincrement=32,
        )

        self.canvas.pack(
            side="left",
            fill="both",
            expand=True,
        )

        self.scrollbar = ThemedScrollbar(
            self,
            command=(
                self.canvas.yview_moveto
            ),
            theme=theme,
            width=12,
        )

        self.scrollbar.pack(
            side="right",
            fill="y",
            padx=(
                6,
                0,
            ),
        )

        self.canvas.configure(
            yscrollcommand=(
                self.scrollbar.set
            )
        )

        self.inner = tk.Frame(
            self.canvas,
            bg=theme[
                "app_bg"
            ],
        )

        self._window = (
            self.canvas.create_window(
                0,
                0,
                anchor="nw",
                window=self.inner,
            )
        )

        self.inner.bind(
            "<Configure>",
            self._on_inner_configure,
        )

        self.canvas.bind(
            "<Configure>",
            self._on_canvas_configure,
        )

        # Bind once at the application level, then filter by pointer position.
        # Message bubbles are child widgets, so Canvas-only bindings do not see
        # wheel events while the pointer is over the actual conversation.
        self.bind_all(
            "<MouseWheel>",
            self._on_mousewheel,
            add="+",
        )

    def _on_inner_configure(
        self,
        event=None,
    ) -> None:
        self.canvas.configure(
            scrollregion=(
                self.canvas.bbox(
                    "all"
                )
            ),
        )


    def _on_canvas_configure(
        self,
        event,
    ) -> None:
        self.canvas.itemconfigure(
            self._window,
            width=max(
                1,
                int(
                    event.width
                ),
            ),
        )

    def _pointer_is_over_chat(
        self,
    ) -> bool:
        try:
            x, y = (
                self.winfo_pointerxy()
            )

            widget = (
                self.winfo_containing(
                    x,
                    y,
                )
            )

            while widget is not None:
                if widget is self:
                    return True

                widget = getattr(
                    widget,
                    "master",
                    None,
                )

        except Exception:
            return False

        return False

    def _on_mousewheel(
        self,
        event,
    ) -> None:
        if not self._pointer_is_over_chat():
            return

        delta = int(
            event.delta
            or 0
        )

        if delta == 0:
            return

        steps = int(
            -1
            * (
                delta
                / 120
            )
        )

        if steps == 0:
            steps = (
                -1
                if delta > 0
                else 1
            )

        # Disable sticky follow before moving upward. Previously this flag was
        # updated only after the scroll, which let pending geometry/configure
        # work snap the conversation straight back to the bottom.
        if steps < 0:
            self._stick_to_bottom = False

        self.canvas.yview_scroll(
            steps,
            "units",
        )

        self._update_stick_to_bottom()

    def _update_stick_to_bottom(
        self,
    ) -> None:
        try:
            _, end = (
                self.canvas.yview()
            )

            self._stick_to_bottom = (
                float(
                    end
                )
                >= 0.995
            )

        except Exception:
            self._stick_to_bottom = True

    def scroll_to_bottom(
        self,
    ) -> None:
        self.canvas.update_idletasks()

        self.canvas.yview_moveto(
            1.0
        )

        self._stick_to_bottom = True

    def add_message(
        self,
        *,
        role: str,
        text: str,
    ) -> None:
        role_value = str(
            role
            or ""
        ).strip().lower()

        message = str(
            text
            or ""
        )

        # A newly submitted user message should always become visible.
        # Mairon's answer also stays visible unless Oliver deliberately scrolls
        # upward while it is arriving.
        should_follow_new_message = (
            self._stick_to_bottom
            or role_value == "user"
        )

        row = tk.Frame(
            self.inner,
            bg=self.theme[
                "app_bg"
            ],
        )

        row.pack(
            fill="x",
            padx=8,
            pady=7,
        )

        if role_value == "system":
            label = tk.Label(
                row,
                text=message,
                bg=self.theme[
                    "app_bg"
                ],
                fg=self.theme[
                    "text_muted"
                ],
                justify="left",
                anchor="w",
                wraplength=700,
                font=(
                    self.font_family,
                    9,
                ),
            )

            label.pack(
                anchor="w",
                padx=6,
            )

            if should_follow_new_message:
                self.after_idle(
                    self.scroll_to_bottom
                )

            return

        if role_value == "user":
            bubble = RoundedMessageBubble(
                row,
                speaker="You",
                text=message,
                fill=self.theme[
                    "surface_hover"
                ],
                outline=self.theme[
                    "border"
                ],
                speaker_color=self.theme[
                    "text_secondary"
                ],
                text_color=self.theme[
                    "text_primary"
                ],
                font_family=(
                    self.font_family
                ),
                max_width=610,
                min_width=180,
                radius=18,
            )

            bubble.pack(
                side="right",
                anchor="e",
            )

            row.bind(
                "<Configure>",
                lambda event, item=bubble: (
                    item.fit_to_width(
                        event.width
                    )
                ),
            )

            row.after_idle(
                lambda item=bubble, container=row: (
                    item.fit_to_width(
                        container.winfo_width()
                    )
                )
            )

        else:
            bubble = RoundedMessageBubble(
                row,
                speaker="Mairon",
                text=message,
                fill=self.theme[
                    "surface"
                ],
                outline=self.theme[
                    "border"
                ],
                speaker_color=self.theme[
                    "accent"
                ],
                text_color=self.theme[
                    "text_primary"
                ],
                font_family=(
                    self.font_family
                ),
                max_width=690,
                min_width=210,
                radius=18,
            )

            bubble.pack(
                side="left",
                anchor="w",
            )

            row.bind(
                "<Configure>",
                lambda event, item=bubble: (
                    item.fit_to_width(
                        event.width
                    )
                ),
            )

            row.after_idle(
                lambda item=bubble, container=row: (
                    item.fit_to_width(
                        container.winfo_width()
                    )
                )
            )

        if should_follow_new_message:
            self.after_idle(
                self.scroll_to_bottom
            )


class DesktopAgentProcessManager:
    """
    Reuse an existing Desktop Agent or quietly start one owned by this app.
    """

    def __init__(
        self,
    ):
        self.process = None
        self.started_by_app = False

    def is_available(
        self,
        timeout: float = 0.5,
    ) -> bool:
        result = ping_desktop_agent(
            timeout=timeout,
        )

        return bool(
            isinstance(
                result,
                dict,
            )
            and result.get(
                "success"
            )
            is True
        )

    def ensure_running(
        self,
    ) -> bool:
        if self.is_available():
            return True

        if not AGENT_SCRIPT.is_file():
            return False

        creationflags = (
            CREATE_NO_WINDOW
            if os.name == "nt"
            else 0
        )

        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    str(
                        AGENT_SCRIPT
                    ),
                ],
                cwd=str(
                    PROJECT_ROOT
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )

            self.started_by_app = True

        except Exception:
            self.process = None
            self.started_by_app = False

            return False

        deadline = (
            time.monotonic()
            + 5.0
        )

        while (
            time.monotonic()
            < deadline
        ):
            if self.is_available(
                timeout=0.35
            ):
                return True

            if (
                self.process
                is not None
                and self.process.poll()
                is not None
            ):
                break

            time.sleep(
                0.15
            )

        return False

    def stop_if_owned(
        self,
    ) -> None:
        process = (
            self.process
        )

        if (
            not self.started_by_app
            or process is None
            or process.poll()
            is not None
        ):
            return

        try:
            process.terminate()

            process.wait(
                timeout=2.0
            )

        except Exception:
            try:
                process.kill()

            except Exception:
                pass


class MaironDesktopApp:
    def __init__(
        self,
        root: tk.Tk,
    ):
        self.root = root
        self.theme = dict(
            MAIRON_THEME
        )

        self.font_family = (
            _pick_font_family(
                root
            )
        )

        self.root.title(
            "MAIRON"
        )

        self.root.geometry(
            "1120x760"
        )

        self.root.minsize(
            860,
            600,
        )

        self.root.configure(
            bg=self.theme[
                "app_bg"
            ]
        )

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self._on_close,
        )

        # Phase 10.4.6 deliberately keeps the real native Windows title bar.
        # Windows therefore owns dragging, snapping, minimize/restore animation,
        # taskbar interaction, Alt+Tab, and close behaviour. We only theme the
        # native non-client area to match Mairon's palette.
        self.native_windows_chrome = (
            os.name == "nt"
        )

        self.agent_manager = (
            DesktopAgentProcessManager()
        )

        self.events = queue.Queue()

        self.application = None
        self.busy = False
        self.pending_approval = False
        self.voice_recording = False
        self.speaking = False

        self.voice_runtime = VoiceRuntime(
            event_sink=(
                lambda message: (
                    self.events.put(
                        (
                            "voice_status",
                            message,
                        )
                    )
                )
            )
        )

        self.thinking_visible = False
        self.thinking_step = 0
        self.thinking_after_id = None

        self._build_ui()

        if self.native_windows_chrome:
            self.root.bind(
                "<Map>",
                self._on_window_map,
            )

            self.root.after(
                80,
                self._apply_windows_titlebar_theme,
            )

        self._append_system_message(
            "Starting Mairon..."
        )

        self._set_status(
            "Starting",
            self.theme[
                "warning"
            ],
        )

        threading.Thread(
            target=self._bootstrap,
            daemon=True,
        ).start()

        self.root.after(
            75,
            self._poll_events,
        )

    # --------------------------------------------------
    # UI construction
    # --------------------------------------------------

    def _build_ui(
        self,
    ) -> None:
        self.root.grid_rowconfigure(
            0,
            weight=1,
        )

        self.root.grid_columnconfigure(
            0,
            weight=1,
        )

        self._build_body()

    def _build_body(
        self,
    ) -> None:
        body = tk.Frame(
            self.root,
            bg=self.theme[
                "app_bg"
            ],
        )

        body.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        body.grid_rowconfigure(
            0,
            weight=1,
        )

        body.grid_columnconfigure(
            1,
            weight=1,
        )

        self._build_sidebar(
            body
        )

        self._build_main_area(
            body
        )

    def _build_sidebar(
        self,
        parent,
    ) -> None:
        sidebar = tk.Frame(
            parent,
            bg=self.theme[
                "surface"
            ],
            width=220,
        )

        sidebar.grid(
            row=0,
            column=0,
            sticky="nsw",
        )

        sidebar.grid_propagate(
            False
        )

        heading = tk.Frame(
            sidebar,
            bg=self.theme[
                "surface"
            ],
        )

        heading.pack(
            fill="x",
            padx=18,
            pady=(
                20,
                12,
            ),
        )

        tk.Label(
            heading,
            text="M",
            bg=self.theme[
                "accent"
            ],
            fg=self.theme[
                "text_primary"
            ],
            width=2,
            height=1,
            font=(
                self.font_family,
                13,
                "bold",
            ),
        ).pack(
            side="left",
        )

        brand_text = tk.Frame(
            heading,
            bg=self.theme[
                "surface"
            ],
        )

        brand_text.pack(
            side="left",
            padx=10,
        )

        tk.Label(
            brand_text,
            text="Mairon",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_primary"
            ],
            font=(
                self.font_family,
                13,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        tk.Label(
            brand_text,
            text="Personal AI",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                8,
            ),
        ).pack(
            anchor="w"
        )

        tk.Label(
            sidebar,
            text="WORKSPACE",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            padx=20,
            pady=(
                18,
                6,
            ),
        )

        self._sidebar_item(
            sidebar,
            "◉  Chat",
            selected=True,
        )

        self._sidebar_item(
            sidebar,
            "▣  Files",
            suffix="soon",
        )

        spacer = tk.Frame(
            sidebar,
            bg=self.theme[
                "surface"
            ],
        )

        spacer.pack(
            fill="both",
            expand=True,
        )

        tk.Label(
            sidebar,
            text="SYSTEM",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                9,
                "bold",
            ),
        ).pack(
            anchor="w",
            padx=20,
            pady=(
                0,
                6,
            ),
        )

        self.agent_label = tk.Label(
            sidebar,
            text="●  Desktop Agent: checking",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                9,
            ),
            anchor="w",
        )

        self.agent_label.pack(
            fill="x",
            padx=20,
            pady=4,
        )

        self.model_label = tk.Label(
            sidebar,
            text="Local model: starting",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                9,
            ),
            anchor="w",
            justify="left",
            wraplength=180,
        )

        self.model_label.pack(
            fill="x",
            padx=20,
            pady=(
                4,
                12,
            ),
        )

        self._sidebar_item(
            sidebar,
            "⚙  Themes",
            suffix="future",
        )

        tk.Label(
            sidebar,
            text="v0.1 • Phase 10",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                7,
            ),
        ).pack(
            anchor="w",
            padx=20,
            pady=(
                6,
                18,
            ),
        )

    def _sidebar_item(
        self,
        parent,
        text: str,
        *,
        selected: bool = False,
        suffix: str = "",
    ) -> None:
        bg = (
            self.theme[
                "surface_hover"
            ]
            if selected
            else self.theme[
                "surface"
            ]
        )

        fg = (
            self.theme[
                "accent"
            ]
            if selected
            else self.theme[
                "text_secondary"
            ]
        )

        row = tk.Frame(
            parent,
            bg=bg,
            height=40,
        )

        row.pack(
            fill="x",
            padx=12,
            pady=2,
        )

        row.pack_propagate(
            False
        )

        tk.Label(
            row,
            text=text,
            bg=bg,
            fg=fg,
            font=(
                self.font_family,
                10,
                "bold"
                if selected
                else "normal",
            ),
            anchor="w",
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=12,
        )

        if suffix:
            tk.Label(
                row,
                text=suffix,
                bg=bg,
                fg=self.theme[
                    "text_muted"
                ],
                font=(
                    self.font_family,
                    8,
                ),
            ).pack(
                side="right",
                padx=10,
            )

    def _build_main_area(
        self,
        parent,
    ) -> None:
        main = tk.Frame(
            parent,
            bg=self.theme[
                "app_bg"
            ],
        )

        main.grid(
            row=0,
            column=1,
            sticky="nsew",
        )

        main.grid_rowconfigure(
            1,
            weight=1,
        )

        main.grid_columnconfigure(
            0,
            weight=1,
        )

        header = tk.Frame(
            main,
            bg=self.theme[
                "app_bg"
            ],
        )

        header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=32,
            pady=(
                18,
                8,
            ),
        )

        tk.Label(
            header,
            text="New Chat",
            bg=self.theme[
                "app_bg"
            ],
            fg=self.theme[
                "text_primary"
            ],
            font=(
                self.font_family,
                12,
                "bold",
            ),
        ).pack(
            side="left",
        )

        self.status_dot = tk.Label(
            header,
            text="●",
            bg=self.theme[
                "app_bg"
            ],
            fg=self.theme[
                "warning"
            ],
            font=(
                self.font_family,
                8,
            ),
        )

        self.status_dot.pack(
            side="right",
        )

        self.status_label = tk.Label(
            header,
            text="Starting",
            bg=self.theme[
                "app_bg"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                8,
            ),
        )

        self.status_label.pack(
            side="right",
            padx=(
                0,
                7,
            ),
        )

        self.chat = ScrollableChat(
            main,
            theme=self.theme,
            font_family=(
                self.font_family
            ),
        )

        self.chat.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=30,
            pady=(
                0,
                8,
            ),
        )

        self.thinking_panel = RoundedPanel(
            main,
            height=48,
            fill=self.theme[
                "surface"
            ],
            outline=self.theme[
                "border"
            ],
            radius=CORNER_RADIUS[
                "chip"
            ],
        )

        self.thinking_label = tk.Label(
            self.thinking_panel.inner,
            text="...",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_secondary"
            ],
            font=(
                self.font_family,
                9,
            ),
        )

        self.thinking_label.pack(
            side="left",
            padx=4,
        )

        self.approval_panel = RoundedPanel(
            main,
            height=116,
            fill=self.theme[
                "surface"
            ],
            outline=self.theme[
                "accent"
            ],
            radius=CORNER_RADIUS[
                "panel"
            ],
        )

        approval_inner = (
            self.approval_panel.inner
        )

        approval_inner.grid_columnconfigure(
            0,
            weight=1,
        )

        self.approval_title = tk.Label(
            approval_inner,
            text="Approval required",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_primary"
            ],
            font=(
                self.font_family,
                9,
                "bold",
            ),
            anchor="w",
        )

        self.approval_title.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(
                0,
                3,
            ),
        )

        self.approval_detail = tk.Label(
            approval_inner,
            text="",
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_secondary"
            ],
            font=(
                self.font_family,
                8,
            ),
            justify="left",
            anchor="w",
            wraplength=640,
        )

        self.approval_detail.grid(
            row=1,
            column=0,
            sticky="ew",
        )

        approval_buttons = tk.Frame(
            approval_inner,
            bg=self.theme[
                "surface"
            ],
        )

        approval_buttons.grid(
            row=1,
            column=1,
            rowspan=2,
            padx=(
                12,
                0,
            ),
        )

        self.decline_button = tk.Button(
            approval_buttons,
            text="Decline",
            command=lambda: self._resolve_approval(
                False
            ),
            bg=self.theme[
                "surface_hover"
            ],
            fg=self.theme[
                "text_primary"
            ],
            activebackground=self.theme[
                "border"
            ],
            activeforeground=self.theme[
                "text_primary"
            ],
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            font=(
                self.font_family,
                8,
            ),
        )

        self.decline_button.pack(
            side="left",
            padx=4,
        )

        self.approve_button = tk.Button(
            approval_buttons,
            text="Approve",
            command=lambda: self._resolve_approval(
                True
            ),
            bg=self.theme[
                "accent"
            ],
            fg=self.theme[
                "text_primary"
            ],
            activebackground=self.theme[
                "surface_hover"
            ],
            activeforeground=self.theme[
                "text_primary"
            ],
            relief="flat",
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            font=(
                self.font_family,
                8,
                "bold",
            ),
        )

        self.approve_button.pack(
            side="left",
            padx=4,
        )

        composer_shell = tk.Frame(
            main,
            bg=self.theme[
                "app_bg"
            ],
        )

        composer_shell.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=30,
            pady=(
                6,
                18,
            ),
        )

        composer_shell.grid_columnconfigure(
            0,
            weight=1,
        )

        self.composer = RoundedPanel(
            composer_shell,
            height=92,
            fill=self.theme[
                "surface"
            ],
            outline=self.theme[
                "border"
            ],
            radius=CORNER_RADIUS[
                "composer"
            ],
        )

        self.composer.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        composer = (
            self.composer.inner
        )

        composer.grid_columnconfigure(
            2,
            weight=1,
        )

        self.attach_button = RoundedIconButton(
            composer,
            text="+",
            command=None,
            width=40,
            height=40,
            radius=13,
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_muted"
            ],
            hover_bg=self.theme[
                "surface_hover"
            ],
            border=self.theme[
                "border"
            ],
            font_family=(
                self.font_family
            ),
            font_size=13,
            enabled=False,
        )

        self.attach_button.grid(
            row=0,
            column=0,
            rowspan=2,
            padx=(
                0,
                7,
            ),
        )

        self.voice_button = RoundedIconButton(
            composer,
            text="🎙",
            command=self._toggle_voice,
            width=40,
            height=40,
            radius=13,
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_secondary"
            ],
            hover_bg=self.theme[
                "surface_hover"
            ],
            border=self.theme[
                "border"
            ],
            font_family=(
                self.font_family
            ),
            font_size=11,
            enabled=False,
        )

        self.voice_button.grid(
            row=0,
            column=1,
            rowspan=2,
            padx=(
                0,
                9,
            ),
        )

        self.input = tk.Text(
            composer,
            height=2,
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_primary"
            ],
            insertbackground=self.theme[
                "accent"
            ],
            selectbackground=self.theme[
                "surface_hover"
            ],
            relief="flat",
            bd=0,
            wrap="word",
            undo=True,
            font=(
                self.font_family,
                11,
            ),
        )

        self.input.grid(
            row=0,
            column=2,
            sticky="ew",
            pady=(
                4,
                0,
            ),
        )

        self.input.bind(
            "<Return>",
            self._on_enter,
        )

        self.input.bind(
            "<Shift-Return>",
            self._on_shift_enter,
        )

        self.composer_hint = tk.Label(
            composer,
            text=(
                "Enter to send • Shift+Enter for a new line "
                "• click mic to talk"
            ),
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                7,
            ),
        )

        self.composer_hint.grid(
            row=1,
            column=2,
            sticky="w",
            pady=(
                0,
                2,
            ),
        )

        self.send_button = RoundedIconButton(
            composer,
            text="↑",
            command=self._send,
            width=48,
            height=48,
            radius=16,
            bg=self.theme[
                "accent"
            ],
            fg=self.theme[
                "text_primary"
            ],
            hover_bg=self.theme[
                "surface_hover"
            ],
            border=self.theme[
                "accent"
            ],
            font_family=(
                self.font_family
            ),
            font_size=16,
            enabled=True,
        )

        self.send_button.grid(
            row=0,
            column=3,
            rowspan=2,
            padx=(
                10,
                2,
            ),
        )

        footer = tk.Frame(
            composer_shell,
            bg=self.theme[
                "app_bg"
            ],
        )

        footer.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(
                6,
                0,
            ),
        )

        self.timing_label = tk.Label(
            footer,
            text="",
            bg=self.theme[
                "app_bg"
            ],
            fg=self.theme[
                "text_muted"
            ],
            font=(
                self.font_family,
                7,
            ),
        )

        self.timing_label.pack(
            side="right",
        )

    # --------------------------------------------------
    # Bootstrap
    # --------------------------------------------------

    def _bootstrap(
        self,
    ) -> None:
        agent_ready = (
            self.agent_manager.ensure_running()
        )

        self.events.put(
            (
                "agent_status",
                agent_ready,
            )
        )

        try:
            application = (
                MaironApplication(
                    event_sink=(
                        lambda message: (
                            self.events.put(
                                (
                                    "debug",
                                    message,
                                )
                            )
                        )
                    )
                )
            )

        except Exception as exc:
            self.events.put(
                (
                    "bootstrap_error",
                    str(
                        exc
                    ),
                )
            )

            return

        self.events.put(
            (
                "application_ready",
                application,
            )
        )

    # --------------------------------------------------
    # Sending / approvals
    # --------------------------------------------------

    def _on_enter(
        self,
        event,
    ):
        if (
            event.state
            & 0x0001
        ):
            return None

        self._send()

        return "break"

    def _on_shift_enter(
        self,
        event,
    ):
        return None

    def _send(
        self,
    ) -> None:
        if (
            self.busy
            or self.pending_approval
            or self.application
            is None
        ):
            return

        text = self.input.get(
            "1.0",
            "end-1c",
        ).strip()

        if not text:
            return

        self.input.delete(
            "1.0",
            "end",
        )

        self._append_user_message(
            text
        )

        self._set_busy(
            True
        )

        self._show_thinking()

        threading.Thread(
            target=self._submit_worker,
            args=(
                text,
                "text",
            ),
            daemon=True,
        ).start()

    def _submit_worker(
        self,
        text: str,
        channel: str = "text",
    ) -> None:
        try:
            result = (
                self.application.submit_text(
                    text,
                    channel=channel,
                )
            )

        except Exception as exc:
            result = ApplicationTurn(
                status="error",
                user_text=text,
                answer=str(
                    exc
                ),
            )

        self.events.put(
            (
                "turn_result",
                result,
            )
        )

    def _toggle_voice(
        self,
    ) -> None:
        if (
            self.application is None
            or self.pending_approval
            or self.speaking
        ):
            return

        if self.voice_recording:
            self._stop_voice_recording()
            return

        if self.busy:
            return

        try:
            self.voice_runtime.start_recording()

        except Exception as exc:
            self._append_system_message(
                "Voice input failed: "
                + str(
                    exc
                )
            )

            self._set_status(
                "Voice error",
                self.theme[
                    "danger"
                ],
            )

            return

        self.voice_recording = True
        self.busy = True

        self.send_button.set_enabled(
            False
        )

        self.voice_button.set_enabled(
            True
        )

        self.voice_button.set_palette(
            bg=self.theme[
                "accent"
            ],
            fg=self.theme[
                "text_primary"
            ],
            hover_bg=self.theme[
                "surface_hover"
            ],
            border=self.theme[
                "accent"
            ],
        )

        self.composer_hint.config(
            text="Listening • click mic again to stop"
        )

        self._set_status(
            "Listening",
            self.theme[
                "accent"
            ],
        )

    def _stop_voice_recording(
        self,
    ) -> None:
        try:
            audio = (
                self.voice_runtime
                .stop_recording()
            )

        except Exception as exc:
            self.voice_recording = False
            self.busy = False

            self._restore_voice_button()

            self.send_button.set_enabled(
                True
            )

            self._append_system_message(
                "Voice input failed: "
                + str(
                    exc
                )
            )

            self._set_status(
                "Voice error",
                self.theme[
                    "danger"
                ],
            )

            return

        self.voice_recording = False

        self._restore_voice_button()

        self.voice_button.set_enabled(
            False
        )

        self.composer_hint.config(
            text="Transcribing local microphone audio..."
        )

        self._set_status(
            "Transcribing",
            self.theme[
                "accent"
            ],
        )

        threading.Thread(
            target=self._voice_transcribe_worker,
            args=(
                audio,
            ),
            daemon=True,
        ).start()

    def _restore_voice_button(
        self,
    ) -> None:
        self.voice_button.set_palette(
            bg=self.theme[
                "surface"
            ],
            fg=self.theme[
                "text_secondary"
            ],
            hover_bg=self.theme[
                "surface_hover"
            ],
            border=self.theme[
                "border"
            ],
        )

    def _voice_transcribe_worker(
        self,
        audio,
    ) -> None:
        try:
            transcript = (
                self.voice_runtime
                .transcribe(
                    audio
                )
            )

            self.events.put(
                (
                    "voice_transcript",
                    transcript,
                )
            )

        except Exception as exc:
            self.events.put(
                (
                    "voice_error",
                    str(
                        exc
                    ),
                )
            )

    def _start_speaking(
        self,
        text: str,
    ) -> None:
        self.speaking = True
        self.busy = True

        self.send_button.set_enabled(
            False
        )

        self.voice_button.set_enabled(
            False
        )

        self.composer_hint.config(
            text="Mairon is speaking"
        )

        self._set_status(
            "Speaking",
            self.theme[
                "accent"
            ],
        )

        threading.Thread(
            target=self._speech_worker,
            args=(
                text,
            ),
            daemon=True,
        ).start()

    def _speech_worker(
        self,
        text: str,
    ) -> None:
        error = None

        try:
            self.voice_runtime.speak_response(
                text
            )

        except Exception as exc:
            error = str(
                exc
            )

        self.events.put(
            (
                "speech_done",
                error,
            )
        )

    def _resolve_approval(
        self,
        approved: bool,
    ) -> None:
        if (
            self.busy
            or not self.pending_approval
            or self.application
            is None
        ):
            return

        self.pending_approval = False

        self._hide_approval()

        self._set_busy(
            True
        )

        self._show_thinking()

        threading.Thread(
            target=self._approval_worker,
            args=(
                approved,
            ),
            daemon=True,
        ).start()

    def _approval_worker(
        self,
        approved: bool,
    ) -> None:
        try:
            result = (
                self.application
                .resolve_pending_approval(
                    approved
                )
            )

        except Exception as exc:
            result = ApplicationTurn(
                status="error",
                answer=str(
                    exc
                ),
            )

        self.events.put(
            (
                "turn_result",
                result,
            )
        )

    # --------------------------------------------------
    # Thinking indicator
    # --------------------------------------------------

    def _show_thinking(
        self,
        text: str = "",
    ) -> None:
        """
        Show a deliberately minimal activity indicator.

        The chat already establishes that Mairon is replying; animated dots
        communicate liveness without repeatedly spelling out "Mairon is
        thinking".
        """

        self.thinking_visible = True
        self.thinking_step = 0

        self.thinking_panel.grid(
            row=2,
            column=0,
            sticky="w",
            padx=30,
            pady=(
                0,
                4,
            ),
        )

        self._animate_thinking()

    def _animate_thinking(
        self,
    ) -> None:
        if not self.thinking_visible:
            return

        frames = (
            ".",
            "..",
            "...",
        )

        self.thinking_label.config(
            text=frames[
                self.thinking_step
                % len(
                    frames
                )
            ]
        )

        self.thinking_step += 1

        self.thinking_after_id = (
            self.root.after(
                360,
                self._animate_thinking,
            )
        )

    def _hide_thinking(
        self,
    ) -> None:
        self.thinking_visible = False

        if self.thinking_after_id:
            try:
                self.root.after_cancel(
                    self.thinking_after_id
                )

            except Exception:
                pass

        self.thinking_after_id = None
        self.thinking_panel.grid_forget()

    # --------------------------------------------------
    # Event processing
    # --------------------------------------------------

    def _poll_events(
        self,
    ) -> None:
        try:
            while True:
                event = (
                    self.events.get_nowait()
                )

                self._handle_event(
                    event
                )

        except queue.Empty:
            pass

        self.root.after(
            75,
            self._poll_events,
        )

    def _handle_event(
        self,
        event,
    ) -> None:
        kind = event[
            0
        ]

        payload = (
            event[
                1
            ]
            if len(
                event
            ) > 1
            else None
        )

        if kind == "agent_status":
            if payload:
                self.agent_label.config(
                    text=(
                        "●  Desktop Agent: connected"
                    ),
                    fg=self.theme[
                        "success"
                    ],
                )

            else:
                self.agent_label.config(
                    text=(
                        "●  Desktop Agent: unavailable"
                    ),
                    fg=self.theme[
                        "danger"
                    ],
                )

        elif kind == "application_ready":
            self.application = payload

            status = (
                self.application.session_status()
            )

            cloud_text = (
                "Cloud ready"
                if status[
                    "cloud_available"
                ]
                else "Local only"
            )

            self.model_label.config(
                text=(
                    "Local: "
                    + str(
                        status[
                            "local_model"
                        ]
                    )
                    + "\n"
                    + cloud_text
                ),
            )

            self._append_system_message(
                self._greeting(
                    status[
                        "user_name"
                    ]
                )
            )

            self._append_system_message(
                "Mairon desktop client is ready."
            )

            self._set_status(
                "Ready",
                self.theme[
                    "success"
                ],
            )

            self.voice_button.set_enabled(
                True
            )

            self.input.focus_set()

        elif kind == "bootstrap_error":
            self._hide_thinking()

            self._set_status(
                "Startup failed",
                self.theme[
                    "danger"
                ],
            )

            self._append_system_message(
                "Startup failed: "
                + str(
                    payload
                )
            )

            messagebox.showerror(
                "Mairon startup failed",
                str(
                    payload
                ),
            )

        elif kind == "turn_result":
            self._hide_thinking()

            self._set_busy(
                False
            )

            self._handle_turn_result(
                payload
            )

        elif kind == "voice_transcript":
            transcript = str(
                payload
                or ""
            ).strip()

            if not transcript:
                self.busy = False

                self.send_button.set_enabled(
                    True
                )

                self.voice_button.set_enabled(
                    True
                )

                self.composer_hint.config(
                    text=(
                        "Enter to send • Shift+Enter for a new line "
                        "• click mic to talk"
                    )
                )

                self._set_status(
                    "Ready",
                    self.theme[
                        "success"
                    ],
                )

                self._append_system_message(
                    "No speech recognised."
                )

                return

            self._append_user_message(
                transcript
            )

            self.composer_hint.config(
                text="Voice request sent"
            )

            self._set_status(
                "Thinking",
                self.theme[
                    "accent"
                ],
            )

            self._show_thinking()

            threading.Thread(
                target=self._submit_worker,
                args=(
                    transcript,
                    "voice",
                ),
                daemon=True,
            ).start()

        elif kind == "voice_error":
            self.voice_recording = False
            self.busy = False

            self._restore_voice_button()

            self.send_button.set_enabled(
                True
            )

            self.voice_button.set_enabled(
                True
            )

            self.composer_hint.config(
                text=(
                    "Enter to send • Shift+Enter for a new line "
                    "• click mic to talk"
                )
            )

            self._set_status(
                "Voice error",
                self.theme[
                    "danger"
                ],
            )

            self._append_system_message(
                "Voice input failed: "
                + str(
                    payload
                    or ""
                )
            )

        elif kind == "voice_status":
            status_text = str(
                payload
                or ""
            ).strip()

            if status_text:
                self._set_status(
                    status_text,
                    self.theme[
                        "accent"
                    ],
                )

        elif kind == "speech_done":
            self.speaking = False
            self.busy = False

            self.send_button.set_enabled(
                not self.pending_approval
            )

            self.voice_button.set_enabled(
                not self.pending_approval
            )

            self.composer_hint.config(
                text=(
                    "Enter to send • Shift+Enter for a new line "
                    "• click mic to talk"
                )
            )

            if payload:
                self._append_system_message(
                    "TTS failed: "
                    + str(
                        payload
                    )
                )

                self._set_status(
                    "Voice error",
                    self.theme[
                        "danger"
                    ],
                )

            else:
                self._set_status(
                    "Ready",
                    self.theme[
                        "success"
                    ],
                )

            self.input.focus_set()

        elif kind == "debug":
            text = str(
                payload
                or ""
            )

            if text.startswith(
                "[Core]"
            ):
                self.status_label.config(
                    text=text
                )

    # --------------------------------------------------
    # Result rendering
    # --------------------------------------------------

    def _handle_turn_result(
        self,
        result: ApplicationTurn,
    ) -> None:
        if result.status in {
            "cloud_approval_required",
            "action_approval_required",
        }:
            self.pending_approval = True

            self.send_button.set_enabled(
                False
            )

            self.voice_button.set_enabled(
                False
            )

            self._show_approval(
                title=(
                    result.approval_title
                    or "Approval required"
                ),
                detail=(
                    result.approval_detail
                    or result.reason
                    or ""
                ),
            )

            self._set_status(
                "Waiting for approval",
                self.theme[
                    "warning"
                ],
            )

            return

        if result.answer:
            if result.status == "system":
                self._append_system_message(
                    result.answer
                )

            else:
                self._append_mairon_message(
                    result.answer
                )

        if (
            result.response_seconds
            is not None
        ):
            self.timing_label.config(
                text=(
                    "Response "
                    f"{result.response_seconds:.2f}s"
                )
            )

        if (
            result.channel == "voice"
            and result.answer
            and result.status == "answered"
        ):
            self._start_speaking(
                result.answer
            )

            return

        if result.status == "error":
            self._set_status(
                "Error",
                self.theme[
                    "danger"
                ],
            )

        else:
            self._set_status(
                "Ready",
                self.theme[
                    "success"
                ],
            )

        self.send_button.set_enabled(
            not self.pending_approval
        )

        self.voice_button.set_enabled(
            not self.pending_approval
        )

        self.composer_hint.config(
            text=(
                "Enter to send • Shift+Enter for a new line "
                "• click mic to talk"
            )
        )

        self.input.focus_set()

    # --------------------------------------------------
    # Approval UI
    # --------------------------------------------------

    def _show_approval(
        self,
        *,
        title: str,
        detail: str,
    ) -> None:
        self.approval_title.config(
            text=title
        )

        self.approval_detail.config(
            text=detail
        )

        self.approval_panel.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=30,
            pady=(
                4,
                4,
            ),
        )

    def _hide_approval(
        self,
    ) -> None:
        self.approval_panel.grid_forget()

    # --------------------------------------------------
    # Chat helpers
    # --------------------------------------------------

    def _append_user_message(
        self,
        text: str,
    ) -> None:
        self.chat.add_message(
            role="user",
            text=text,
        )

    def _append_mairon_message(
        self,
        text: str,
    ) -> None:
        self.chat.add_message(
            role="mairon",
            text=text,
        )

    def _append_system_message(
        self,
        text: str,
    ) -> None:
        self.chat.add_message(
            role="system",
            text=text,
        )

    # --------------------------------------------------
    # State / title bar
    # --------------------------------------------------

    def _set_busy(
        self,
        busy: bool,
    ) -> None:
        self.busy = bool(
            busy
        )

        self.send_button.set_enabled(
            not self.busy
            and not self.pending_approval
        )

        self.voice_button.set_enabled(
            (
                self.voice_recording
            )
            or (
                not self.busy
                and not self.pending_approval
                and self.application
                is not None
            )
        )

        if self.busy:
            self._set_status(
                "Thinking",
                self.theme[
                    "accent"
                ],
            )

    def _set_status(
        self,
        text: str,
        color: str,
    ) -> None:
        self.status_label.config(
            text=text
        )

        self.status_dot.config(
            fg=color
        )

    def _windows_top_level_hwnd(
        self,
    ):
        """
        Return the native top-level HWND backing Tk's client widget.
        """

        if os.name != "nt":
            return None

        try:
            self.root.update_idletasks()

            child_hwnd = int(
                self.root.winfo_id()
            )

            parent_hwnd = int(
                ctypes.windll.user32.GetParent(
                    child_hwnd
                )
                or 0
            )

            return (
                parent_hwnd
                or child_hwnd
            )

        except Exception:
            return None

    def _apply_windows_titlebar_theme(
        self,
    ) -> None:
        """
        Theme the real Windows title bar without replacing it.

        Keeping the native non-client area gives Mairon normal Windows drag,
        snapping, minimize/restore transitions, taskbar animation, Alt+Tab,
        and shell behaviour. DWM only changes its colours/corner preference.
        """

        if (
            not self.native_windows_chrome
            or os.name != "nt"
        ):
            return

        hwnd = (
            self._windows_top_level_hwnd()
        )

        if not hwnd:
            return

        try:
            dwmapi = (
                ctypes.windll.dwmapi
            )

            dark_mode = (
                ctypes.c_int(
                    1
                )
            )

            corner_preference = (
                ctypes.c_int(
                    DWMWCP_ROUND
                )
            )

            caption_color = (
                ctypes.c_uint(
                    MAIRON_DWM_CAPTION_COLOR
                )
            )

            text_color = (
                ctypes.c_uint(
                    MAIRON_DWM_TEXT_COLOR
                )
            )

            border_color = (
                ctypes.c_uint(
                    MAIRON_DWM_BORDER_COLOR
                )
            )

            attributes = (
                (
                    DWMWA_USE_IMMERSIVE_DARK_MODE,
                    dark_mode,
                ),
                (
                    DWMWA_WINDOW_CORNER_PREFERENCE,
                    corner_preference,
                ),
                (
                    DWMWA_CAPTION_COLOR,
                    caption_color,
                ),
                (
                    DWMWA_TEXT_COLOR,
                    text_color,
                ),
                (
                    DWMWA_BORDER_COLOR,
                    border_color,
                ),
            )

            for attribute, value in attributes:
                try:
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        attribute,
                        ctypes.byref(
                            value
                        ),
                        ctypes.sizeof(
                            value
                        ),
                    )

                except Exception:
                    # Some attributes require newer Windows builds.
                    continue

        except Exception:
            # Native theming is visual polish only; Mairon must still start.
            return

    def _on_window_map(
        self,
        event,
    ) -> None:
        if not self.native_windows_chrome:
            return

        # Reapply after restore because DWM/Tk may refresh the native frame.
        self.root.after(
            20,
            self._apply_windows_titlebar_theme,
        )

    # --------------------------------------------------
    # Shutdown
    # --------------------------------------------------

    def _on_close(
        self,
    ) -> None:
        self._hide_thinking()

        try:
            self.voice_runtime.cancel_recording()

        except Exception:
            pass

        self.agent_manager.stop_if_owned()

        self.root.destroy()

    @staticmethod
    def _greeting(
        user_name: str,
    ) -> str:
        hour = (
            datetime.now().hour
        )

        if hour < 12:
            period = "morning"

        elif hour < 18:
            period = "afternoon"

        else:
            period = "evening"

        return (
            f"Good {period}, {user_name}."
        )


def main():
    set_windows_app_identity()

    if not ensure_single_instance_or_activate():
        return

    root = tk.Tk()

    root.iconname(
        "Mairon"
    )

    if APP_ICON_PATH.is_file():
        try:
            root.iconbitmap(
                default=str(
                    APP_ICON_PATH
                )
            )

        except Exception:
            pass

    MaironDesktopApp(
        root
    )

    root.mainloop()


if __name__ == "__main__":
    main()
