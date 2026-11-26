"""Check that the published figures, files, and images describe the same dataset."""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
README = (ROOT / "README.md").read_text(encoding="utf-8")
TOLERANCE = 1.0  # dollars


def fail(message: str) -> None:
    raise SystemExit(message)


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        signature = handle.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            fail(f"{path.name} is not a PNG")
        handle.read(8)
        width, height = struct.unpack(">II", handle.read(8))
    return width, height


def statement(frame: pd.DataFrame) -> dict[str, float]:
    revenue = float(frame["Revenue"].sum())
    gross_profit = float(frame["GrossProfit"].sum())
    opex = float(frame["OpEx"].sum())
    ebitda = float(frame["EBITDA"].sum())
    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "opex": opex,
        "ebitda": ebitda,
    }


def close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > TOLERANCE:
        fail(f"{label}: CSV {actual:.2f} vs metrics {expected:.2f}")


def main() -> None:
    metrics = json.loads((DATA / "forecast_metrics.json").read_text(encoding="utf-8"))
    actuals = pd.read_csv(DATA / "fact_revenue_actuals.csv", parse_dates=["Date"])
    plan = pd.read_csv(DATA / "fact_budget_forecast.csv", parse_dates=["Date"])
    dates = pd.read_csv(DATA / "dim_date.csv", parse_dates=["Date"])
    regions = pd.read_csv(DATA / "dim_region.csv")
    products = pd.read_csv(DATA / "dim_product_line.csv")
    segments = pd.read_csv(DATA / "dim_customer_segment.csv")

    if metrics["dataset"]["synthetic"] is not True:
        fail("Metrics file must mark the dataset as synthetic")
    if "simulated" not in README.lower() and "synthetic" not in README.lower():
        fail("README must say the dataset is simulated or synthetic")

    for column in ("Revenue", "COGS", "GrossProfit", "OpEx", "EBITDA"):
        if column not in actuals.columns or column not in plan.columns:
            fail(f"Missing column {column}")
    identity = (actuals["Revenue"] - actuals["COGS"] - actuals["GrossProfit"]).abs().max()
    ebitda_gap = (actuals["GrossProfit"] - actuals["OpEx"] - actuals["EBITDA"]).abs().max()
    if identity > 0.02 or ebitda_gap > 0.02:
        fail("Actuals accounting identity failed")
    plan_gap = (plan["GrossProfit"] - (plan["Revenue"] - plan["COGS"])).abs().max()
    if plan_gap > 0.02:
        fail("Plan accounting identity failed")

    month_starts = set(dates.loc[dates["IsMonthStart"] == True, "DateKey"])  # noqa: E712
    if set(actuals["DateKey"]) - month_starts or set(plan["DateKey"]) - month_starts:
        fail("Fact DateKey values are not month starts on dim_date")
    if set(actuals["RegionKey"]) - set(regions["RegionKey"]):
        fail("Unknown region key")
    if set(actuals["ProductLineKey"]) - set(products["ProductLineKey"]):
        fail("Unknown product key")
    if set(actuals["SegmentKey"]) - set(segments["SegmentKey"]):
        fail("Unknown segment key")

    actuals["Year"] = actuals["Date"].dt.year
    plan["Year"] = plan["Date"].dt.year
    for year, expected in metrics["annual_actuals"].items():
        got = statement(actuals[actuals["Year"] == int(year)])
        for field in ("revenue", "gross_profit", "opex", "ebitda"):
            close(got[field], expected[field], f"FY{year} actual {field}")
    budget = plan[plan["Scenario"] == "Budget"]
    for year, expected in metrics["annual_budget"].items():
        got = statement(budget[budget["Year"] == int(year)])
        for field in ("revenue", "gross_profit", "opex", "ebitda"):
            close(got[field], expected[field], f"FY{year} budget {field}")
    for scenario, key in (
        ("Forecast - Base", "base"),
        ("Forecast - Upside", "upside"),
        ("Forecast - Downside", "downside"),
    ):
        got = statement(plan[plan["Scenario"] == scenario])
        expected = metrics["forecast_2026"][key]
        for field in ("revenue", "gross_profit", "opex", "ebitda"):
            close(got[field], expected[field], f"{scenario} {field}")

    monthly = metrics["backtest"]["monthly"]
    abs_error = sum(abs(row["forecast"] - row["actual"]) for row in monthly)
    actual_total = sum(row["actual"] for row in monthly)
    wape = abs_error / actual_total
    mape = sum(row["absolute_pct_error"] for row in monthly) / len(monthly)
    if abs(wape - metrics["backtest"]["wape_raw"]) > 1e-9:
        fail("Stored WAPE does not match the monthly backtest")
    if abs(mape - metrics["backtest"]["mape_raw"]) > 1e-9:
        fail("Stored MAPE does not match the monthly backtest")
    if not (metrics["forecast_2026"]["downside"]["revenue"] < metrics["forecast_2026"]["base"]["revenue"] < metrics["forecast_2026"]["upside"]["revenue"]):
        fail("Scenario revenue is not ordered downside < base < upside")

    missing = [figure for figure in metrics["readme_figures"] if figure not in README]
    if missing:
        fail("README is missing figures:\n  " + "\n  ".join(missing))

    for name in (
        "assets/01_executive_summary.png",
        "assets/02_forecast_scenarios.png",
        "assets/03_variance_and_margins.png",
        "assets/04_data_model_star_schema.png",
    ):
        if f"]({name})" not in README and f"]({name} " not in README:
            # Markdown image links use the path inside parentheses.
            if name not in README:
                fail(f"README does not link {name}")
        path = ROOT / name
        if not path.exists():
            fail(f"Missing image {name}")
        width, height = png_size(path)
        if width < 2000 or height < 1000:
            fail(f"{name} is {width}x{height}, expected a high-resolution preview")
        if path.stat().st_size < 50_000:
            fail(f"{name} looks empty")

    json_paths = list((ROOT / "powerbi").rglob("*.json")) + [DATA / "forecast_metrics.json"]
    for path in json_paths:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fail(f"{path.relative_to(ROOT)} is not valid JSON: {exc}")

    measures_tmdl = (ROOT / "powerbi/VantageFinancialForecast.SemanticModel/definition/tables/_Measures.tmdl").read_text(encoding="utf-8")
    dax = (ROOT / "dax/measures.dax").read_text(encoding="utf-8")
    dax_names = []
    for line in dax.splitlines():
        if (
            line.endswith(" =")
            and not line.startswith("//")
            and not line[:1].isspace()
            and not line.startswith("VAR ")
        ):
            dax_names.append(line[:-2].strip())
    if len(dax_names) < 40:
        fail(f"Only found {len(dax_names)} measures in dax/measures.dax")
    absent = [name for name in dax_names if f"measure {name} " not in measures_tmdl and f"measure '{name}' " not in measures_tmdl]
    if absent:
        fail("Measures missing from TMDL: " + ", ".join(absent))
    for required in (
        "Revenue YoY %",
        "Revenue MoM %",
        "Revenue Rolling 3M",
        "Revenue Rolling 12M",
        "Forecast WAPE",
        "Forecast MAPE",
        "Forecast Revenue Base",
        "Forecast Revenue Upside",
        "Forecast Revenue Downside",
        "EBITDA Margin %",
        "Revenue vs Budget $",
        "Revenue vs Budget %",
    ):
        if required not in dax_names:
            fail(f"Required measure not exported: {required}")

    relationships = (ROOT / "powerbi/VantageFinancialForecast.SemanticModel/definition/relationships.tmdl").read_text(encoding="utf-8")
    for token in ("fact_revenue_actuals.Date", "dim_date.Date", "fact_budget_forecast.Scenario", "Scenario.Scenario"):
        if token not in relationships:
            fail(f"Relationship file is missing {token}")
    model = (ROOT / "powerbi/VantageFinancialForecast.SemanticModel/definition/model.tmdl").read_text(encoding="utf-8")
    if "defaultPowerBIDataSourceVersion: powerBI_V3" not in model:
        fail("Model is not marked as a Power BI V3 model")

    pages = json.loads((ROOT / "powerbi/VantageFinancialForecast.Report/definition/pages/pages.json").read_text(encoding="utf-8"))
    if len(pages["pageOrder"]) != 4:
        fail("Expected four report pages")
    print(f"Validated {len(metrics['readme_figures'])} README figures, {len(dax_names)} measures, {len(json_paths)} JSON files.")


if __name__ == "__main__":
    main()
