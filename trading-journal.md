# Trading Journal — Price Action Framework

> This is a **sample** journal used to demonstrate the framework loader.
> Replace it with your own file. No code changes are required — the loader
> parses this structure and the agent is rebuilt from it at startup.

## Master Rules

- **MR-1** — Trade only in the direction of the 200 SMA on the 1h. While price is below it, long setups on every lower timeframe are ignored.
- **MR-2** — On the 1-minute chart only the 9 EMA and the 40 SMA apply. A 1m read that leans on the 20, 100 or 200 SMA is not a valid 1m read.
- **MR-3** — No entry without a completed candlestick signal from the library below. A signal forming on an unclosed candle does not count.
- **MR-4** — Volume on the signal candle must exceed the 20-period volume average. Signals on below-average volume are ignored.
- **MR-5** — Every long or short must state entry, stop loss and take profit. A setup without all three is not a trade.
- **MR-6** — When price sits between the 0.5 and 0.618 Fibonacci retracement of the last impulse, a counter-trend signal is void. Wait for the zone to resolve.

## Moving Averages

Only these apply, and only on the timeframe they are listed under.

- 1m — 9 EMA, 40 SMA
- 5m — 9 EMA, 20 SMA, 40 SMA, 100 SMA, 200 SMA
- 15m — 9 EMA, 20 SMA, 40 SMA, 100 SMA, 200 SMA
- 1h — 9 EMA, 20 SMA, 40 SMA, 100 SMA, 200 SMA

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
