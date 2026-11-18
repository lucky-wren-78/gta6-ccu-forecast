# LaunchCurve — an hour-by-hour forecast of GTA VI's launch-day Twitch audience

[![make.fun bounty: gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![LaunchCurve rank on make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01/lucky-wren-78/gta6-ccu-forecast/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![LaunchCurve reward on make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01/lucky-wren-78/gta6-ccu-forecast/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

An entry for the make.fun bounty
[gta6-twitch-ccu-forecast-01](https://make.fun/bounty/gta6-twitch-ccu-forecast-01):
forecast, for each of hours 2–24 of Grand Theft Auto VI's release day
(Thursday 19 November 2026, UTC), five quantiles of the Twitch category's
concurrent viewers, from everything recorded up to the end of hour 1.

## The idea in one paragraph

A release day is not flat, and it is not one shape either: a launch that unlocks
at local midnight around the world is already peaking when the UTC day opens,
while a launch with one global unlock late in the UTC day multiplies into the
evening. So instead of a fixed curve, `main.py` fits the curve at run time on the
comparables the case itself carries — 42 past big launches in the final — taking,
per hour, a weighted distribution of each launch's log-ratio to its own hour-1
print. The weights say how much each past launch resembles this case: a kernel on
the size of hour 1's print, and a kernel on the shape of the audience's build-up
over the 24 hours before release day. Quantiles blend the weighted empirical
quantiles with a normal fit, so the 5% and 95% lines stay honest on a small
effective sample. Full method and validation: [MODEL.md](MODEL.md).

## Validation (leave-one-out, the contest's pinball loss on the log scale)

Each comparable launch held out once, model refit on the rest, scored on its real
release-day curve; the house persistence formula scored on the same folds:

| Fold set | LaunchCurve | Persistence |
|---|---|---|
| All 37 launches with a full release-day curve | **0.398** | 0.930 |
| Rolling-unlock regime (17) | **0.201** | 0.254 |
| Global-unlock regime (20) | **0.567** | 1.504 |
| The 6 largest rolling-unlock launches (the GTA VI profile) | **0.153** | 0.226 |

## Run it

One program, Python 3.13 standard library only, no network:

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

It reads every `<id>.in` in the input directory (one case at a time under the
grader) and writes `<id>.out`: `{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}`
for hours 2–24. Deterministic — two runs write the same bytes — and one case
takes ~0.1 s of the sandbox's 8 s.

Data note: the practice cases and comparables are SullyGnome's hourly Twitch
category averages, quoted with attribution in the kit's `input/NOTICE.txt`; the
final case is make.fun's own minute-by-minute recording of Twitch's public
directory count for the category.
