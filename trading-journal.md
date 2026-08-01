# Trading Journal — Price Action Framework

> This is a **sample** journal used to demonstrate the framework loader.
> Replace it with your own file. No code changes are required — the loader
> parses this structure and the agent is rebuilt from it at startup.

## Master Rules

- **MR-1** — Trade only in the direction of the 1H trend. If price is below the 1H EMA 200, long setups are ignored entirely.
- **MR-2** — No entry without a completed candlestick signal from the library below. A signal forming on an unclosed candle does not count.
- **MR-3** — Volume on the signal candle must exceed the 20-period volume average. Signals on below-average volume are ignored.
- **MR-4** — Every long or short must state entry, stop loss and take profit. A setup without all three is not a trade.
- **MR-5** — Stop loss goes beyond the structural swing that produced the signal, never at a round number and never inside the Bollinger band.
- **MR-6** — When price sits between the 0.5 and 0.618 Fibonacci retracement of the last impulse, a counter-trend signal is void. Wait for the zone to resolve.

## Moving Averages

| Timeframe | Fast | Slow |
| --- | --- | --- |
| 5m | EMA 9 | EMA 21 |
| 1h | EMA 50 | EMA 200 |
| 1D | SMA 50 | SMA 200 |

## Indicators

- BB(20, 2.0)
- VOL-MA(20)
- FIB(0.382, 0.5, 0.618, 0.786)

## Candlestick Library

- bullish_engulfing — body fully engulfs the previous red body, close above previous open
- bearish_engulfing — body fully engulfs the previous green body, close below previous open
- hammer — lower wick at least twice the body, closing in the upper third of the range
- shooting_star — upper wick at least twice the body, closing in the lower third of the range
- inside_bar — full range contained within the previous candle's range
