# Model notes — how the forecast is built and how it was validated

## The problem with flat

The house baseline forecasts every hour of release day at hour 1's print, with a
random-walk spread. Scored identically to this entry (below), that formula loses
0.930 in mean pinball on the comparable launches — because a release day's shape is
not flat. Two regimes dominate:

- **Rolling unlock** (most console launches): the game unlocks at local midnight
  zone by zone, so by 00:00 UTC the audience has been building for hours; hour 1 is
  already near the day's peak, the curve sags into the UTC morning, then climbs
  again as the US unlocks and prime time arrives.
- **Single global unlock** (most PC/Steam launches, typically 16:00–18:00 UTC):
  hour 1 is a pre-unlock trickle and the curve multiplies — sometimes a hundredfold
  — into the evening.

Any single fixed curve averages these two into a shape that fits neither. The fix
is to let the case itself say which launches it resembles.

## The model (all fitted at run time, from the case file)

For each comparable launch c with a usable release-day curve, and each hour
h = 2..24, take the log-ratio to its own hour-1 print:

    r_c(h) = ln( viewers_c(h) / viewers_c(1) )

The forecast for the case is q_tau(h) = p1 · exp( Q_tau( r(h) ) ), where Q_tau is a
weighted quantile over the comparables. Weights are a product of two kernels:

1. **Scale kernel** — Gaussian on ln(p1), bandwidth 1.0, floor 0.03. A launch that
   opened at 800k viewers evolves like other launches that opened at 800k, not like
   one that opened at 200. This alone separates most of the two regimes, because
   global-unlock launches open small.
2. **Trajectory kernel** — Gaussian (bandwidth 0.8) on the RMS distance between
   the case's and the comparable's mean-centred log-viewer trajectories over the
   24 hours before day_start, with ln(p1) appended. Launches whose audiences built
   the same way into release day (a rolling-unlock staircase, a flat ambient line,
   a premiere spike decaying) tend to keep evolving the same way. The factor is 1
   when fewer than 8 hours overlap, so sparse histories degrade gracefully.

Per hour, the five quantiles blend the weighted empirical quantiles of r(h) (30%)
with a normal fit through the weighted median and the weighted IQR/1.349 (70%) —
the blend keeps the 5% and 95% quantiles honest when the effectively-weighted
sample is a dozen launches — the spread is then scaled by 0.95 around the median,
and each quantile column is smoothed over ±1 hour.

Details that matter:

- A comparable whose release-day curve lacks hour 1 or has fewer than 18 of the
  day's 24 hours is dropped (in the practice files this removes exactly one: the
  Grand Theft Auto VI category's pre-release premiere day, whose "release day" is
  mostly unsampled). Interior gaps in the remaining curves are interpolated in
  log space.
- The case's trajectory comes from its `history_hourly`; if a case carries only
  raw `history` points, they are bucketed into whole-hour means first.
- If a case carried no usable comparable at all, the program falls back to the
  house persistence formula, so the output is always a valid forecast.
- No randomness, no clock, no network: two runs write the same bytes. One case
  runs in ~0.1 s against the sandbox's 8 s budget.

## Validation — leave-one-out on the comparables themselves

Each of the 37 comparable launches with a full release-day curve was held out
once; the model was refit on the remaining 36 (plus that file's unusable
premiere-day comparable excluded, as at run time) and scored on the held-out
launch's real curve with the contest's own pinball loss on the log scale. The
house persistence formula (the kit's starter) was scored on the same folds.

| Fold set | This model | Persistence (house baseline formula) |
|---|---|---|
| All 37 launches | **0.398** | 0.930 |
| Rolling-unlock regime (17 launches whose day peaks by hour 6) | **0.201** | 0.254 |
| Global-unlock regime (20 launches peaking at hour 11+) | **0.567** | 1.504 |
| The 6 largest rolling-unlock launches (hour-1 print ≥ e^12.5 ≈ 268k — the GTA VI profile) | **0.153** | 0.226 |

For reference, the house baseline's server-measured practice loss is ≈ 0.387 on
the four practice launches (Wolverine, RDR2, Ragnarök, Spider-Man 2 — all
rolling-unlock launches with large hour-1 prints, i.e. the third row's regime,
where this model's leave-one-out loss is 0.201).

What the validation does not promise: the final is one day of one game, and the
house also fields an AI-model forecast made before hour 1 is known. This entry's
structural edge is that it is run at the deadline on the real case — hour 1's
actual print and two days of recorded pre-release history included — and that its
curve is fitted to the 42 launches the final case carries, the four practice
launches among them.
