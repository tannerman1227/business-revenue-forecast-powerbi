"""Fit a seasonal Holt-Winters forecast and a 12-month holdout backtest.

Model selection uses three earlier 12-month origins and never scores the final
holdout until the specification is frozen. Sector forecasts are then scaled so
each month sums to an independently fitted total forecast.

    python scripts/forecast_model.py
"""

from __future__ import annotations

import json
import sys
import warnings
from hashlib import sha256

import numpy as np
import pandas as pd
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from retail_lib import (
    DATA_DIR,
    DETAIL_KEYS,
    FORECAST_DECIMALS,
    FORWARD_MONTHS,
    HOLDOUT_MONTHS,
    VALIDATION_YEARS,
    build_headline,
    coverage,
    error_metrics,
    load_sales_panel,
    round_amount,
    round_rate,
    sector_by_key,
    write_json,
)

SIMULATIONS = 2000
INTERVAL = 0.80
CANDIDATE_YEARS = (None, 20, 15, 12, 10, 8)
CANDIDATE_SEASONALS = ("mul", "add")
CANDIDATE_DAMPED = (False, True)
MASTER_SEED = 42


def window_start(origin: pd.Timestamp, years: int | None) -> pd.Timestamp | None:
    if years is None:
        return None
    return pd.Timestamp(origin) - pd.DateOffset(years=int(years))


def window_label(years: int | None) -> str:
    return "full history" if years is None else f"{years}-year"


def rng_for(purpose: str, key: str) -> np.random.Generator:
    digest = sha256(f"{MASTER_SEED}|{purpose}|{key}".encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "little")
    return np.random.default_rng(seed)


def fit_hw(series: pd.Series, seasonal: str, damped: bool):
    model = ExponentialSmoothing(
        series.astype(float),
        trend="add",
        damped_trend=damped,
        seasonal=seasonal,
        seasonal_periods=12,
        initialization_method="estimated",
    )
    attempts = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        attempts.append(model.fit(optimized=True, use_brute=True))
        converged = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
    if not converged:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            attempts.append(model.fit(optimized=True, use_brute=False, method="L-BFGS-B"))
        attempts.sort(key=lambda result: float(result.sse))
        return attempts[0], False
    return attempts[0], True


def forecast_series(series: pd.Series, origin: pd.Timestamp, years: int | None, seasonal: str, damped: bool, steps: int):
    train_end = pd.Timestamp(origin) - pd.DateOffset(months=1)
    start = window_start(origin, years)
    train = series.loc[:train_end]
    if start is not None:
        train = train.loc[start:]
    if len(train) < 36:
        raise RuntimeError("Training window is shorter than 36 months")
    result, converged = fit_hw(train, seasonal, damped)
    point = result.forecast(steps)
    point.index = pd.DatetimeIndex(point.index).to_period("M").to_timestamp()
    if not np.isfinite(point.to_numpy()).all() or (point <= 0).any():
        raise RuntimeError("Forecast was not strictly positive")
    return result, point, converged


def simulate_band(result, steps: int, purpose: str, key: str) -> tuple[pd.Series, pd.Series]:
    sims = result.simulate(
        nsimulations=steps,
        repetitions=SIMULATIONS,
        error="add",
        random_errors="bootstrap",
        rng=rng_for(purpose, key),
    )
    values = np.asarray(sims, dtype=float)
    values = np.clip(values, 0, None)
    lower_q = (1 - INTERVAL) / 2
    upper_q = 1 - lower_q
    lower = np.quantile(values, lower_q, axis=1)
    upper = np.quantile(values, upper_q, axis=1)
    index = pd.DatetimeIndex(sims.index).to_period("M").to_timestamp()
    return pd.Series(lower, index=index), pd.Series(upper, index=index)


def allocate_rounding(sector_frame: pd.DataFrame, total: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    rounded = sector_frame.round(FORECAST_DECIMALS)
    total_rounded = total.round(FORECAST_DECIMALS)
    residual = (total_rounded - rounded.sum(axis=1)).round(FORECAST_DECIMALS)
    for stamp, gap in residual.items():
        if gap == 0:
            continue
        column = sector_frame.loc[stamp].idxmax()
        rounded.loc[stamp, column] = round(float(rounded.loc[stamp, column]) + float(gap), FORECAST_DECIMALS)
    return rounded, total_rounded


def scale_bounds(bounds: pd.DataFrame, factor: pd.Series, point: pd.DataFrame, side: str) -> pd.DataFrame:
    scaled = bounds.mul(factor, axis=0).clip(lower=0)
    array = scaled.to_numpy(dtype=float)
    target = point.to_numpy(dtype=float)
    if side == "lower":
        array = np.minimum(array, target)
    else:
        array = np.maximum(array, target)
    return pd.DataFrame(array, index=point.index, columns=point.columns).round(FORECAST_DECIMALS)


def score_total(panel: pd.DataFrame, origin: pd.Timestamp, years, seasonal, damped) -> float:
    _, point, _ = forecast_series(panel.sum(axis=1), origin, years, seasonal, damped, HOLDOUT_MONTHS)
    actual = panel.sum(axis=1).loc[point.index]
    return float(np.mean(np.abs(point.to_numpy() - actual.to_numpy()) / actual.to_numpy()))


def candidate_fits_sectors(panel: pd.DataFrame, origins: list[pd.Timestamp], years, seasonal, damped) -> bool:
    for origin in origins:
        for key in DETAIL_KEYS:
            try:
                forecast_series(panel[key], origin, years, seasonal, damped, HOLDOUT_MONTHS)
            except Exception:
                return False
    return True


def select_model(panel: pd.DataFrame, holdout_start: pd.Timestamp) -> dict:
    origins = [holdout_start - pd.DateOffset(years=year) for year in VALIDATION_YEARS]
    scored = []
    for years in CANDIDATE_YEARS:
        for seasonal in CANDIDATE_SEASONALS:
            for damped in CANDIDATE_DAMPED:
                name = f"{window_label(years)} {seasonal} {'damped' if damped else 'undamped'}"
                try:
                    mapes = [score_total(panel, origin, years, seasonal, damped) for origin in origins]
                except Exception as exc:
                    print(f"  skip {name}: {exc}")
                    continue
                mean_mape = float(np.mean(mapes))
                scored.append(
                    {
                        "name": name,
                        "years": years,
                        "seasonal": seasonal,
                        "damped_trend": damped,
                        "validation_total_mape": round_rate(mean_mape),
                        "validation_origins": [
                            {
                                "origin": origin.strftime("%Y-%m-%d"),
                                "mape": round_rate(value),
                            }
                            for origin, value in zip(origins, mapes)
                        ],
                    }
                )
                print(f"  {name:28} validation MAPE {mean_mape * 100:6.3f}%")
    if not scored:
        raise RuntimeError("No forecast specification could be fit")
    scored.sort(
        key=lambda row: (
            row["validation_total_mape"],
            0 if row["years"] is None else 1,
            0 if row["years"] is None else -int(row["years"]),
            int(row["damped_trend"]),
            0 if row["seasonal"] == "mul" else 1,
        )
    )
    for candidate in scored:
        label = candidate["name"]
        print(f"Checking sector fits for {label}...")
        if candidate_fits_sectors(panel, origins, candidate["years"], candidate["seasonal"], candidate["damped_trend"]):
            candidate["validation_origins_policy"] = [origin.strftime("%Y-%m-%d") for origin in origins]
            candidate["candidates_scored"] = len(scored)
            return candidate
        print(f"  {label} did not fit every sector")
    raise RuntimeError("No specification fit every sector on the validation origins")


def project_origin(panel: pd.DataFrame, origin: pd.Timestamp, spec: dict, purpose: str):
    years = spec["years"]
    seasonal = spec["seasonal"]
    damped = spec["damped_trend"]
    total_series = panel.sum(axis=1)
    total_fit, total_point, total_converged = forecast_series(
        total_series, origin, years, seasonal, damped, HOLDOUT_MONTHS
    )
    total_lower, total_upper = simulate_band(total_fit, HOLDOUT_MONTHS, purpose, "TOTAL")
    sector_points = {}
    sector_lower = {}
    sector_upper = {}
    converged = {"TOTAL": total_converged}
    for key in DETAIL_KEYS:
        fit, point, flag = forecast_series(panel[key], origin, years, seasonal, damped, HOLDOUT_MONTHS)
        lower, upper = simulate_band(fit, HOLDOUT_MONTHS, purpose, key)
        sector_points[key] = point
        sector_lower[key] = lower
        sector_upper[key] = upper
        converged[key] = flag
    points = pd.DataFrame(sector_points).loc[total_point.index, DETAIL_KEYS]
    lowers = pd.DataFrame(sector_lower).loc[total_point.index, DETAIL_KEYS]
    uppers = pd.DataFrame(sector_upper).loc[total_point.index, DETAIL_KEYS]
    raw_sum = points.sum(axis=1)
    factor = total_point / raw_sum
    if not np.isfinite(factor.to_numpy()).all() or (factor <= 0).any():
        raise RuntimeError("Reconciliation factor was not strictly positive")
    reconciled = points.mul(factor, axis=0)
    rounded, total_rounded = allocate_rounding(reconciled, total_point)
    lower_scaled = scale_bounds(lowers, factor, rounded, "lower")
    upper_scaled = scale_bounds(uppers, factor, rounded, "upper")
    total_index = total_rounded.index
    total_lower = pd.Series(
        np.minimum(total_lower.loc[total_index].to_numpy(dtype=float), total_rounded.to_numpy(dtype=float)),
        index=total_index,
    ).round(FORECAST_DECIMALS)
    total_upper = pd.Series(
        np.maximum(total_upper.loc[total_index].to_numpy(dtype=float), total_rounded.to_numpy(dtype=float)),
        index=total_index,
    ).round(FORECAST_DECIMALS)
    return {
        "sectors": rounded,
        "sector_lower": lower_scaled.round(FORECAST_DECIMALS),
        "sector_upper": upper_scaled.round(FORECAST_DECIMALS),
        "factor": factor,
        "total": total_rounded,
        "total_lower": total_lower,
        "total_upper": total_upper,
        "converged": converged,
    }


def model_name(spec: dict) -> str:
    damp = "damped" if spec["damped_trend"] else "undamped"
    return (
        f"Holt-Winters additive {damp} trend, {spec['seasonal']} seasonality, "
        f"{spec['window_label']} window, reconciled to the total forecast"
    )


def frame_records(projection, spec: dict, actual: pd.DataFrame | None, naive: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    name = model_name(spec)
    sector_rows = []
    total_rows = []
    dates = list(projection["total"].index)
    for horizon, stamp in enumerate(dates, start=1):
        total_row = {
            "Date": stamp.strftime("%Y-%m-%d"),
            "Horizon": horizon,
            "ForecastNSA": round_amount(projection["total"].loc[stamp]),
            "Lower80": round_amount(projection["total_lower"].loc[stamp]),
            "Upper80": round_amount(projection["total_upper"].loc[stamp]),
            "Model": name,
        }
        if actual is not None:
            actual_value = float(actual.sum(axis=1).loc[stamp])
            naive_value = float(naive.sum(axis=1).loc[stamp])
            forecast_value = total_row["ForecastNSA"]
            total_row.update(
                {
                    "ActualNSA": round_amount(actual_value, 0) if float(actual_value).is_integer() else round_amount(actual_value),
                    "SeasonalNaiveNSA": round_amount(naive_value, 0),
                    "Error": round_amount(forecast_value - actual_value),
                    "AbsError": round_amount(abs(forecast_value - actual_value)),
                    "AbsPctError": round_rate(abs(forecast_value - actual_value) / actual_value),
                }
            )
            total_row["ActualNSA"] = int(round(actual_value))
            total_row["SeasonalNaiveNSA"] = int(round(naive_value))
        total_rows.append(total_row)
        for key in DETAIL_KEYS:
            row = {
                "Date": stamp.strftime("%Y-%m-%d"),
                "SectorKey": key,
                "Horizon": horizon,
                "ForecastNSA": round_amount(projection["sectors"].at[stamp, key]),
                "Lower80": round_amount(projection["sector_lower"].at[stamp, key]),
                "Upper80": round_amount(projection["sector_upper"].at[stamp, key]),
                "ReconcileFactor": round_rate(float(projection["factor"].loc[stamp])),
                "Model": name,
            }
            if actual is not None:
                actual_value = float(actual.at[stamp, key])
                naive_value = float(naive.at[stamp, key])
                forecast_value = row["ForecastNSA"]
                row.update(
                    {
                        "ActualNSA": int(round(actual_value)),
                        "SeasonalNaiveNSA": int(round(naive_value)),
                        "Error": round_amount(forecast_value - actual_value),
                        "AbsError": round_amount(abs(forecast_value - actual_value)),
                        "AbsPctError": round_rate(abs(forecast_value - actual_value) / actual_value),
                    }
                )
            sector_rows.append(row)
    return pd.DataFrame(sector_rows), pd.DataFrame(total_rows)


def metrics_for(sector_backtest: pd.DataFrame, total_backtest: pd.DataFrame, forward_total: pd.DataFrame, panel: pd.DataFrame) -> dict:
    names = sector_by_key()
    total_metrics = error_metrics(
        total_backtest["ActualNSA"],
        total_backtest["ForecastNSA"],
        total_backtest["SeasonalNaiveNSA"],
    )
    total_metrics["interval_80_coverage"] = coverage(
        total_backtest["ActualNSA"], total_backtest["Lower80"], total_backtest["Upper80"]
    )
    last_actual = panel.index.max()
    prior_start = last_actual - pd.DateOffset(months=11)
    prior_12 = float(panel.loc[prior_start:last_actual].sum().sum())
    forward_sum = float(forward_total["ForecastNSA"].sum())
    total_metrics["prior_12_actual_millions"] = round_amount(prior_12)
    total_metrics["forward_forecast_millions"] = round_amount(forward_sum)
    total_metrics["forward_vs_prior"] = round_rate(forward_sum / prior_12 - 1)
    sectors = []
    for key in DETAIL_KEYS:
        rows = sector_backtest[sector_backtest["SectorKey"] == key]
        item = error_metrics(rows["ActualNSA"], rows["ForecastNSA"], rows["SeasonalNaiveNSA"])
        item["interval_80_coverage"] = coverage(rows["ActualNSA"], rows["Lower80"], rows["Upper80"])
        item["sector_key"] = key
        item["sector_short"] = names[key]["sector_short"]
        item["sector_name"] = names[key]["sector_name"]
        sectors.append(item)
    return {"total": total_metrics, "sectors": sectors}


def main() -> None:
    panel = load_sales_panel("SalesNSA")
    last = panel.index.max()
    holdout_start = last - pd.DateOffset(months=HOLDOUT_MONTHS - 1)
    forward_start = last + pd.DateOffset(months=1)
    print(f"History {panel.index.min().date()} to {last.date()}")
    print(f"Final holdout {holdout_start.date()} to {last.date()} is sealed during selection")
    spec = select_model(panel, holdout_start)
    spec["window_label"] = window_label(spec["years"])
    print(f"Selected {spec['name']} on validation MAPE {spec['validation_total_mape'] * 100:.2f}%")

    print("Fitting the sealed holdout...")
    holdout = project_origin(panel, holdout_start, spec, "holdout")
    actual = panel.loc[holdout["total"].index]
    naive = panel.shift(12).loc[holdout["total"].index]
    print("Fitting the forward forecast...")
    forward = project_origin(panel, forward_start, spec, "forward")

    sector_backtest, total_backtest = frame_records(holdout, spec, actual, naive)
    sector_forecast, total_forecast = frame_records(forward, spec, None, None)
    metric_body = metrics_for(sector_backtest, total_backtest, total_forecast, panel)

    gap = (sector_forecast.groupby("Date")["ForecastNSA"].sum() - total_forecast.set_index("Date")["ForecastNSA"]).abs().max()
    back_gap = (
        sector_backtest.groupby("Date")["ForecastNSA"].sum() - total_backtest.set_index("Date")["ForecastNSA"]
    ).abs().max()
    if gap > 0.001 or back_gap > 0.001:
        raise RuntimeError(f"Reconciled forecasts do not sum to the total (forward {gap}, holdout {back_gap})")

    converged_flags = {**{f"holdout_{k}": v for k, v in holdout["converged"].items()}, **{f"forward_{k}": v for k, v in forward["converged"].items()}}
    payload = {
        "model": {
            "name": model_name(spec),
            "family": "Holt-Winters",
            "trend": "add",
            "damped_trend": spec["damped_trend"],
            "seasonal": spec["seasonal"],
            "seasonal_periods": 12,
            "initialization_method": "estimated",
            "window_years": spec["years"],
            "window_label": spec["window_label"],
            "selection_rule": (
                "Lowest mean total MAPE across three 12-month validation origins "
                "ending the month before the sealed holdout. The specification must "
                "fit every sector on those origins. Ties prefer a longer window, "
                "then an undamped trend, then multiplicative seasonality."
            ),
            "validation_total_mape": spec["validation_total_mape"],
            "validation_origins": spec["validation_origins"],
            "candidates_scored": spec["candidates_scored"],
            "reconciliation": (
                "Each sector is forecast on its own, then multiplied by a common "
                "monthly factor so the sectors sum to the total model's forecast."
            ),
            "interval": (
                f"{int(INTERVAL * 100)} percent central band from {SIMULATIONS} "
                "bootstrap simulations of the fitted Holt-Winters model. Sector "
                "bands are scaled by the same reconciliation factor as the point forecast."
            ),
            "interval_level": INTERVAL,
            "simulations": SIMULATIONS,
            "random_seed": MASTER_SEED,
            "holdout_months": HOLDOUT_MONTHS,
            "history_start": panel.index.min().strftime("%Y-%m-%d"),
            "train_end": (holdout_start - pd.DateOffset(months=1)).strftime("%Y-%m-%d"),
            "holdout_start": holdout_start.strftime("%Y-%m-%d"),
            "holdout_end": last.strftime("%Y-%m-%d"),
            "forecast_start": forward_start.strftime("%Y-%m-%d"),
            "forecast_end": forward["total"].index.max().strftime("%Y-%m-%d"),
            "optimizer_converged": converged_flags,
            "mean_abs_reconcile_gap": round_rate(float((holdout["factor"] - 1).abs().mean())),
        },
        "total": metric_body["total"],
        "sectors": metric_body["sectors"],
    }
    sources = json.loads((DATA_DIR / "data_sources.json").read_text(encoding="utf-8"))
    headline = build_headline(sources, payload)
    headline["retrieved_at"] = sources["retrieved_at"]

    sector_forecast.to_csv(DATA_DIR / "fact_forecast.csv", index=False)
    total_forecast.to_csv(DATA_DIR / "forecast_total.csv", index=False)
    sector_backtest.to_csv(DATA_DIR / "fact_backtest.csv", index=False)
    total_backtest.to_csv(DATA_DIR / "backtest_total.csv", index=False)
    write_json(DATA_DIR / "forecast_metrics.json", payload)
    write_json(DATA_DIR / "kpi_snapshot.json", headline)
    print(
        f"Holdout MAPE {payload['total']['mape'] * 100:.2f}%  "
        f"seasonal naive {payload['total']['seasonal_naive_mape'] * 100:.2f}%  "
        f"80% coverage {payload['total']['interval_80_coverage'] * 100:.1f}%"
    )
    print(
        f"Forward 12 months {payload['total']['forward_forecast_millions']:,.2f} million "
        f"vs prior 12 {payload['total']['forward_vs_prior'] * 100:+.2f}%"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
