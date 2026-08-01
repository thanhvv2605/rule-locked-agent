"""rule-locked-agent — run the reject-and-regenerate loop.

    python main.py --offline                     # no API key needed
    python main.py --chart chart.png --symbol BTCUSD --timeframe 1h
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import agent
import journal
from agent import Attempt

HERE = Path(__file__).parent

DIM, RED, GREEN, YELLOW, BOLD, OFF = "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[1m", "\033[0m"


# Four canned responses for offline mode. The first three each break a
# different constraint; the fourth is what the framework actually produces.
SCRIPT = [
    # 1. wrong shape — verdict is not in the enum, take_profit is a string
    json.dumps({
        "symbol": "BTCUSD", "timeframe": "1h", "verdict": "buy",
        "confidence": "high", "entry": 61200.0, "stop_loss": 60400.0,
        "take_profit": "around 63k", "rule_citations": ["MR-1"],
        "candlestick_signal": "hammer", "evidence": [], "reasoning": "Uptrend intact.",
    }),
    # 2. right shape, generic technical analysis underneath
    json.dumps({
        "symbol": "BTCUSD", "timeframe": "1h", "verdict": "long",
        "confidence": "high", "entry": 61200.0, "stop_loss": 60400.0,
        "take_profit": 63100.0, "rule_citations": ["MR-1", "MR-7"],
        "candlestick_signal": "morning_star",
        "evidence": ["RSI at 41 is recovering from oversold", "price reclaimed the EMA 100"],
        "reasoning": "MACD is about to cross bullish and RSI has turned up from oversold, "
                     "so the EMA 100 reclaim is likely to hold.",
    }),
    # 3. on-framework, but hedging and handing the decision back
    json.dumps({
        "symbol": "BTCUSD", "timeframe": "1h", "verdict": "long",
        "confidence": "low", "entry": None, "stop_loss": None, "take_profit": None,
        "rule_citations": ["MR-1", "MR-2"], "candlestick_signal": "hammer",
        "evidence": ["price above EMA 200 on 1h", "hammer closed on the 1h"],
        "reasoning": "This could go either way. Price is above the EMA 200 and a hammer "
                     "closed, but volume is unclear — do your own research on the volume "
                     "before sizing. Where would you put the stop?",
    }),
    # 4. what the framework actually produces
    json.dumps({
        "symbol": "BTCUSD", "timeframe": "1h", "verdict": "no_trade",
        "confidence": "high", "entry": None, "stop_loss": None, "take_profit": None,
        "rule_citations": ["MR-3", "MR-6"], "candlestick_signal": None,
        "evidence": [
            "hammer closed on the 1h above EMA 200, satisfying MR-1 and MR-2",
            "signal-candle volume is below VOL-MA(20), which voids it under MR-3",
            "price sits between the 0.5 and 0.618 retracement of the last impulse",
        ],
        "reasoning": "The 1h trend permits longs and a hammer closed, but the signal "
                     "candle prints below the 20-period volume average, so MR-3 voids it. "
                     "Price is also inside the 0.5-0.618 retracement zone, where MR-6 "
                     "requires waiting for resolution. No trade.",
    }),
]


def report(attempt: Attempt) -> None:
    if attempt.accepted:
        print(f"  {GREEN}attempt {attempt.n}: ACCEPTED{OFF} — reached the trader\n")
        return
    print(f"  {RED}attempt {attempt.n}: REJECTED{OFF} — regenerating")
    for v in attempt.violations:
        print(f"    {YELLOW}✗{OFF} {v.constraint}")
        print(f"      {DIM}{v.detail}{OFF}")
    print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--journal", default=HERE / "trading-journal.md", type=Path)
    p.add_argument("--offline", action="store_true", help="replay canned responses, no API key")
    p.add_argument("--chart", type=Path, help="chart image to analyse")
    p.add_argument("--symbol", default="BTCUSD")
    p.add_argument("--timeframe", default="1h")
    args = p.parse_args(argv)

    fw = journal.load(args.journal)
    print(f"\n{BOLD}framework{OFF}  {fw.summary()}")
    print(f"{DIM}the system prompt is rebuilt from this file at startup{OFF}\n")

    if args.offline:
        transport: agent.Transport = agent.ScriptedTransport(SCRIPT)
        print(f"{DIM}offline mode — replaying canned model responses{OFF}\n")
    else:
        transport = agent.AnthropicTransport(chart_path=args.chart)

    request = (
        f"Analyse {args.symbol} on the {args.timeframe} timeframe using the journal. "
        "Return the analysis in the required schema."
    )

    try:
        result = agent.analyse(fw, transport, request, on_attempt=report)
    except RuntimeError as exc:
        print(f"{RED}{exc}{OFF}")
        return 1

    print(f"{BOLD}verdict{OFF}      {result.verdict}  ({result.confidence} confidence)")
    print(f"{BOLD}rules{OFF}        {', '.join(result.rule_citations)}")
    for rid in result.rule_citations:
        print(f"  {DIM}{rid} — {fw.rules[rid]}{OFF}")
    if result.entry is not None:
        print(f"{BOLD}levels{OFF}       entry {result.entry}  stop {result.stop_loss}  target {result.take_profit}")
    print(f"{BOLD}evidence{OFF}")
    for e in result.evidence:
        print(f"  - {e}")
    print(f"{BOLD}reasoning{OFF}    {result.reasoning}")
    print(f"\n{DIM}every rejection above was appended to {agent.AUDIT_LOG.name}{OFF}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
