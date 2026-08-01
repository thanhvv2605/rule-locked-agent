"""Locked system prompt + reject-and-regenerate loop + audit log."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from pydantic import ValidationError

import contract
from contract import Analysis, Violation
from journal import Framework

MODEL = "claude-opus-5"
MAX_ATTEMPTS = 5
AUDIT_LOG = Path(__file__).with_name("audit.log")


# ---------------------------------------------------------------- system prompt

def build_system_prompt(fw: Framework) -> str:
    """Every hard constraint is stated three times: here, in the field
    descriptions of the schema, and again as the last thing the model reads.

    Stating it once is how a rule gets silently overridden.
    """
    rules = "\n".join(f"{rid} — {text}" for rid, text in fw.rules.items())
    mas = "\n".join(f"{tf}: {', '.join(tokens)}" for tf, tokens in fw.moving_averages.items())
    candles = "\n".join(f"{name} — {desc}" for name, desc in fw.candlesticks.items())

    return f"""You analyse price charts using EXACTLY ONE framework: the trading journal below.
It is the trader's own framework, loaded from {fw.path.name} (sha256 {fw.sha256[:12]}).

You have no other knowledge of technical analysis. Indicators, patterns and
heuristics that are not in this journal do not exist for the purposes of this
conversation. If the journal does not cover something, the answer is no_trade.

=== MASTER RULES ===
{rules}

=== MOVING AVERAGES (the only ones configured, per timeframe) ===
{mas}

=== INDICATORS (the only ones configured) ===
{chr(10).join(fw.indicators)}

=== CANDLESTICK LIBRARY (the only signals that count) ===
{candles}

=== HARD CONSTRAINTS ===
1. Every conclusion must cite the Master Rule IDs that produced it, in
   rule_citations. A rule ID that is not listed above is a fabrication.
2. Never mention an indicator or moving average that is not configured above.
3. Never hedge, never disclaim, never ask the trader a question. Decide.
4. A long or short requires entry, stop_loss and take_profit (MR-5) and a
   candlestick_signal named exactly as in the library (MR-3).
5. When the framework does not produce a setup, verdict is no_trade. That is a
   correct answer, not a failure.
"""


REMINDER = """Before you answer, re-read this:
- cite real Master Rule IDs from the journal in rule_citations
- no indicator outside the journal, no hedging, no questions
- long/short requires entry, stop_loss, take_profit and a library signal
"""


# ------------------------------------------------------------------- transports

class Transport(Protocol):
    """Returns the model's raw JSON text for one attempt."""

    def generate(self, system: str, messages: list[dict], schema: dict) -> str: ...


class AnthropicTransport:
    """The real thing: Claude with the framework as a locked system prompt and
    a strict output schema."""

    def __init__(self, chart_path: Path | None = None) -> None:
        import anthropic  # imported lazily so offline mode needs no dependency

        self.client = anthropic.Anthropic()
        self.chart_path = chart_path

    def _with_chart(self, messages: list[dict]) -> list[dict]:
        """Attach the chart image to the first user turn, once."""
        if not self.chart_path:
            return messages
        import base64
        import mimetypes

        media_type = mimetypes.guess_type(self.chart_path.name)[0] or "image/png"
        data = base64.standard_b64encode(self.chart_path.read_bytes()).decode()
        head, *rest = messages
        return [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": media_type, "data": data,
                    }},
                    {"type": "text", "text": head["content"]},
                ],
            },
            *rest,
        ]

    def generate(self, system: str, messages: list[dict], schema: dict) -> str:
        messages = self._with_chart(messages)
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=messages,
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"model declined: {response.stop_details}")
        return next(b.text for b in response.content if b.type == "text")


class ScriptedTransport:
    """Offline demo. Replays canned model responses so the reject loop is
    visible without an API key. Each one breaks a different constraint."""

    def __init__(self, script: list[str]) -> None:
        self.script = list(script)
        self.calls = 0

    def generate(self, system: str, messages: list[dict], schema: dict) -> str:
        payload = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return payload


# ------------------------------------------------------------------------ loop

@dataclass
class Attempt:
    n: int
    raw: str
    violations: list[Violation]

    @property
    def accepted(self) -> bool:
        return not self.violations


def analyse(
    fw: Framework,
    transport: Transport,
    request: str,
    on_attempt: Callable[[Attempt], None] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> Analysis:
    """Ask, validate, and refuse anything that deviates — up to max_attempts."""
    system = build_system_prompt(fw)
    schema = contract.json_schema(fw)
    messages: list[dict] = [{"role": "user", "content": f"{request}\n\n{REMINDER}"}]

    for n in range(1, max_attempts + 1):
        raw = transport.generate(system, messages, schema)

        try:
            analysis = Analysis.model_validate_json(raw)
        except ValidationError as exc:
            violations = [
                Violation(
                    f"schema: {'.'.join(str(p) for p in e['loc']) or '<root>'}",
                    e["msg"],
                )
                for e in exc.errors()
            ]
            analysis = None
        else:
            violations = contract.check(analysis, fw)

        attempt = Attempt(n=n, raw=raw, violations=violations)
        _audit(fw, attempt)
        if on_attempt:
            on_attempt(attempt)

        if attempt.accepted:
            return analysis  # type: ignore[return-value]

        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": _rejection(violations)})

    raise RuntimeError(
        f"rejected {max_attempts} responses without one that satisfies the framework"
    )


def _rejection(violations: list[Violation]) -> str:
    listed = "\n".join(f"- {v.constraint} — {v.detail}" for v in violations)
    return (
        "That response was rejected before it reached the trader. "
        "It violated these constraints:\n"
        f"{listed}\n\n"
        "Produce the analysis again, satisfying every constraint. "
        "Do not apologise or explain the rejection — return the corrected analysis only.\n\n"
        f"{REMINDER}"
    )


def _audit(fw: Framework, attempt: Attempt) -> None:
    """Every rejection, with the constraint it broke. Over a few weeks this log
    shows exactly where the framework itself is ambiguous."""
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "framework_sha256": fw.sha256[:12],
            "attempt": attempt.n,
            "accepted": attempt.accepted,
            "violations": [
                {"constraint": v.constraint, "detail": v.detail} for v in attempt.violations
            ],
            "raw": attempt.raw[:2000],
        }, ensure_ascii=False) + "\n")
