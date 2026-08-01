"""The output contract.

Two layers:
  1. Pydantic / JSON Schema  — shape. Enforced by the API via structured outputs.
  2. `check()`               — content. Enforced here, against the journal.

Layer 2 is the one that stops generic technical analysis: the model has to name
which rule in the journal produced the conclusion, and the rule has to exist.
"""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from journal import Framework

# Indicators a model trained on the open internet reaches for by default.
# None of these are in the journal, so any mention is knowledge from outside it.
OFF_FRAMEWORK_INDICATORS = [
    "RSI", "MACD", "Stochastic", "Ichimoku", "ADX", "OBV", "CCI",
    "Parabolic SAR", "VWAP", "Williams %R", "ATR", "Keltner",
]

HEDGING_PHRASES = [
    "it depends", "consult", "not financial advice", "do your own research",
    "could go either way", "hard to say", "i cannot", "i'm not able",
    "as an ai", "generally speaking", "typically", "may or may not",
]

MA_MENTION_RE = re.compile(r"\b(EMA|SMA)\s*\(?\s*(\d+)\s*\)?", re.IGNORECASE)


class Analysis(BaseModel):
    """What a correct answer looks like. Anything else does not reach the screen."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    timeframe: Literal["5m", "15m", "1h", "4h", "1D"]
    verdict: Literal["long", "short", "no_trade"]
    confidence: Literal["low", "medium", "high"]
    entry: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    rule_citations: list[str]
    candlestick_signal: Optional[str]
    evidence: list[str]
    reasoning: str


class Violation(Exception):
    """A constraint the response broke, phrased so it can be fed back to the model."""

    def __init__(self, constraint: str, detail: str) -> None:
        super().__init__(f"{constraint}: {detail}")
        self.constraint = constraint
        self.detail = detail


def json_schema() -> dict:
    return Analysis.model_json_schema()


def check(analysis: Analysis, fw: Framework) -> list[Violation]:
    """Every way a schema-valid response can still be wrong."""
    out: list[Violation] = []
    text = f"{analysis.reasoning} {' '.join(analysis.evidence)}"

    # 1. The citation gate. This is the load-bearing one.
    if not analysis.rule_citations:
        out.append(Violation(
            "rule_citations must not be empty",
            "name at least one Master Rule from the journal that produced this conclusion",
        ))
    for cited in analysis.rule_citations:
        if cited not in fw.rules:
            out.append(Violation(
                "rule_citations must reference a rule that exists in the journal",
                f"cited {cited!r}; the journal defines only {sorted(fw.rules)}",
            ))

    # 2. No knowledge from outside the journal.
    for name in OFF_FRAMEWORK_INDICATORS:
        if re.search(rf"\b{re.escape(name)}\b", text, re.IGNORECASE):
            out.append(Violation(
                "only indicators configured in the journal may be used",
                f"mentioned {name!r}, which the journal does not configure",
            ))
    for kind, period in MA_MENTION_RE.findall(text):
        token = f"{kind.upper()} {period}"
        if token not in fw.ma_tokens:
            out.append(Violation(
                "only moving averages configured in the journal may be used",
                f"mentioned {token!r}; the journal configures {sorted(fw.ma_tokens)}",
            ))

    # 3. No hedging, no questions back to the trader.
    lowered = text.lower()
    for phrase in HEDGING_PHRASES:
        if phrase in lowered:
            out.append(Violation(
                "the response must not hedge",
                f"contains {phrase!r}; state the verdict the framework produces",
            ))
    if "?" in analysis.reasoning:
        out.append(Violation(
            "the response must not ask the trader a question",
            "reasoning contains a question mark; decide from the chart and the rules",
        ))

    # 4. MR-4: a directional call is not a trade without all three levels.
    if analysis.verdict in ("long", "short"):
        missing = [
            f for f in ("entry", "stop_loss", "take_profit")
            if getattr(analysis, f) is None
        ]
        if missing:
            out.append(Violation(
                "MR-4 requires entry, stop loss and take profit on every trade",
                f"verdict is {analysis.verdict!r} but {', '.join(missing)} is null",
            ))

    # 5. MR-2: a trade needs a signal from the library, by its exact name.
    if analysis.verdict in ("long", "short"):
        sig = analysis.candlestick_signal
        if sig is None:
            out.append(Violation(
                "MR-2 requires a completed candlestick signal from the library",
                "candlestick_signal is null on a directional call",
            ))
        elif sig not in fw.candlesticks:
            out.append(Violation(
                "candlestick_signal must be a pattern defined in the journal",
                f"got {sig!r}; the library defines {sorted(fw.candlesticks)}",
            ))

    return _dedupe(out)


def _dedupe(violations: list[Violation]) -> list[Violation]:
    """A term mentioned in both reasoning and evidence is still one violation."""
    seen: set[tuple[str, str]] = set()
    out: list[Violation] = []
    for v in violations:
        key = (v.constraint, v.detail)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out
