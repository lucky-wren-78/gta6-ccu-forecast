"""gta6-twitch-ccu-forecast-01 entry: a kernel-weighted quantile curve fitted at run time
on the case's own comparables (Python 3.13, standard library only, no network).

Why not persistence: the house baseline holds every hour at hour 1's print. Across the
38-42 past big launches each case carries as `comparables`, a release day's shape is
anything but flat: launches whose unlock rolled through the time zones before 00:00 UTC
peak early and sag, launches with a single global unlock later in the UTC day multiply
tenfold by the evening. This program learns that shape from the comparables of the very
case it is forecasting, per hour, as a distribution of log-ratios to hour 1's print:

    r_c(h) = ln( viewers_c(h) / viewers_c(1) ),      q_tau(h) = p1 * exp( Q_tau( r(h) ) )

with the comparables weighted by how much they resemble this case:

  * a Gaussian kernel on ln(p1) (bandwidth 1.0, floor 0.03): a launch that opened at
    800k viewers evolves like other launches that opened at 800k, not like one that
    opened at 200;
  * a Gaussian kernel on the RMS distance (bandwidth 0.8) between the case's and the
    comparable's mean-centred log-viewer trajectory over the 24 hours before day_start,
    plus ln(p1): two launches whose audiences built the same way into release day tend
    to keep evolving the same way (the factor is 1 when fewer than 8 hours overlap).

Each hour's five quantiles blend the weighted empirical quantiles of r(h) (30%) with a
normal fit through the weighted median and IQR (70%), the spread then scaled by 0.95,
and every quantile column is smoothed over +-1 hour. Validation (leave-one-out over the
37 comparable launches with a full release-day curve, refitting on the rest each time):
mean pinball loss 0.398 against 0.930 for the persistence formula scored identically;
on the six largest early-unlock launches - the Grand Theft Auto VI profile - 0.153
against 0.226. See MODEL.md for the full table.

Deterministic: no randomness, no clock, no environment reads beyond the two directory
variables below, so two runs write the same bytes.

How the grader runs it: `python3 -P -s /bot/main.py` (PYTHONHASHSEED=0) in
python:3.13-slim. Outside the grader's container, MAKEFUN_INPUT_DIR and
MAKEFUN_OUTPUT_DIR stand in for /input and /output:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]

BW_LP1 = 1.0        # kernel bandwidth on ln(hour-1 print)
W_FLOOR = 0.03      # every comparable keeps at least this much weight from the p1 kernel
BW_TRAJ = 0.8       # kernel bandwidth on the trajectory RMS distance
BLEND = 0.3         # weight of the empirical quantile against the normal fit
KAPPA = 0.95        # spread calibration around the median
SIGFLOOR = 0.15     # smallest log-spread an hour may report


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def round2(x):
    """x rounded to 2 decimals, half up, as JavaScript's Math.round(x * 100) / 100 rounds it.

    A whole number comes back as an int, so json.dumps writes 1240 where JavaScript
    writes 1240 (not 1240.0).
    """
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def hourly_map(points, time_key):
    """{timestamp: viewers} from a case's or comparable's hourly points."""
    out = {}
    for p in points or []:
        v = p.get("viewers")
        if v is None:
            continue
        out[parse_time(p[time_key])] = v
    return out


def day_curve(hourly, day_start):
    """The launch's release-day viewers for hours 0..23 (point at day_start + h hours),
    with interior gaps interpolated in log space and a trailing gap carried flat.
    Returns None when hour 0 is missing or fewer than 18 of the 24 hours are present."""
    raw = [hourly.get(day_start + timedelta(hours=h)) for h in range(24)]
    if raw[0] is None or sum(1 for v in raw if v is not None) < 18:
        return None
    logs = [math.log(max(1, v)) if v is not None else None for v in raw]
    last = logs[0]
    for h in range(24):
        if logs[h] is None:
            logs[h] = last
        else:
            last = logs[h]
    # log-linear interpolation between anchors for interior gaps
    anchors = [h for h in range(24) if raw[h] is not None]
    for a, b in zip(anchors, anchors[1:]):
        if b - a > 1:
            for h in range(a + 1, b):
                logs[h] = logs[a] + (logs[b] - logs[a]) * (h - a) / (b - a)
    return [math.exp(x) for x in logs]


def trajectory(hourly, day_start, logp1):
    """Mean-centred log viewers at hours -24..-1 before day_start, plus ln(p1):
    25 slots, None where the source has no point."""
    vals = []
    for k in range(24, 0, -1):
        v = hourly.get(day_start - timedelta(hours=k))
        vals.append(math.log(max(1, v)) if v is not None else None)
    vals.append(logp1)
    present = [v for v in vals if v is not None]
    if not present:
        return [None] * 25
    mean = sum(present) / len(present)
    return [(v - mean) if v is not None else None for v in vals]


def traj_distance(a, b):
    ds = [(x - y) ** 2 for x, y in zip(a, b) if x is not None and y is not None]
    if len(ds) < 8:
        return None
    return math.sqrt(sum(ds) / len(ds))


def wquantile(pairs, tau):
    """Weighted quantile of [(value, weight)], linear interpolation on the sorted values."""
    pairs = sorted(pairs)
    tot = sum(w for _, w in pairs)
    if tot <= 0:
        return pairs[len(pairs) // 2][0]
    acc = 0.0
    for i, (v, w) in enumerate(pairs):
        acc += w
        if acc >= tau * tot:
            if i == 0:
                return v
            pv = pairs[i - 1][0]
            frac = (tau * tot - (acc - w)) / w if w > 0 else 0.0
            return pv + (v - pv) * frac
    return pairs[-1][0]


def comparable_model(comp):
    """A comparable launch reduced to what the forecaster needs, or None if its
    release-day curve is unusable (e.g. a pre-release category's premiere day)."""
    try:
        day_start = parse_time(comp["day_start"])
        hourly = hourly_map(comp.get("hourly"), "from")
        curve = day_curve(hourly, day_start)
        if curve is None:
            return None
        p1 = max(1, curve[0])
        logp1 = math.log(p1)
        return {
            "logp1": logp1,
            "traj": trajectory(hourly, day_start, logp1),
            "r": {h: math.log(curve[h - 1] / p1) for h in range(2, 25)},
        }
    except Exception:
        return None


def case_trajectory(case, day_start, logp1):
    """The case's own pre-release trajectory from history_hourly, falling back to
    hour-bucketed means of the raw history points when no hourly series is given."""
    hourly = hourly_map(case.get("history_hourly"), "from")
    if not hourly and case.get("history"):
        buckets = {}
        for p in case["history"]:
            v = p.get("viewers")
            if v is None:
                continue
            t = parse_time(p["at"]).replace(minute=0, second=0, microsecond=0)
            buckets.setdefault(t, []).append(v)
        hourly = {t: sum(vs) / len(vs) for t, vs in buckets.items()}
    return trajectory(hourly, day_start, logp1)


def forecast_ratios(train, case_logp1, case_traj):
    """{hour: [5 log-quantile offsets from ln(p1)]} fitted on the training comparables."""
    weights = []
    for f in train:
        w = math.exp(-0.5 * ((f["logp1"] - case_logp1) / BW_LP1) ** 2) + W_FLOOR
        d = traj_distance(f["traj"], case_traj)
        if d is not None:
            w *= math.exp(-0.5 * (d / BW_TRAJ) ** 2)
        weights.append(w)
    hours = list(range(2, 25))
    pred = {}
    for h in hours:
        pairs = [(f["r"][h], w) for f, w in zip(train, weights)]
        mu = wquantile(pairs, 0.5)
        q25 = wquantile(pairs, 0.25)
        q75 = wquantile(pairs, 0.75)
        sig = max(SIGFLOOR, (q75 - q25) / 1.349)
        row = []
        for tau, z in zip(LEVELS, Z):
            emp = wquantile(pairs, tau)
            v = BLEND * emp + (1 - BLEND) * (mu + z * sig)
            row.append(mu + KAPPA * (v - mu))
        pred[h] = row
    for ti in range(5):
        for h in hours:
            vals = [pred[h + j][ti] for j in (-1, 0, 1) if (h + j) in pred]
            pred[h][ti] = sum(vals) / len(vals)
    return pred


def persistence(p1, h):
    """The house baseline's row, kept as the fallback if a case carries no usable
    comparable at all: q_tau = p1 * exp(z_tau * 0.15 * sqrt(h - 1))."""
    return [round2(p1 * math.exp(z * 0.15 * math.sqrt(h - 1))) for z in Z]


def forecast_case(case):
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    p1 = max(1, first["viewers"]) if first else 1
    hours = [row["hour"] for row in case["forecast"]]
    day_start = parse_time(case["day_start"])
    train = [m for m in (comparable_model(c) for c in case.get("comparables") or []) if m]
    if not train:
        return {"hours": [{"hour": h, "q": persistence(p1, h)} for h in hours]}
    offsets = forecast_ratios(train, math.log(p1), case_trajectory(case, day_start, math.log(p1)))
    out = []
    for h in hours:
        row = []
        prev = 0.0
        for off in offsets[h]:
            q = p1 * math.exp(off)
            q = min(max(q, 0.01), 1e9)
            q = max(q, prev)  # quantiles never decrease along the row
            row.append(round2(q))
            prev = row[-1]
        out.append({"hour": h, "q": row})
    return {"hours": out}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
