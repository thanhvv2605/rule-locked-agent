# rule-locked-agent

A ~400-line reference implementation of one thing: **stopping Claude from
quietly falling back on generic technical analysis instead of your framework.**

The risk in a build like this is not the chat window. It is the model producing
a fluent, confident answer that came from its training data rather than from
your journal — and looking identical to a correct one. This repo shows the
mechanism that catches that.

```
trading-journal.md ──► parsed into typed sections + hashed
                              │
                              ▼
                       locked system prompt
                              │
                    chart ──► Claude (Anthropic API)
                              │
                              ▼
                    strict JSON schema — validated
                       │                    │
                    ✅ passes            ❌ deviates
                       │                    │
                       ▼                    ▼
                 reaches the trader   rejected, quoted,
                                      regenerated, logged
```

## Run it

**No API key required.** Offline mode replays canned model responses, so the
reject loop is visible immediately. One dependency:

```bash
pip install pydantic
python main.py --offline
```

Against the real API — adds the Anthropic SDK and a key:

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python main.py --chart your-chart.png --symbol BTCUSD --timeframe 1h
```

## What each layer does

| File | Role |
| --- | --- |
| `trading-journal.md` | The framework. Edit this file, restart, it is live. No code changes, ever. |
| `journal.py` | Parses it into typed sections — Master Rules, MA config per timeframe, indicators, candlestick library — and hashes the file. |
| `contract.py` | The output contract. Pydantic model for shape; `check()` for content. |
| `agent.py` | Locked system prompt, the API call, the reject-and-regenerate loop, the audit log. |
| `main.py` | CLI and the canned responses used by `--offline`. |

## The two gates

**Shape** is enforced by the API. The Pydantic model is passed as a strict JSON
schema via structured outputs, so a free-text verdict or a price as a string
never validates.

**Content** is enforced in `contract.check()`, and this is the part that
matters:

- `rule_citations` — the model must name which Master Rules produced the
  conclusion, and each one must exist in the journal. A fabricated `MR-7` is
  caught. This single field is what stops generic TA from creeping in: the
  model cannot cite a rule it invented.
- Only indicators and moving averages configured in the journal may be
  mentioned. `RSI`, `MACD`, an `EMA 100` that is not in your config — all
  rejected.
- No hedging, no disclaimers, no questions handed back to the trader.
- `MR-4`: a long or short without entry, stop and target is not a trade.
- `MR-2`: a directional call needs a candlestick signal named exactly as in
  your library.

A rejected response never reaches the screen. The violated constraint is quoted
back to the model and it regenerates, up to five attempts.

## The audit log

Every rejection is appended to `audit.log` as JSON — the attempt number, the
framework hash, the constraints violated, and the raw payload:

```json
{"ts":"...","framework_sha256":"fa47372e72ff","attempt":2,"accepted":false,
 "violations":[{"constraint":"rule_citations must reference a rule that exists in the journal",
                "detail":"cited 'MR-7'; the journal defines only ['MR-1', ...]"}]}
```

Over a few weeks that log shows exactly where your own framework is ambiguous —
which rules the model keeps misreading, which situations it has no rule for.
That is worth as much as the analysis itself.

## Why constraints are stated three times

In `agent.py`, every hard constraint appears in the system prompt, in the
schema, and again as the last thing the model reads before answering. This is
deliberate. In a structured-output pipeline of mine, a rule stated clearly in
the system prompt was silently overridden by a field description inside the
JSON schema, and the model did the opposite of what it had been told. State it
once and it can be lost; state it in all three places and then refuse anything
that still deviates.

## Scope

This is a demonstration of the constraint mechanism, not a trading product. It
does not execute orders, does not connect to a broker, and is not investment
advice. `trading-journal.md` is a sample — the whole point is that it is
replaced with yours.
