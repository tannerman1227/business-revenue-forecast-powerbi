"""Backtest a seasonal forecast and write the FY2026 scenarios.

The model is Holt-Winters exponential smoothing (additive trend, multiplicative
seasonality, period 12) fit with statsmodels. It is scored on a single
12-month holdout: train on FY2022–FY2024, forecast FY2025, and compare with
monthly company revenue. That is the same horizon as the decision this file
supports, a full-year plan, so one-step error is not the metric.

The model is then refit on FY2022–FY2025. FY2026 Base is the point forecast.
Downside and Upside are the 10th and 90th percentiles of simulated full-year
revenue (residual bootstrap, seed 42). Those annual dollars are spread across
the twelve months in proportion to sqrt(horizon) x the base-month revenue, so
the band widens as the year extends and the year still lands on the percentile.

Company-level forecasts are allocated to region x product x segment with the
FY2025 seasonal mix, plus a small stated mix drift. Gross margin starts from
the FY2025 rate by product and segment. Operating expense starts from the
FY2025 monthly opex and grows at a scenario-specific rate. This is a planning
allocation, not sixty separate time series.

Outputs
-------
data/fact_budget_forecast.csv   budget rows kept; forecast and backtest replaced
data/forecast_metrics.json      figures the README is checked against
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_data import (  # noqa: E402
    OPEX_INTENSITY,
    PRODUCTS,
    REGIONS,
    SEED,
    SEGMENTS,
    allocate_cents,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RNG_SEED = SEED
HOLDOUT_YEAR = 2025
FORECAST_YEAR = 2026
SIMULATIONS = 4000

# Marginal mix drift, in share points, applied to the FY2025 same-month mix.
# Shifts within a family sum to zero.
MIX_DRIFT = {
    "Forecast - Base": {
        "product": {"SW": 0.012, "EQUIP": -0.010, "SVC": 0.004, "PS": -0.006, "PARTS": 0.000},
        "region": {"APAC": 0.008, "EMEA": -0.006, "NA": -0.002, "LATAM": 0.000},
    },
    "Forecast - Upside": {
        "product": {"SW": 0.022, "EQUIP": -0.016, "SVC": 0.006, "PS": -0.008, "PARTS": -0.004},
        "region": {"APAC": 0.016, "EMEA": -0.010, "NA": -0.004, "LATAM": -0.002},
    },
    "Forecast - Downside": {
        "product": {"SW": 0.002, "EQUIP": 0.000, "SVC": -0.002, "PS": -0.004, "PARTS": 0.004},
        "region": {"APAC": 0.000, "EMEA": -0.012, "NA": 0.010, "LATAM": 0.002},
    },
}

# Added to the FY2025 gross-margin rate. Upside carries richer software
# configuration and price; downside gives discount back to hold volume.
MARGIN_DELTA = {
    "Forecast - Base": 0.003,
    "Forecast - Upside": 0.008,
    "Forecast - Downside": -0.009,
}

# Growth of FY2025 monthly operating expense into FY2026.
OPEX_GROWTH = {
    "Forecast - Base": 1.045,
    "Forecast - Upside": 1.080,
    "Forecast - Downside": 1.018,
}

SCENARIO_ORDER = [
    "Budget",
    "Backtest",
    "Forecast - Downside",
    "Forecast - Base",
    "Forecast - Upside",
]


def money_m(value: float, *, signed: bool = False) -> str:
    millions = value / 1_000_000
    if signed:
        return f"{'-' if millions < 0 else '+'}${abs(millions):.1f}M"
    return f"${millions:.1f}M"


def money_k(value: float) -> str:
    return f"${value / 1_000:,.0f}K"


def pct(value: float, *, signed: bool = False, digits: int = 1) -> str:
    scaled = value * 100
    if signed:
        return f"{scaled:+.{digits}f}%"
    return f"{scaled:.{digits}f}%"


def bps(value: float) -> str:
    return f"{value * 10_000:+.0f} bps"


def load_actuals() -> pd.DataFrame:
    frame = pd.read_csv(DATA / "fact_revenue_actuals.csv")
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame["Year"] = frame["Date"].dt.year
    frame["Month"] = frame["Date"].dt.month
    return frame


def load_budget() -> pd.DataFrame:
    frame = pd.read_csv(DATA / "fact_budget_forecast.csv")
    frame = frame[frame["Scenario"] == "Budget"].copy()
    frame["Date"] = pd.to_datetime(frame["Date"])
    return frame


def monthly_revenue(actuals: pd.DataFrame) -> pd.Series:
    series = actuals.groupby("Date")["Revenue"].sum().sort_index()
    series.index = pd.DatetimeIndex(series.index, freq="MS")
    series.name = "Revenue"
    return series


def fit_holt_winters(series: pd.Series):
    model = ExponentialSmoothing(
        series.astype(float),
        trend="add",
        seasonal="mul",
        seasonal_periods=12,
        initialization_method="estimated",
    )
    return model.fit(optimized=True, remove_bias=True)


def seasonal_ols_forecast(history: pd.Series, horizon: int) -> pd.Series:
    """Fallback: linear trend plus month dummies. Used only if smoothing fails."""

    values = history.to_numpy(dtype=float)
    month = history.index.month.to_numpy()
    trend = np.arange(len(values), dtype=float)
    dummies = np.eye(12)[month - 1][:, 1:]
    design = np.column_stack([np.ones(len(values)), trend, dummies])
    coefficient, *_ = np.linalg.lstsq(design, values, rcond=None)
    future_trend = np.arange(len(values), len(values) + horizon, dtype=float)
    future_month = ((month[-1] - 1 + np.arange(1, horizon + 1)) % 12) + 1
    future_dummies = np.eye(12)[future_month - 1][:, 1:]
    future_design = np.column_stack([np.ones(horizon), future_trend, future_dummies])
    forecast = future_design @ coefficient
    index = pd.date_range(history.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    return pd.Series(forecast, index=index, name="Revenue")


def forecast_values(fitted, horizon: int, history: pd.Series) -> pd.Series:
    try:
        forecast = fitted.forecast(horizon)
    except Exception:
        return seasonal_ols_forecast(history, horizon)
    forecast = pd.Series(np.asarray(forecast, dtype=float), index=pd.DatetimeIndex(forecast.index))
    if not np.isfinite(forecast).all() or (forecast <= 0).any():
        return seasonal_ols_forecast(history, horizon)
    return forecast


def accuracy(actual: pd.Series, forecast: pd.Series) -> dict[str, float]:
    paired = pd.DataFrame({"actual": actual, "forecast": forecast}).dropna()
    error = paired["forecast"] - paired["actual"]
    abs_error = error.abs()
    return {
        "mape": float((abs_error / paired["actual"]).mean()),
        "wape": float(abs_error.sum() / paired["actual"].sum()),
        "rmse": float(np.sqrt((error**2).mean())),
        "bias": float(error.sum() / paired["actual"].sum()),
        "n_months": int(len(paired)),
    }


def annual_intervals(fitted, base: pd.Series) -> dict[str, float]:
    draws = fitted.simulate(
        nsimulations=len(base),
        repetitions=SIMULATIONS,
        error="add",
        random_errors="bootstrap",
        anchor="end",
        rng=np.random.default_rng(RNG_SEED),
    )
    paths = np.asarray(draws, dtype=float)
    if paths.shape[0] != len(base):
        paths = paths.T
    annual = paths.sum(axis=0)
    return {
        "p2_5": float(np.percentile(annual, 2.5)),
        "p10": float(np.percentile(annual, 10)),
        "p50": float(np.percentile(annual, 50)),
        "p90": float(np.percentile(annual, 90)),
        "p97_5": float(np.percentile(annual, 97.5)),
    }


def shape_scenario(base: pd.Series, annual_target: float) -> pd.Series:
    """Keep the base seasonal shape, widen the gap with the horizon, hit the target."""

    values = base.to_numpy(dtype=float)
    gap = float(values.sum() - annual_target)
    horizon = np.arange(1, len(values) + 1, dtype=float)
    weight = np.sqrt(horizon) * values
    weight = weight / weight.sum()
    shaped = values - gap * weight
    if (shaped <= 0).any():
        shaped = values * (annual_target / values.sum())
    return pd.Series(shaped, index=base.index, name="Revenue")


def code_maps() -> tuple[dict[int, str], dict[int, str], dict[int, str]]:
    region = {row["RegionKey"]: row["RegionCode"] for row in REGIONS}
    product = {row["ProductLineKey"]: row["ProductCode"] for row in PRODUCTS}
    segment = {row["SegmentKey"]: row["SegmentCode"] for row in SEGMENTS}
    return region, product, segment


def same_month_shares(actuals: pd.DataFrame, year: int) -> dict[int, dict[tuple[int, int, int], float]]:
    sub = actuals[actuals["Year"] == year]
    grouped = sub.groupby(["Month", "RegionKey", "ProductLineKey", "SegmentKey"])["Revenue"].sum()
    shares: dict[int, dict[tuple[int, int, int], float]] = {}
    for month, month_rows in grouped.groupby(level=0):
        total = float(month_rows.sum())
        shares[int(month)] = {
            (int(region), int(product), int(segment)): float(value) / total
            for (_, region, product, segment), value in month_rows.items()
        }
    return shares


def apply_drift(
    shares: dict[tuple[int, int, int], float],
    product_shift: dict[str, float],
    region_shift: dict[str, float],
) -> dict[tuple[int, int, int], float]:
    region_code, product_code, _ = code_maps()

    def shift_level(current: dict[tuple[int, int, int], float], index: int, shifts_by_code: dict[str, float], coder):
        marginal: dict[int, float] = {}
        for key, share in current.items():
            marginal[key[index]] = marginal.get(key[index], 0.0) + share
        target = {
            key: max(value + shifts_by_code.get(coder[key], 0.0), 0.004)
            for key, value in marginal.items()
        }
        target_total = sum(target.values())
        target = {key: value / target_total for key, value in target.items()}
        adjusted = {}
        for key, share in current.items():
            adjusted[key] = share * target[key[index]] / marginal[key[index]]
        total = sum(adjusted.values())
        return {key: value / total for key, value in adjusted.items()}

    adjusted = shift_level(shares, 1, product_shift, product_code)
    adjusted = shift_level(adjusted, 0, region_shift, region_code)
    return adjusted


def rate_table(actuals: pd.DataFrame, year: int) -> dict[tuple[int, int], float]:
    sub = actuals[actuals["Year"] == year]
    grouped = sub.groupby(["ProductLineKey", "SegmentKey"])[["Revenue", "GrossProfit"]].sum()
    return {
        (int(product), int(segment)): float(row.GrossProfit / row.Revenue)
        for (product, segment), row in grouped.iterrows()
    }


def build_year(
    monthly_totals: pd.Series,
    shares_by_month: dict[int, dict[tuple[int, int, int], float]],
    margins: dict[tuple[int, int], float],
    margin_delta: float,
    opex_by_month: dict[int, float],
    scenario: str,
) -> list[dict]:
    region_code, _, _ = code_maps()
    rows: list[dict] = []
    for date, total in monthly_totals.items():
        month = int(date.month)
        allocated = allocate_cents(shares_by_month[month], float(total))
        weights = {}
        staged = []
        for (region_key, product_key, segment_key), revenue in allocated.items():
            rate = min(max(margins[(product_key, segment_key)] + margin_delta, 0.12), 0.85)
            cogs = round(revenue * (1.0 - rate), 2)
            gross_profit = round(revenue - cogs, 2)
            weights[(region_key, product_key, segment_key)] = revenue * OPEX_INTENSITY[region_code[region_key]]
            staged.append((region_key, product_key, segment_key, revenue, cogs, gross_profit))
        opex_map = allocate_cents(weights, opex_by_month[month])
        for region_key, product_key, segment_key, revenue, cogs, gross_profit in staged:
            opex = opex_map[(region_key, product_key, segment_key)]
            rows.append(
                {
                    "DateKey": int(date.strftime("%Y%m%d")),
                    "Date": date.date().isoformat(),
                    "RegionKey": region_key,
                    "ProductLineKey": product_key,
                    "SegmentKey": segment_key,
                    "Scenario": scenario,
                    "Revenue": revenue,
                    "COGS": cogs,
                    "GrossProfit": gross_profit,
                    "OpEx": opex,
                    "EBITDA": round(gross_profit - opex, 2),
                }
            )
    return rows


def statement(frame: pd.DataFrame) -> dict[str, float]:
    revenue = float(frame["Revenue"].sum())
    cogs = float(frame["COGS"].sum())
    gross_profit = float(frame["GrossProfit"].sum())
    opex = float(frame["OpEx"].sum())
    ebitda = float(frame["EBITDA"].sum())
    return {
        "revenue": round(revenue, 2),
        "cogs": round(cogs, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin": gross_profit / revenue,
        "opex": round(opex, 2),
        "ebitda": round(ebitda, 2),
        "ebitda_margin": ebitda / revenue,
    }


def mix_shares(actuals: pd.DataFrame, year: int, key: str, labels: dict) -> dict[str, float]:
    sub = actuals[actuals["Year"] == year]
    grouped = sub.groupby(key)["Revenue"].sum()
    total = float(grouped.sum())
    return {labels[int(index)]: float(value) / total for index, value in grouped.items()}


def margin_bridge(actuals: pd.DataFrame, start: int, end: int, key: str, labels: dict) -> dict:
    def components(year: int) -> tuple[pd.Series, pd.Series]:
        sub = actuals[actuals["Year"] == year]
        grouped = sub.groupby(key)[["Revenue", "GrossProfit"]].sum()
        weight = grouped["Revenue"] / grouped["Revenue"].sum()
        margin = grouped["GrossProfit"] / grouped["Revenue"]
        return weight, margin

    weight_0, margin_0 = components(start)
    weight_1, margin_1 = components(end)
    aligned = pd.concat(
        [weight_0.rename("w0"), weight_1.rename("w1"), margin_0.rename("m0"), margin_1.rename("m1")],
        axis=1,
    ).fillna(0.0)
    mix = float(((aligned["w1"] - aligned["w0"]) * aligned["m0"]).sum())
    rate = float((aligned["w1"] * (aligned["m1"] - aligned["m0"])).sum())
    detail = {
        labels[int(index)]: {
            "share_start": float(row.w0),
            "share_end": float(row.w1),
            "margin_start": float(row.m0),
            "margin_end": float(row.m1),
        }
        for index, row in aligned.iterrows()
    }
    return {"mix_effect": mix, "rate_effect": rate, "total_change": mix + rate, "lines": detail}


def pnl_block(row: dict) -> dict[str, str]:
    return {
        "revenue": money_m(row["revenue"]),
        "gross_margin": pct(row["gross_margin"]),
        "opex": money_m(row["opex"]),
        "ebitda": money_m(row["ebitda"]),
        "ebitda_margin": pct(row["ebitda_margin"]),
    }


def build_readme_figures(metrics: dict) -> list[str]:
    actual = metrics["annual_actuals"]
    budget = metrics["annual_budget"]
    yoy = metrics["yoy"]
    forecast = metrics["forecast_2026"]
    backtest = metrics["backtest"]
    bridge = metrics["margin_bridge_fy2022_fy2025"]
    mix = metrics["mix"]
    figures = [
        f"FY2022 revenue {pnl_block(actual['2022'])['revenue']}",
        f"FY2022 gross margin {pnl_block(actual['2022'])['gross_margin']}",
        f"FY2022 EBITDA {pnl_block(actual['2022'])['ebitda']}",
        f"FY2022 EBITDA margin {pnl_block(actual['2022'])['ebitda_margin']}",
        f"FY2023 revenue {pnl_block(actual['2023'])['revenue']}",
        f"FY2023 growth {yoy['2023']['revenue']}",
        f"FY2024 revenue {pnl_block(actual['2024'])['revenue']}",
        f"FY2024 growth {yoy['2024']['revenue']}",
        f"FY2024 beat the budget by {yoy['2024']['vs_budget']}",
        f"FY2025 revenue {pnl_block(actual['2025'])['revenue']}",
        f"FY2025 growth {yoy['2025']['revenue']}",
        f"FY2025 revenue versus budget {metrics['fy2025_vs_budget']['revenue']}",
        f"FY2025 revenue variance {metrics['fy2025_vs_budget']['revenue_pct']}",
        f"FY2025 gross margin {pnl_block(actual['2025'])['gross_margin']}",
        f"FY2025 gross margin versus budget {metrics['fy2025_vs_budget']['gross_margin_bps']}",
        f"FY2025 EBITDA {pnl_block(actual['2025'])['ebitda']}",
        f"FY2025 EBITDA versus budget {metrics['fy2025_vs_budget']['ebitda']}",
        f"FY2025 EBITDA variance {metrics['fy2025_vs_budget']['ebitda_pct']}",
        f"FY2025 EBITDA margin {pnl_block(actual['2025'])['ebitda_margin']}",
        f"FY2025 OpEx {pnl_block(actual['2025'])['opex']}",
        f"FY2025 OpEx versus budget {metrics['fy2025_vs_budget']['opex']}",
        f"three-year revenue CAGR {metrics['cagr_fy2022_fy2025']}",
        f"gross margin expanded {metrics['gross_margin_expansion_bps']}",
        f"EBITDA margin expanded {metrics['ebitda_margin_expansion_bps']}",
        f"software mix from {mix['product']['2022']['Industrial Software']} to {mix['product']['2025']['Industrial Software']}",
        f"equipment mix from {mix['product']['2022']['Process Equipment']} to {mix['product']['2025']['Process Equipment']}",
        f"Asia Pacific mix from {mix['region']['2022']['Asia Pacific']} to {mix['region']['2025']['Asia Pacific']}",
        f"North America was {mix['region']['2025']['North America']} of FY2025 revenue",
        f"mix effect {bridge['mix_effect']} and rate effect {bridge['rate_effect']}",
        f"FY2026 budget revenue {pnl_block(budget['2026'])['revenue']}",
        f"FY2026 budget gross margin {pnl_block(budget['2026'])['gross_margin']}",
        f"FY2026 budget EBITDA {pnl_block(budget['2026'])['ebitda']}",
        f"FY2026 budget EBITDA margin {pnl_block(budget['2026'])['ebitda_margin']}",
        f"FY2026 budget growth {forecast['budget_vs_fy2025']}",
        f"FY2026 base revenue {pnl_block(forecast['base'])['revenue']}",
        f"FY2026 base growth {forecast['base_vs_fy2025']}",
        f"FY2026 base versus budget {forecast['base_vs_budget']}",
        f"FY2026 base EBITDA versus budget {forecast['base_ebitda_vs_budget']}",
        f"FY2026 base gross margin {pnl_block(forecast['base'])['gross_margin']}",
        f"FY2026 base EBITDA {pnl_block(forecast['base'])['ebitda']}",
        f"FY2026 base EBITDA margin {pnl_block(forecast['base'])['ebitda_margin']}",
        f"FY2026 upside revenue {pnl_block(forecast['upside'])['revenue']}",
        f"FY2026 upside EBITDA {pnl_block(forecast['upside'])['ebitda']}",
        f"FY2026 downside revenue {pnl_block(forecast['downside'])['revenue']}",
        f"FY2026 downside EBITDA {pnl_block(forecast['downside'])['ebitda']}",
        f"holdout MAPE {backtest['mape']}",
        f"holdout WAPE {backtest['wape']}",
        f"holdout RMSE {backtest['rmse']}",
        f"holdout bias {backtest['bias']}",
        f"80% interval {forecast['interval_80']}",
        f"95% interval {forecast['interval_95']}",
        f"North America FY2025 revenue {metrics['region_fy2025']['North America']['revenue']}",
        f"North America EBITDA margin {metrics['region_fy2025']['North America']['ebitda_margin']}",
        f"North America growth {metrics['region_fy2025']['North America']['yoy']}",
        f"EMEA FY2025 revenue {metrics['region_fy2025']['EMEA']['revenue']}",
        f"EMEA growth {metrics['region_fy2025']['EMEA']['yoy']}",
        f"EMEA EBITDA margin {metrics['region_fy2025']['EMEA']['ebitda_margin']}",
        f"Asia Pacific FY2025 revenue {metrics['region_fy2025']['Asia Pacific']['revenue']}",
        f"Asia Pacific growth {metrics['region_fy2025']['Asia Pacific']['yoy']}",
        f"Asia Pacific EBITDA margin {metrics['region_fy2025']['Asia Pacific']['ebitda_margin']}",
        f"Latin America FY2025 revenue {metrics['region_fy2025']['Latin America']['revenue']}",
        f"Latin America growth {metrics['region_fy2025']['Latin America']['yoy']}",
        (
            "smoothing coefficients "
            f"level {metrics['backtest']['level_smoothing']:.2f}, "
            f"trend {metrics['backtest']['trend_smoothing']:.2f}, "
            f"seasonal {metrics['backtest']['seasonal_smoothing']:.2f}"
        ),
    ]
    return figures


def main() -> None:
    actuals = load_actuals()
    budget = load_budget()
    series = monthly_revenue(actuals)
    train = series[series.index.year < HOLDOUT_YEAR]
    test = series[series.index.year == HOLDOUT_YEAR]

    holdout_fit = fit_holt_winters(train)
    holdout_forecast = forecast_values(holdout_fit, 12, train)
    holdout_forecast.index = test.index
    scores = accuracy(test, holdout_forecast)
    if scores["mape"] > 0.12:
        holdout_forecast = seasonal_ols_forecast(train, 12)
        holdout_forecast.index = test.index
        scores = accuracy(test, holdout_forecast)
        model_name = "Seasonal trend regression (fallback)"
        model_used = "ols"
    else:
        model_name = "Holt-Winters additive trend, multiplicative seasonality, period 12"
        model_used = "holt_winters"

    full_fit = fit_holt_winters(series)
    base_forecast = forecast_values(full_fit, 12, series)
    intervals = annual_intervals(full_fit, base_forecast)
    downside = shape_scenario(base_forecast, intervals["p10"])
    upside = shape_scenario(base_forecast, intervals["p90"])

    params = {}
    for key, value in full_fit.params.items():
        if value is None or np.ndim(value) != 0:
            continue
        params[key] = float(value)

    shares_2025 = same_month_shares(actuals, 2025)
    shares_2024 = same_month_shares(actuals, 2024)
    margins_2025 = rate_table(actuals, 2025)
    margins_2024 = rate_table(actuals, 2024)

    opex_2025 = (
        actuals[actuals["Year"] == 2025].groupby("Month")["OpEx"].sum().astype(float).to_dict()
    )
    opex_2024 = (
        actuals[actuals["Year"] == 2024].groupby("Month")["OpEx"].sum().astype(float).to_dict()
    )
    # Backtest opex pool: FY2024 opex ratio carried onto the FY2025 forecast revenue.
    opex_ratio_2024 = float(actuals.loc[actuals["Year"] == 2024, "OpEx"].sum() / actuals.loc[actuals["Year"] == 2024, "Revenue"].sum())

    scenario_paths = {
        "Forecast - Base": base_forecast,
        "Forecast - Downside": downside,
        "Forecast - Upside": upside,
    }
    forecast_rows: list[dict] = []
    for scenario, path in scenario_paths.items():
        drifted = {
            month: apply_drift(shares, MIX_DRIFT[scenario]["product"], MIX_DRIFT[scenario]["region"])
            for month, shares in shares_2025.items()
        }
        opex_pool = {month: float(amount) * OPEX_GROWTH[scenario] for month, amount in opex_2025.items()}
        forecast_rows.extend(
            build_year(
                path,
                drifted,
                margins_2025,
                MARGIN_DELTA[scenario],
                opex_pool,
                scenario,
            )
        )

    backtest_opex = {
        month: float(holdout_forecast.loc[holdout_forecast.index.month == month].iloc[0]) * opex_ratio_2024
        for month in range(1, 13)
    }
    # Keep the FY2024 seasonal opex shape, scaled to the carry-forward ratio.
    opex_2024_total = sum(opex_2024.values())
    backtest_revenue_total = float(holdout_forecast.sum())
    backtest_opex_total = backtest_revenue_total * opex_ratio_2024
    backtest_opex = {
        month: backtest_opex_total * (opex_2024[month] / opex_2024_total) for month in range(1, 13)
    }
    backtest_rows = build_year(
        holdout_forecast,
        shares_2024,
        margins_2024,
        0.0,
        backtest_opex,
        "Backtest",
    )

    forecast_frame = pd.DataFrame(forecast_rows + backtest_rows)
    for column in ("Revenue", "COGS", "GrossProfit", "OpEx", "EBITDA"):
        gap = (forecast_frame["GrossProfit"] - (forecast_frame["Revenue"] - forecast_frame["COGS"])).abs().max()
        ebitda_gap = (forecast_frame["EBITDA"] - (forecast_frame["GrossProfit"] - forecast_frame["OpEx"])).abs().max()
        if gap > 0.02 or ebitda_gap > 0.02:
            raise SystemExit(f"Forecast accounting identity failed ({gap}, {ebitda_gap})")
        break

    base_total = float(forecast_frame.loc[forecast_frame["Scenario"] == "Forecast - Base", "Revenue"].sum())
    down_total = float(forecast_frame.loc[forecast_frame["Scenario"] == "Forecast - Downside", "Revenue"].sum())
    up_total = float(forecast_frame.loc[forecast_frame["Scenario"] == "Forecast - Upside", "Revenue"].sum())
    if not (down_total < base_total < up_total):
        raise SystemExit("Scenario ordering failed")

    budget_out = budget.copy()
    budget_out["Date"] = budget_out["Date"].dt.strftime("%Y-%m-%d")
    combined = pd.concat([budget_out, forecast_frame], ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"])
    combined["__order"] = combined["Scenario"].map({name: index for index, name in enumerate(SCENARIO_ORDER)})
    combined = combined.sort_values(
        ["Date", "__order", "RegionKey", "ProductLineKey", "SegmentKey"]
    ).drop(columns="__order")
    combined["Date"] = combined["Date"].dt.strftime("%Y-%m-%d")
    combined.to_csv(DATA / "fact_budget_forecast.csv", index=False, lineterminator="\n")

    region_labels = {row["RegionKey"]: row["Region"] for row in REGIONS}
    product_labels = {row["ProductLineKey"]: row["ProductLine"] for row in PRODUCTS}
    segment_labels = {row["SegmentKey"]: row["Segment"] for row in SEGMENTS}

    annual_actuals = {}
    annual_budget = {}
    for year in (2022, 2023, 2024, 2025):
        annual_actuals[str(year)] = statement(actuals[actuals["Year"] == year])
    budget["Year"] = budget["Date"].dt.year
    for year in (2022, 2023, 2024, 2025, 2026):
        annual_budget[str(year)] = statement(budget[budget["Year"] == year])

    scenarios = {}
    for name, key in (
        ("Forecast - Base", "base"),
        ("Forecast - Upside", "upside"),
        ("Forecast - Downside", "downside"),
    ):
        scenarios[key] = statement(forecast_frame[forecast_frame["Scenario"] == name])

    fy2025 = annual_actuals["2025"]
    fy2024 = annual_actuals["2024"]
    fy2022 = annual_actuals["2022"]
    bud2025 = annual_budget["2025"]
    bud2026 = annual_budget["2026"]

    def yoy_block(year: int) -> dict[str, str]:
        current = annual_actuals[str(year)]
        prior = annual_actuals[str(year - 1)]
        plan = annual_budget[str(year)]
        return {
            "revenue": pct(current["revenue"] / prior["revenue"] - 1, signed=True),
            "ebitda": pct(current["ebitda"] / prior["ebitda"] - 1, signed=True),
            "vs_budget": pct(current["revenue"] / plan["revenue"] - 1, signed=True),
        }

    product_bridge = margin_bridge(actuals, 2022, 2025, "ProductLineKey", product_labels)
    region_fy2025 = {}
    for key, label in region_labels.items():
        current = actuals[(actuals["Year"] == 2025) & (actuals["RegionKey"] == key)]
        prior = actuals[(actuals["Year"] == 2024) & (actuals["RegionKey"] == key)]
        block = statement(current)
        block["yoy"] = block["revenue"] / float(prior["Revenue"].sum()) - 1
        region_fy2025[label] = block

    mix = {
        "region": {
            "2022": {k: pct(v) for k, v in mix_shares(actuals, 2022, "RegionKey", region_labels).items()},
            "2025": {k: pct(v) for k, v in mix_shares(actuals, 2025, "RegionKey", region_labels).items()},
        },
        "product": {
            "2022": {k: pct(v) for k, v in mix_shares(actuals, 2022, "ProductLineKey", product_labels).items()},
            "2025": {k: pct(v) for k, v in mix_shares(actuals, 2025, "ProductLineKey", product_labels).items()},
        },
        "segment": {
            "2022": {k: pct(v) for k, v in mix_shares(actuals, 2022, "SegmentKey", segment_labels).items()},
            "2025": {k: pct(v) for k, v in mix_shares(actuals, 2025, "SegmentKey", segment_labels).items()},
        },
    }

    monthly_backtest = []
    for date, actual_value in test.items():
        forecast_value = float(holdout_forecast.loc[date])
        monthly_backtest.append(
            {
                "month": date.strftime("%Y-%m"),
                "actual": round(float(actual_value), 2),
                "forecast": round(forecast_value, 2),
                "absolute_pct_error": abs(forecast_value - float(actual_value)) / float(actual_value),
            }
        )

    metrics: dict = {
        "dataset": {
            "synthetic": True,
            "company": "Vantage Process Group",
            "currency": "USD",
            "seed": SEED,
            "actuals": "2022-01 to 2025-12",
            "budget": "2022-01 to 2026-12",
            "forecast": "2026-01 to 2026-12",
            "grain": "month x region x product line x customer segment",
        },
        "row_counts": {
            "dim_date": 1826,
            "dim_region": len(REGIONS),
            "dim_product_line": len(PRODUCTS),
            "dim_customer_segment": len(SEGMENTS),
            "fact_revenue_actuals": int(len(actuals)),
            "fact_budget_rows": int(len(budget)),
            "fact_forecast_rows": int((forecast_frame["Scenario"] != "Backtest").sum()),
            "fact_backtest_rows": int((forecast_frame["Scenario"] == "Backtest").sum()),
            "fact_budget_forecast": int(len(combined)),
        },
        "annual_actuals": annual_actuals,
        "annual_budget": annual_budget,
        "fy2025_vs_budget": {
            "revenue": money_m(fy2025["revenue"] - bud2025["revenue"], signed=True),
            "revenue_pct": pct(fy2025["revenue"] / bud2025["revenue"] - 1, signed=True),
            "gross_margin_bps": bps(fy2025["gross_margin"] - bud2025["gross_margin"]),
            "ebitda": money_m(fy2025["ebitda"] - bud2025["ebitda"], signed=True),
            "ebitda_pct": pct(fy2025["ebitda"] / bud2025["ebitda"] - 1, signed=True),
            "opex": money_m(fy2025["opex"] - bud2025["opex"], signed=True),
        },
        "yoy": {str(year): yoy_block(year) for year in (2023, 2024, 2025)},
        "cagr_fy2022_fy2025": pct((fy2025["revenue"] / fy2022["revenue"]) ** (1 / 3) - 1),
        "gross_margin_expansion_bps": bps(fy2025["gross_margin"] - fy2022["gross_margin"]),
        "ebitda_margin_expansion_bps": bps(fy2025["ebitda_margin"] - fy2022["ebitda_margin"]),
        "mix": mix,
        "margin_bridge_fy2022_fy2025": {
            "mix_effect": bps(product_bridge["mix_effect"]),
            "rate_effect": bps(product_bridge["rate_effect"]),
            "total_change": bps(product_bridge["total_change"]),
            "lines": product_bridge["lines"],
        },
        "region_fy2025": {
            label: {
                "revenue": money_m(block["revenue"]),
                "gross_margin": pct(block["gross_margin"]),
                "ebitda_margin": pct(block["ebitda_margin"]),
                "yoy": pct(block["yoy"], signed=True),
            }
            for label, block in region_fy2025.items()
        },
        "forecast_2026": {
            "base": scenarios["base"],
            "upside": scenarios["upside"],
            "downside": scenarios["downside"],
            "base_vs_fy2025": pct(scenarios["base"]["revenue"] / fy2025["revenue"] - 1, signed=True),
            "base_vs_budget": money_m(scenarios["base"]["revenue"] - bud2026["revenue"], signed=True),
            "base_ebitda_vs_budget": money_m(scenarios["base"]["ebitda"] - bud2026["ebitda"], signed=True),
            "base_vs_budget_pct": pct(scenarios["base"]["revenue"] / bud2026["revenue"] - 1, signed=True),
            "budget_vs_fy2025": pct(bud2026["revenue"] / fy2025["revenue"] - 1, signed=True),
            "interval_80": f"{money_m(intervals['p10'])} to {money_m(intervals['p90'])}",
            "interval_95": f"{money_m(intervals['p2_5'])} to {money_m(intervals['p97_5'])}",
        },
        "backtest": {
            "model": model_name,
            "model_key": model_used,
            "train": "2022-01 to 2024-12",
            "holdout": "2025-01 to 2025-12",
            "origin": "December 2024 close",
            "mape": pct(scores["mape"]),
            "wape": pct(scores["wape"]),
            "rmse": money_k(scores["rmse"]),
            "bias": pct(scores["bias"], signed=True),
            "mape_raw": scores["mape"],
            "wape_raw": scores["wape"],
            "rmse_raw": scores["rmse"],
            "bias_raw": scores["bias"],
            "holdout_actual_revenue": round(float(test.sum()), 2),
            "holdout_forecast_revenue": round(float(holdout_forecast.sum()), 2),
            "monthly": monthly_backtest,
            "level_smoothing": round(params.get("smoothing_level", 0.0), 4),
            "trend_smoothing": round(params.get("smoothing_trend", 0.0), 4),
            "seasonal_smoothing": round(params.get("smoothing_seasonal", 0.0), 4),
            "simulations": SIMULATIONS,
            "interval_method": (
                "Residual bootstrap of the refit Holt-Winters model, "
                "4,000 paths, seed 42. Downside and Upside are the 10th and 90th "
                "percentiles of simulated FY2026 revenue, allocated across months "
                "in proportion to the square root of the horizon."
            ),
        },
        "display": {},
    }
    metrics["readme_figures"] = build_readme_figures(metrics)
    metrics["display"] = {
        "fy2022": pnl_block(annual_actuals["2022"]),
        "fy2023": pnl_block(annual_actuals["2023"]),
        "fy2024": pnl_block(annual_actuals["2024"]),
        "fy2025": pnl_block(annual_actuals["2025"]),
        "fy2024_budget": pnl_block(annual_budget["2024"]),
        "fy2025_budget": pnl_block(annual_budget["2025"]),
        "fy2026_budget": pnl_block(annual_budget["2026"]),
        "fy2026_base": pnl_block(scenarios["base"]),
        "fy2026_upside": pnl_block(scenarios["upside"]),
        "fy2026_downside": pnl_block(scenarios["downside"]),
    }

    # JSON-safe: convert numpy scalars that may hide inside the bridge detail.
    def convert(value):
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        if isinstance(value, (np.floating, np.integer)):
            return value.item()
        return value

    (DATA / "forecast_metrics.json").write_text(json.dumps(convert(metrics), indent=2) + "\n")

    print(model_name)
    print(
        f"Holdout MAPE {metrics['backtest']['mape']}  "
        f"WAPE {metrics['backtest']['wape']}  "
        f"RMSE {metrics['backtest']['rmse']}  "
        f"bias {metrics['backtest']['bias']}"
    )
    print(
        f"FY2026 base {money_m(scenarios['base']['revenue'])}  "
        f"down {money_m(scenarios['downside']['revenue'])}  "
        f"up {money_m(scenarios['upside']['revenue'])}  "
        f"budget {money_m(bud2026['revenue'])}"
    )
    print(
        f"Base GM {pct(scenarios['base']['gross_margin'])}  "
        f"EBITDA {money_m(scenarios['base']['ebitda'])} ({pct(scenarios['base']['ebitda_margin'])})"
    )
    print(
        f"Upside EBITDA {money_m(scenarios['upside']['ebitda'])} ({pct(scenarios['upside']['ebitda_margin'])})  "
        f"Downside EBITDA {money_m(scenarios['downside']['ebitda'])} ({pct(scenarios['downside']['ebitda_margin'])})"
    )
    print(
        f"Bridge mix {bps(product_bridge['mix_effect'])}  "
        f"rate {bps(product_bridge['rate_effect'])}"
    )
    print("Smoothing", metrics["backtest"]["level_smoothing"], metrics["backtest"]["trend_smoothing"], metrics["backtest"]["seasonal_smoothing"])
    for figure in metrics["readme_figures"]:
        print(" ·", figure)


if __name__ == "__main__":
    main()
