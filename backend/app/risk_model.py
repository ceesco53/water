"""
Predicted bacteria risk: the chance a sample drawn today would meet or exceed
NC's swim standard (104 MPN enterococcus), from recent rain, Trent River flow
and time of year.

Fit by calibration/fit_model.py on NC DEQ's 1998-2026 samples at Union Point
and NW Creek, which writes the coefficients and the warning policy to
data/bacteria_risk_model.json. River Bend has no numeric sampling history, so
it's predicted as Union Point, the nearest sampled site. `features` is shared
with the training script so the inputs are transformed identically in both.
"""
import functools
import json
import math
from datetime import date
from pathlib import Path

_MODEL_FILE = Path(__file__).resolve().parent / "data" / "bacteria_risk_model.json"

# What each model input is built from, for "unavailable" notes
_SOURCE = {"rain_0_3d": "72h rain", "rain_3_7d": "7-day rain", "flow": "river flow"}


def features(
    rain_72h_in: float | None,
    rain_7d_in: float | None,
    flow_ratio: float | None,
    day_of_year: int,
    union_point: float = 1.0,
) -> dict[str, float | None]:
    """Model inputs, transformed exactly as in training. None = unknown."""
    angle = 2 * math.pi * day_of_year / 365.25
    return {
        "rain_0_3d": math.log1p(rain_72h_in) if rain_72h_in is not None else None,
        "rain_3_7d": (
            math.log1p(max(rain_7d_in - rain_72h_in, 0.0))
            if rain_72h_in is not None and rain_7d_in is not None
            else None
        ),
        "flow": math.log(max(flow_ratio, 0.01)) if flow_ratio is not None else None,
        "season_sin": math.sin(angle),
        "season_cos": math.cos(angle),
        "union_point": union_point,
    }


@functools.cache
def load_model() -> dict:
    return json.loads(_MODEL_FILE.read_text())


def predict(
    rain_72h_in: float | None,
    rain_7d_in: float | None,
    flow_ratio: float | None,
    day: date,
    storm_rain_72h_in: float | None = None,
) -> dict:
    """
    Chance of exceeding at Union Point, plus whether the warning policy's
    summer-storm floor applies. An unknown input is held at its training
    average (contributes nothing) and listed in missing_inputs, so a dead
    gauge reads as "can't tell" rather than as "no rain".

    storm_rain_72h_in: another 72h rain reading (radar at HOME) for the
    summer-storm floor only. The floor uses the wetter of it and
    rain_72h_in, so a storm the airport gauge missed still counts; the model
    itself keeps the gauge it was trained on.
    """
    model = load_model()
    x = features(rain_72h_in, rain_7d_in, flow_ratio, day.timetuple().tm_yday)

    eta = model["intercept"]
    missing: list[str] = []
    for feature, mean, scale, coef in zip(
        model["features"], model["scaler_mean"], model["scaler_scale"], model["coef"]
    ):
        value = x[feature["name"]]
        if value is None:
            source = _SOURCE.get(feature["name"], feature["name"])
            if source not in missing:
                missing.append(source)
            continue
        eta += coef * (value - mean) / scale

    if model["model"] == "logistic":
        probability = 1 / (1 + math.exp(-eta))
    else:  # tobit: eta is the expected log10(MPN), with normal residuals
        z = (math.log10(model["exceedance_mpn"]) - eta) / model["sigma"]
        probability = 0.5 * math.erfc(z / math.sqrt(2))

    policy = model["policy"]
    floor = policy["summer_floor"]
    storm_rain = max((r for r in (rain_72h_in, storm_rain_72h_in) if r is not None), default=None)
    return {
        "probability": probability,
        "caution_probability": policy["caution_probability"],
        "summer_storm": (
            day.month in floor["months"]
            and storm_rain is not None
            and storm_rain >= floor["rain_72h_in"]
        ),
        "summer_floor_rain_in": floor["rain_72h_in"],
        "rain_72h_in": storm_rain,
        "missing_inputs": missing,
        "trained": model["trained"],
        "validation": model["validation"],
    }
