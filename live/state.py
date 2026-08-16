"""Persist live slot state across restarts."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LiveSlot:
    symbol: str
    side: int  # +1 long / -1 short
    entry: float
    qty: float
    notional: float
    margin: float
    sl: float
    tp: float
    trail_atr: float
    peak: float
    risk: float
    boost: float
    trail_unlocked: bool = False
    scale_n: int = 0
    entry_bar_ms: int = 0
    bars_held: int = 0


@dataclass
class LiveState:
    size_mult: float = 1.0
    last_bar_ms: dict[str, int] = field(default_factory=dict)
    slots: dict[str, LiveSlot] = field(default_factory=dict)
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "size_mult": self.size_mult,
            "last_bar_ms": self.last_bar_ms,
            "slots": {k: asdict(v) for k, v in self.slots.items()},
            "pending": self.pending,
        }

    @classmethod
    def from_json(cls, data: dict) -> "LiveState":
        slots = {k: LiveSlot(**v) for k, v in (data.get("slots") or {}).items()}
        return cls(
            size_mult=float(data.get("size_mult", 1.0)),
            last_bar_ms={k: int(v) for k, v in (data.get("last_bar_ms") or {}).items()},
            slots=slots,
            pending=dict(data.get("pending") or {}),
        )


def load_state(path: Path) -> LiveState:
    if not path.exists():
        return LiveState()
    return LiveState.from_json(json.loads(path.read_text(encoding="utf-8")))


def save_state(path: Path, state: LiveState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state.to_json(), indent=2), encoding="utf-8")
    tmp.replace(path)
