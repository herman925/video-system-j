from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List

from nicegui import ui


FileResolver = Callable[[], List[Path]]


@dataclass
class _SaveStateBinding:
    badge: ui.label
    detail: ui.label


@dataclass
class _SaveStateChannel:
    key: str
    resolver: FileResolver | None = None
    bindings: list[_SaveStateBinding] = field(default_factory=list)
    status: str = "idle"
    last_saved_at: datetime | None = None
    error_text: str = ""


_CHANNELS: dict[str, _SaveStateChannel] = {}


def _get_channel(key: str) -> _SaveStateChannel:
    channel = _CHANNELS.get(key)
    if channel is None:
        channel = _SaveStateChannel(key=key)
        _CHANNELS[key] = channel
    return channel


def register_save_state(key: str, resolver: FileResolver | None = None) -> None:
    channel = _get_channel(key)
    if resolver is not None:
        channel.resolver = resolver
    refresh_save_state(key)


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "No saved state yet"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _render_channel(channel: _SaveStateChannel) -> None:
    if channel.status == "saving":
        badge_text = "SAVING"
        badge_style = (
            "background:rgba(250,204,21,0.18);color:#fde68a;"
            "border:1px solid rgba(250,204,21,0.28);"
        )
        detail_text = (
            f"Writing... Last saved {_format_timestamp(channel.last_saved_at)}"
            if channel.last_saved_at
            else "Writing..."
        )
    elif channel.status == "error":
        badge_text = "ERROR"
        badge_style = (
            "background:rgba(248,113,113,0.18);color:#fecaca;"
            "border:1px solid rgba(248,113,113,0.30);"
        )
        detail_text = channel.error_text or "Save failed"
    elif channel.status == "saved" or channel.last_saved_at is not None:
        badge_text = "SAVED"
        badge_style = (
            "background:rgba(52,211,153,0.16);color:#d1fae5;"
            "border:1px solid rgba(52,211,153,0.30);"
        )
        detail_text = f"Last write {_format_timestamp(channel.last_saved_at)}"
    else:
        badge_text = "IDLE"
        badge_style = (
            "background:rgba(148,163,184,0.16);color:#e5e7eb;"
            "border:1px solid rgba(148,163,184,0.24);"
        )
        detail_text = "No saved state yet"

    for binding in channel.bindings:
        binding.badge.set_text(badge_text)
        binding.badge.style(
            "font-size:0.63rem;font-weight:800;letter-spacing:0.08em;"
            "padding:3px 8px;border-radius:999px;min-width:58px;text-align:center;"
            + badge_style
        )
        binding.detail.set_text(detail_text)


def refresh_save_state(key: str) -> None:
    channel = _get_channel(key)
    if channel.resolver is not None:
        try:
            paths = [path for path in channel.resolver() if path.exists()]
        except Exception:
            paths = []
        if paths:
            latest_path = max(paths, key=lambda path: path.stat().st_mtime)
            channel.last_saved_at = datetime.fromtimestamp(latest_path.stat().st_mtime)
    _render_channel(channel)


def mark_save_state_saving(key: str) -> None:
    channel = _get_channel(key)
    channel.status = "saving"
    channel.error_text = ""
    _render_channel(channel)


def mark_save_state_saved(key: str) -> None:
    channel = _get_channel(key)
    channel.status = "saved"
    channel.error_text = ""
    channel.last_saved_at = datetime.now()
    refresh_save_state(key)


def mark_save_state_error(key: str, error: Exception) -> None:
    channel = _get_channel(key)
    channel.status = "error"
    channel.error_text = str(error) or error.__class__.__name__
    _render_channel(channel)


@contextmanager
def tracked_save_state(key: str):
    mark_save_state_saving(key)
    try:
        yield
    except Exception as error:
        mark_save_state_error(key, error)
        raise
    else:
        mark_save_state_saved(key)


def build_save_state_badge(key: str, resolver: FileResolver | None = None) -> ui.row:
    register_save_state(key, resolver)
    channel = _get_channel(key)

    with ui.row().classes("items-center gap-2 no-wrap") as row:
        badge = ui.label("")
        detail = ui.label("").style(
            "font-size:0.76rem;color:#cbd5e1;opacity:0.92;white-space:nowrap;"
        )

    channel.bindings.append(_SaveStateBinding(badge=badge, detail=detail))
    _render_channel(channel)
    return row