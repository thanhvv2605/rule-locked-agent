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

# Matches both orders a trader might write: "9 EMA" and "EMA 9" / "EMA(9)".
MA_MENTION_RE = re.compile(
    r"\b(?:(\d+)\s*(EMA|SMA)|(EMA|SMA)\s*\(?\s*(\d+)\s*\)?)", re.IGNORECASE
)


def _ma_order(tokens) -> list[str]:
    """EMA before SMA, then by period — "9 EMA, 20 SMA, 40 SMA" reads naturally,
    where a plain sort would give "100 SMA, 20 SMA, 200 SMA"."""
    return sorted(tokens, key=lambda t: (t.split()[1], int(t.split()[0])))


def _ma_tokens_in(text: str) -> set[str]:
    """Normalise every moving-average mention to the journal's "9 EMA" form."""
    found = set()
    for a_period, a_kind, b_kind, b_period in MA_MENTION_RE.findall(text):
        period, kind = (a_period, a_kind) if a_period else (b_period, b_kind)
        found.add(f"{period} {kind.upper()}")
    return found


class Analysis(BaseModel):
    """What a correct answer looks like. Anything else does not reach the screen."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    # Not a Literal: the valid timeframes come from the journal, not from this
    # file. json_schema() injects them as an enum and check() enforces them, so
    # adding a timeframe to the journal needs no code change.
    timeframe: str
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


def json_schema(fw: Framework) -> dict:
    """The strict schema sent to the API, with the journal's timeframes as the
    enum — so the model cannot even name a timeframe the trader has not set up."""
    schema = Analysis.model_json_schema()
    schema["properties"]["timeframe"]["enum"] = list(fw.moving_averages)
    return schema


def check(analysis: Analysis, fw: Framework) -> list[Violation]:
    """Every way a schema-valid response can still be wrong."""
    out: list[Violation] = []
    text = f"{analysis.reasoning} {' '.join(analysis.evidence)}"

    # 0. The timeframe has to be one the journal sets up.
    if analysis.timeframe not in fw.moving_averages:
        out.append(Violation(
            "timeframe must be one the journal configures",
            f"got {analysis.timeframe!r}; the journal covers {list(fw.moving_averages)}",
        ))

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
    for token in sorted(_ma_tokens_in(text)):
        if token not in fw.ma_tokens:
            out.append(Violation(
                "only moving averages configured in the journal may be used",
                f"mentioned {token!r}; the journal configures {_ma_order(fw.ma_tokens)}",
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

    # 4. MR-5: a directional call is not a trade without all three levels.
    if analysis.verdict in ("long", "short"):
        missing = [
            f for f in ("entry", "stop_loss", "take_profit")
            if getattr(analysis, f) is None
        ]
        if missing:
            out.append(Violation(
                "MR-5 requires entry, stop loss and take profit on every trade",
                f"verdict is {analysis.verdict!r} but {', '.join(missing)} is null",
            ))

    # 5. MR-3: a trade needs a signal from the library, by its exact name.
    if analysis.verdict in ("long", "short"):
        sig = analysis.candlestick_signal
        if sig is None:
            out.append(Violation(
                "MR-3 requires a completed candlestick signal from the library",
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
