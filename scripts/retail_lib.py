"""Shared definitions for the Census retail sales forecast project.

Sales figures are nominal millions of dollars, as published by the U.S. Census
Bureau Advance Monthly Sales for Retail and Food Services program and
redistributed by FRED. The 13 detail sectors sum to the published total.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"

FRED_PAGE = "https://fred.stlouisfed.org/series/{series_id}"
CENSUS_SALES_PAGE = "https://www.census.gov/retail/sales.html"
CENSUS_HISTORY_URL = "https://www.census.gov/retail/mrts/www/mrtssales92-present.xlsx"
CENSUS_ADVANCE_URL = "https://www.census.gov/retail/marts/www/marts_current.xlsx"
CENSUS_METHODS_PAGE = "https://www.census.gov/retail/mrts/how_surveys_are_collected.html"
USER_AGENT = "business-revenue-forecast-powerbi (public Census retail forecast; no API key)"

MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_FULL = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

# Census MRTS kind-of-business categories. NSA and SA series are both millions
# of dollars. Detail keys exclude the published total, which is the sum of them.
SECTORS = [
    {
        "sector_key": "MOTOR",
        "sector_name": "Motor Vehicle and Parts Dealers",
        "sector_short": "Motor Vehicles",
        "sector_group": "Durable Goods",
        "channel": "Store Retail",
        "kind_of_business": "441",
        "fred_nsa": "RSMVPDN",
        "fred_sa": "RSMVPD",
        "sort_order": 10,
    },
    {
        "sector_key": "FURNITURE",
        "sector_name": "Furniture and Home Furnishings Stores",
        "sector_short": "Furniture & Home",
        "sector_group": "Durable Goods",
        "channel": "Store Retail",
        "kind_of_business": "442",
        "fred_nsa": "RSFHFSN",
        "fred_sa": "RSFHFS",
        "sort_order": 20,
    },
    {
        "sector_key": "ELECTRONICS",
        "sector_name": "Electronics and Appliance Stores",
        "sector_short": "Electronics",
        "sector_group": "Durable Goods",
        "channel": "Store Retail",
        "kind_of_business": "443",
        "fred_nsa": "RSEASN",
        "fred_sa": "RSEAS",
        "sort_order": 30,
    },
    {
        "sector_key": "BUILDING",
        "sector_name": "Building Materials and Garden Equipment",
        "sector_short": "Building Materials",
        "sector_group": "Durable Goods",
        "channel": "Store Retail",
        "kind_of_business": "444",
        "fred_nsa": "RSBMGESDN",
        "fred_sa": "RSBMGESD",
        "sort_order": 40,
    },
    {
        "sector_key": "FOOD_STORES",
        "sector_name": "Food and Beverage Stores",
        "sector_short": "Food & Beverage Stores",
        "sector_group": "Staples",
        "channel": "Store Retail",
        "kind_of_business": "445",
        "fred_nsa": "RSDBSN",
        "fred_sa": "RSDBS",
        "sort_order": 50,
    },
    {
        "sector_key": "HEALTH",
        "sector_name": "Health and Personal Care Stores",
        "sector_short": "Health & Personal Care",
        "sector_group": "Staples",
        "channel": "Store Retail",
        "kind_of_business": "446",
        "fred_nsa": "RSHPCSN",
        "fred_sa": "RSHPCS",
        "sort_order": 60,
    },
    {
        "sector_key": "GASOLINE",
        "sector_name": "Gasoline Stations",
        "sector_short": "Gasoline Stations",
        "sector_group": "Staples",
        "channel": "Store Retail",
        "kind_of_business": "447",
        "fred_nsa": "RSGASSN",
        "fred_sa": "RSGASS",
        "sort_order": 70,
    },
    {
        "sector_key": "CLOTHING",
        "sector_name": "Clothing and Clothing Accessories Stores",
        "sector_short": "Clothing",
        "sector_group": "Discretionary",
        "channel": "Store Retail",
        "kind_of_business": "448",
        "fred_nsa": "RSCCASN",
        "fred_sa": "RSCCAS",
        "sort_order": 80,
    },
    {
        "sector_key": "SPORTING",
        "sector_name": "Sporting Goods, Hobby, Musical Instrument, and Book Stores",
        "sector_short": "Sporting Goods & Hobby",
        "sector_group": "Discretionary",
        "channel": "Store Retail",
        "kind_of_business": "451",
        "fred_nsa": "RSSGHBMSN",
        "fred_sa": "RSSGHBMS",
        "sort_order": 90,
    },
    {
        "sector_key": "GENERAL",
        "sector_name": "General Merchandise Stores",
        "sector_short": "General Merchandise",
        "sector_group": "Staples",
        "channel": "Store Retail",
        "kind_of_business": "452",
        "fred_nsa": "RSGMSN",
        "fred_sa": "RSGMS",
        "sort_order": 100,
    },
    {
        "sector_key": "MISC",
        "sector_name": "Miscellaneous Store Retailers",
        "sector_short": "Miscellaneous Stores",
        "sector_group": "Discretionary",
        "channel": "Store Retail",
        "kind_of_business": "453",
        "fred_nsa": "RSMSRN",
        "fred_sa": "RSMSR",
        "sort_order": 110,
    },
    {
        "sector_key": "NONSTORE",
        "sector_name": "Nonstore Retailers",
        "sector_short": "Nonstore Retailers",
        "sector_group": "Nonstore",
        "channel": "Nonstore Retail",
        "kind_of_business": "454",
        "fred_nsa": "RSNSRN",
        "fred_sa": "RSNSR",
        "sort_order": 120,
    },
    {
        "sector_key": "FOOD_SERVICE",
        "sector_name": "Food Services and Drinking Places",
        "sector_short": "Food Services",
        "sector_group": "Food Services",
        "channel": "Food Services",
        "kind_of_business": "722",
        "fred_nsa": "RSFSDPN",
        "fred_sa": "RSFSDP",
        "sort_order": 130,
    },
]

TOTAL_SERIES = {
    "sector_key": "TOTAL",
    "sector_name": "Retail Trade and Food Services",
    "sector_short": "All Retail & Food Services",
    "fred_nsa": "RSAFSNA",
    "fred_sa": "RSAFS",
    "role_nsa": "total_nsa",
    "role_sa": "total_sa",
}

RETAIL_TRADE_SERIES = {
    "sector_key": "RETAIL_TRADE",
    "sector_name": "Retail Trade",
    "fred_nsa": "RSXFSN",
    "fred_sa": "RSXFS",
    "role_nsa": "retail_trade_nsa",
    "role_sa": "retail_trade_sa",
}

DETAIL_KEYS = [s["sector_key"] for s in SECTORS]
RETAIL_TRADE_KEYS = [s["sector_key"] for s in SECTORS if s["sector_key"] != "FOOD_SERVICE"]
FORECAST_DECIMALS = 2
RATE_DECIMALS = 6
HOLDOUT_MONTHS = 12
FORWARD_MONTHS = 12
VALIDATION_YEARS = (3, 2, 1)


def sector_by_key() -> dict:
    return {s["sector_key"]: s for s in SECTORS}


def fred_page_url(series_id: str) -> str:
    return FRED_PAGE.format(series_id=series_id)


def month_label(ts, full: bool = False) -> str:
    ts = pd.Timestamp(ts)
    names = MONTH_FULL if full else MONTH_SHORT
    return f"{names[ts.month - 1]} {ts.year}"


def fmt_int(value: float) -> str:
    return f"{int(round(value)):,}"


def fmt_number(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def fmt_billions_from_millions(millions: float, digits: int = 3) -> str:
    return f"{millions / 1000:,.{digits}f}"


def fmt_pct(ratio: float, signed: bool = False) -> str:
    return f"{ratio * 100:+.2f}%" if signed else f"{ratio * 100:.2f}%"


def round_rate(value: float) -> float:
    return float(f"{float(value):.{RATE_DECIMALS}f}")


def round_amount(value: float, digits: int = FORECAST_DECIMALS) -> float:
    return float(f"{float(value):.{digits}f}")


def read_csv(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    frame = pd.read_csv(path)
    if "Date" in frame.columns:
        frame["Date"] = pd.to_datetime(frame["Date"])
    return frame


def load_sales_panel(column: str = "SalesNSA") -> pd.DataFrame:
    fact = read_csv("fact_retail_sales.csv")
    panel = fact.pivot(index="Date", columns="SectorKey", values=column).sort_index()
    panel = panel[DETAIL_KEYS]
    panel.index = pd.DatetimeIndex(panel.index).to_period("M").to_timestamp()
    return panel


def error_metrics(actual, forecast, naive=None) -> dict:
    actual = np.asarray(actual, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    error = forecast - actual
    abs_error = np.abs(error)
    ape = abs_error / np.abs(actual)
    denom = np.abs(forecast) + np.abs(actual)
    smape = np.where(denom == 0, np.nan, 2 * abs_error / denom)
    out = {
        "mape": round_rate(float(np.mean(ape))),
        "wape": round_rate(float(np.sum(abs_error) / np.sum(np.abs(actual)))),
        "smape": round_rate(float(np.mean(smape))),
        "rmse_millions": round_amount(float(np.sqrt(np.mean(error**2)))),
        "mae_millions": round_amount(float(np.mean(abs_error))),
        "bias_millions": round_amount(float(np.mean(error))),
        "actual_millions": round_amount(float(np.sum(actual))),
        "forecast_millions": round_amount(float(np.sum(forecast))),
    }
    if naive is not None:
        naive = np.asarray(naive, dtype=float)
        naive_ape = np.abs(naive - actual) / np.abs(actual)
        out["seasonal_naive_mape"] = round_rate(float(np.mean(naive_ape)))
        out["mape_skill_vs_seasonal_naive"] = round_rate(
            1 - out["mape"] / out["seasonal_naive_mape"] if out["seasonal_naive_mape"] else np.nan
        )
    return out


def coverage(actual, lower, upper) -> float:
    actual = np.asarray(actual, dtype=float)
    lower = np.asarray(lower, dtype=float)
    upper = np.asarray(upper, dtype=float)
    inside = (actual >= lower) & (actual <= upper)
    return round_rate(float(np.mean(inside)))


def build_headline(sources: dict, metrics: dict) -> dict:
    """Exact figures the README and the validator both use."""
    fact = read_csv("fact_retail_sales.csv")
    panel = load_sales_panel("SalesNSA")
    last = panel.index.max()
    prev_month = last - pd.DateOffset(months=1)
    prev_year = last - pd.DateOffset(years=1)
    ytd_start = pd.Timestamp(year=last.year, month=1, day=1)
    ytd_py_start = pd.Timestamp(year=last.year - 1, month=1, day=1)
    ytd_py_end = prev_year

    total = panel.sum(axis=1)
    latest = float(total.loc[last])
    latest_py = float(total.loc[prev_year])
    latest_pm = float(total.loc[prev_month])
    ttm = float(total.loc[prev_year + pd.DateOffset(months=1) : last].sum())
    ttm_py_end = prev_year
    ttm_py_start = ttm_py_end - pd.DateOffset(months=11)
    ttm_py = float(total.loc[ttm_py_start:ttm_py_end].sum())
    ytd = float(total.loc[ytd_start:last].sum())
    ytd_py = float(total.loc[ytd_py_start:ytd_py_end].sum())

    latest_sector = panel.loc[last]
    largest_key = str(latest_sector.idxmax())
    names = sector_by_key()
    sector_yoy = panel.loc[last] / panel.loc[prev_year] - 1
    fastest_key = str(sector_yoy.idxmax())
    slowest_key = str(sector_yoy.idxmin())

    total_metrics = metrics["total"]
    sector_rows = metrics["sectors"]
    best = min(sector_rows, key=lambda row: row["mape"])
    worst = max(sector_rows, key=lambda row: row["mape"])
    model = metrics["model"]

    history_start = pd.Timestamp(sources["date_coverage"]["start"])
    history_end = pd.Timestamp(sources["date_coverage"]["end"])
    literals = {
        "latest_month_label": month_label(last, full=True),
        "history_start_label": month_label(history_start, full=True),
        "history_end_label": month_label(history_end, full=True),
        "history_months": str(int(sources["date_coverage"]["months"])),
        "sector_count": str(len(SECTORS)),
        "latest_sales_millions": fmt_int(latest),
        "latest_sales_billions": fmt_billions_from_millions(latest),
        "latest_yoy": fmt_pct(latest / latest_py - 1, signed=True),
        "latest_mom": fmt_pct(latest / latest_pm - 1, signed=True),
        "latest_prior_year_millions": fmt_int(latest_py),
        "ttm_billions": fmt_billions_from_millions(ttm),
        "ttm_yoy": fmt_pct(ttm / ttm_py - 1, signed=True),
        "ytd_billions": fmt_billions_from_millions(ytd),
        "ytd_yoy": fmt_pct(ytd / ytd_py - 1, signed=True),
        "largest_sector": names[largest_key]["sector_short"],
        "largest_sector_billions": fmt_billions_from_millions(float(latest_sector.loc[largest_key])),
        "largest_sector_share": fmt_pct(float(latest_sector.loc[largest_key]) / latest),
        "fastest_sector": names[fastest_key]["sector_short"],
        "fastest_sector_yoy": fmt_pct(float(sector_yoy.loc[fastest_key]), signed=True),
        "slowest_sector": names[slowest_key]["sector_short"],
        "slowest_sector_yoy": fmt_pct(float(sector_yoy.loc[slowest_key]), signed=True),
        "holdout_window": (
            f"{month_label(model['holdout_start'], full=True)} to {month_label(model['holdout_end'], full=True)}"
        ),
        "forecast_window": (
            f"{month_label(model['forecast_start'], full=True)} to {month_label(model['forecast_end'], full=True)}"
        ),
        "holdout_mape": fmt_pct(total_metrics["mape"]),
        "holdout_wape": fmt_pct(total_metrics["wape"]),
        "seasonal_naive_mape": fmt_pct(total_metrics["seasonal_naive_mape"]),
        "mape_skill": fmt_pct(total_metrics["mape_skill_vs_seasonal_naive"]),
        "holdout_rmse": fmt_number(total_metrics["rmse_millions"], 2),
        "holdout_mae": fmt_number(total_metrics["mae_millions"], 2),
        "holdout_bias": fmt_number(total_metrics["bias_millions"], 2),
        "interval_coverage": fmt_pct(total_metrics["interval_80_coverage"]),
        "forward_12_billions": fmt_billions_from_millions(total_metrics["forward_forecast_millions"]),
        "prior_12_billions": fmt_billions_from_millions(total_metrics["prior_12_actual_millions"]),
        "forward_vs_prior": fmt_pct(total_metrics["forward_vs_prior"], signed=True),
        "model_window": model["window_label"],
        "model_seasonal": model["seasonal"],
        "model_damped": "damped" if model["damped_trend"] else "undamped",
        "best_sector": best["sector_short"],
        "best_sector_mape": fmt_pct(best["mape"]),
        "worst_sector": worst["sector_short"],
        "worst_sector_mape": fmt_pct(worst["mape"]),
        "retrieved_at": sources["retrieved_at"],
        "validation_mape": fmt_pct(model["validation_total_mape"]),
    }
    values = {
        "latest_sales_nsa_millions": int(round(latest)),
        "latest_yoy": round_rate(latest / latest_py - 1),
        "latest_mom": round_rate(latest / latest_pm - 1),
        "ttm_sales_nsa_millions": int(round(ttm)),
        "ttm_yoy": round_rate(ttm / ttm_py - 1),
        "ytd_sales_nsa_millions": int(round(ytd)),
        "ytd_yoy": round_rate(ytd / ytd_py - 1),
        "largest_sector_key": largest_key,
        "fastest_sector_key": fastest_key,
        "slowest_sector_key": slowest_key,
    }
    return {"literals": literals, "values": values}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
