"""Parse trading-journal.md into typed sections and hash it.

Edit the markdown file, restart, the framework is live. No code changes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

RULE_RE = re.compile(r"^-\s+\*\*(MR-\d+)\*\*\s+[—-]\s+(.+)$")
MA_LINE_RE = re.compile(r"^-\s+([0-9A-Za-z]+)\s+[—-]\s+(.+)$")
MA_TOKEN_RE = re.compile(r"(\d+)\s*(EMA|SMA)", re.IGNORECASE)
INDICATOR_RE = re.compile(r"^-\s+([A-Z][A-Z0-9-]*)\(")
CANDLE_RE = re.compile(r"^-\s+([a-z_]+)\s+[—-]\s+(.+)$")


@dataclass(frozen=True)
class Framework:
    path: Path
    sha256: str
    raw: str
    rules: dict[str, str] = field(default_factory=dict)
    moving_averages: dict[str, list[str]] = field(default_factory=dict)
    indicators: list[str] = field(default_factory=list)
    candlesticks: dict[str, str] = field(default_factory=dict)

    @property
    def ma_tokens(self) -> set[str]:
        """Every moving average the journal configures, e.g. {"9 EMA", "40 SMA", ...}."""
        return {token for tokens in self.moving_averages.values() for token in tokens}

    def summary(self) -> str:
        """What was parsed out of the file, for the startup banner."""
        return (
            f"{len(self.rules)} master rules · "
            f"{len(self.moving_averages)} MA timeframes · "
            f"{len(self.indicators)} indicators · "
            f"{len(self.candlesticks)} candlestick patterns"
        )


def load(path: str | Path) -> Framework:
    path = Path(path)
    raw = path.read_text(encoding="utf-8")

    rules: dict[str, str] = {}
    moving_averages: dict[str, list[str]] = {}
    indicators: list[str] = []
    candlesticks: dict[str, str] = {}

    section = ""
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip().lower()
            continue

        if section == "master rules":
            if m := RULE_RE.match(stripped):
                rules[m.group(1)] = m.group(2).strip()
        elif section == "moving averages":
            if m := MA_LINE_RE.match(stripped):
                timeframe, listed = m.groups()
                tokens = [
                    f"{period} {kind.upper()}"
                    for period, kind in MA_TOKEN_RE.findall(listed)
                ]
                if tokens:
                    moving_averages[timeframe] = tokens
        elif section == "indicators":
            if m := INDICATOR_RE.match(stripped):
                indicators.append(stripped[2:].strip())
        elif section == "candlestick library":
            if m := CANDLE_RE.match(stripped):
                candlesticks[m.group(1)] = m.group(2).strip()

    if not rules:
        raise ValueError(f"{path}: no Master Rules found — check the '## Master Rules' section")

    return Framework(
        path=path,
        sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        raw=raw,
        rules=rules,
        moving_averages=moving_averages,
        indicators=indicators,
        candlesticks=candlesticks,
    )
