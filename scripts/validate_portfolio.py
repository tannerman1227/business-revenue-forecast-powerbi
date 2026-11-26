"""Check that the repo matches the Census figures and contains no leftover stand-in data.

    python scripts/validate_portfolio.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from retail_lib import (
    CENSUS_ADVANCE_URL,
    CENSUS_HISTORY_URL,
    DATA_DIR,
    DETAIL_KEYS,
    RETAIL_TRADE_KEYS,
    ROOT,
    SECTORS,
    build_headline,
    coverage,
    error_metrics,
    read_csv,
)

TEXT_SUFFIXES = {".md", ".py", ".pq", ".dax", ".json", ".tmdl", ".csv", ".pbip", ".pbir", ".pbism", ".txt"}
IMAGE_LINKS = [
    "assets/01-executive-overview.png",
    "assets/02-sector-performance.png",
    "assets/03-forecast-outlook.png",
    "assets/04-forecast-accuracy.png",
]
PAGE_TITLES = ["Executive Overview", "Sector Performance", "12-Month Forecast", "Forecast Accuracy"]


def banned_phrases() -> list[str]:
    return [
        "vant" + "age",
        "process " + "group",
        "synth" + "etic",
        "fict" + "ional",
        "made-" + "up",
        "lorem " + "ipsum",
        "dummy " + "data",
        "fake " + "company",
        "toy " + "data",
    ]


def main() -> int:
    problems = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            problems.append(message)

    required = [
        ROOT / "README.md",
        ROOT / "requirements.txt",
        ROOT / "scripts" / "fetch_data.py",
        ROOT / "scripts" / "forecast_model.py",
        ROOT / "scripts" / "render_previews.py",
        ROOT / "power_query" / "transformations.pq",
        ROOT / "dax" / "measures.dax",
        DATA_DIR / "fact_retail_sales.csv",
        DATA_DIR / "dim_sector.csv",
        DATA_DIR / "dim_date.csv",
        DATA_DIR / "reference_total.csv",
        DATA_DIR / "fact_forecast.csv",
        DATA_DIR / "forecast_total.csv",
        DATA_DIR / "fact_backtest.csv",
        DATA_DIR / "backtest_total.csv",
        DATA_DIR / "data_sources.json",
        DATA_DIR / "forecast_metrics.json",
        DATA_DIR / "kpi_snapshot.json",
        ROOT / "powerbi" / "USRetailForecast.pbip",
    ]
    for path in required:
        check(path.exists(), f"Missing {path.relative_to(ROOT)}")

    phrases = banned_phrases()
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if ".git" in path.parts or "__pycache__" in path.parts or path.name == "validate_portfolio.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for phrase in phrases:
            if phrase in text:
                problems.append(f"{path.relative_to(ROOT)} contains '{phrase}'")

    sources = json.loads((DATA_DIR / "data_sources.json").read_text(encoding="utf-8"))
    metrics = json.loads((DATA_DIR / "forecast_metrics.json").read_text(encoding="utf-8"))
    snapshot = json.loads((DATA_DIR / "kpi_snapshot.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    queries = (ROOT / "power_query" / "transformations.pq").read_text(encoding="utf-8")
    file_urls = {item["url"] for item in sources["files"]}
    check(CENSUS_HISTORY_URL in file_urls, "History workbook URL missing from data_sources.json")
    check(CENSUS_ADVANCE_URL in file_urls, "Advance workbook URL missing from data_sources.json")
    check(CENSUS_HISTORY_URL in readme and CENSUS_ADVANCE_URL in readme, "README is missing a Census workbook link")
    check(CENSUS_HISTORY_URL in queries and CENSUS_ADVANCE_URL in queries, "Power Query is missing a Census workbook link")

    by_key = {row["sector_key"]: row for row in sources["series"]}
    check(set(by_key) == set(DETAIL_KEYS), "data_sources series keys do not match the sector list")
    for sector in SECTORS:
        row = by_key[sector["sector_key"]]
        check(row["fred_series_nsa"] == sector["fred_nsa"], f"NSA series id mismatch for {sector['sector_key']}")
        check(row["fred_series_sa"] == sector["fred_sa"], f"SA series id mismatch for {sector['sector_key']}")
        check(sector["fred_nsa"] in queries, f"Power Query is missing {sector['fred_nsa']}")
        check(
            row["observation_start"] == sources["date_coverage"]["start"]
            and row["observation_end"] == sources["date_coverage"]["end"],
            f"Date coverage mismatch for {sector['sector_key']}",
        )

    fact = read_csv("fact_retail_sales.csv")
    reference = read_csv("reference_total.csv")
    grouped = fact.groupby("Date")[["SalesNSA", "SalesSA"]].sum()
    reference = reference.set_index("Date")
    check(grouped.index.equals(reference.index), "Fact dates do not match the published total")
    check((grouped["SalesNSA"] - reference["TotalNSA"]).abs().max() == 0, "Sector sales do not sum to the published total")
    check((grouped["SalesSA"] - reference["TotalSA"]).abs().max() == 0, "Adjusted sector sales do not sum to the published total")
    retail = fact[fact["SectorKey"].isin(RETAIL_TRADE_KEYS)].groupby("Date")[["SalesNSA", "SalesSA"]].sum()
    check((retail["SalesNSA"] - reference["RetailTradeNSA"]).abs().max() == 0, "Retail sectors do not sum to retail trade")
    check(int(sources["date_coverage"]["months"]) == len(reference), "Month count does not match the fact table")
    check(sources["retrieved_at"] == snapshot["retrieved_at"], "Retrieval timestamps do not match")

    sector_fc = read_csv("fact_forecast.csv")
    total_fc = read_csv("forecast_total.csv").set_index("Date")["ForecastNSA"]
    gap = (sector_fc.groupby("Date")["ForecastNSA"].sum() - total_fc).abs().max()
    check(gap <= 0.001, f"Sector forecasts do not add up to the total ({gap})")
    sector_bt = read_csv("fact_backtest.csv")
    total_bt = read_csv("backtest_total.csv")
    back_gap = (sector_bt.groupby("Date")["ForecastNSA"].sum() - total_bt.set_index("Date")["ForecastNSA"]).abs().max()
    check(back_gap <= 0.001, f"Sector test forecasts do not add up to the total ({back_gap})")

    fresh_total = error_metrics(total_bt["ActualNSA"], total_bt["ForecastNSA"], total_bt["SeasonalNaiveNSA"])
    fresh_total["interval_80_coverage"] = coverage(total_bt["ActualNSA"], total_bt["Lower80"], total_bt["Upper80"])
    for key, value in fresh_total.items():
        check(metrics["total"][key] == value, f"forecast_metrics total {key} does not match the backtest file")

    headline = build_headline(sources, metrics)
    check(headline["literals"] == snapshot["literals"], "kpi_snapshot literals do not match a fresh calculation")
    check(headline["values"] == snapshot["values"], "kpi_snapshot values do not match a fresh calculation")
    for key, value in snapshot["literals"].items():
        check(str(value) in readme, f"README is missing {key}: {value}")

    for link in IMAGE_LINKS:
        path = ROOT / link
        check(path.exists(), f"Missing preview {link}")
        check(f"]({link})" in readme, f"README does not link {link}")
        if path.exists():
            with Image.open(path) as image:
                width, height = image.size
            check(width >= 2400 and height >= 1350, f"{link} is {width}x{height}, expected at least 2400x1350")

    for title in PAGE_TITLES:
        check(title in readme, f"README is missing the page title {title}")
        found = list((ROOT / "powerbi").rglob("page.json"))
        check(any(title in path.read_text(encoding="utf-8") for path in found), f"Report is missing page {title}")

    measures = (ROOT / "dax" / "measures.dax").read_text(encoding="utf-8")
    model_measures = (ROOT / "powerbi" / "USRetailForecast.SemanticModel" / "definition" / "tables" / "Metrics.tmdl").read_text(
        encoding="utf-8"
    )
    for line in measures.splitlines():
        if line.startswith("//// "):
            measure_name = line.split("|", 1)[0].replace("////", "").strip()
            check(f"measure '{measure_name}'" in model_measures, f"Semantic model is missing measure {measure_name}")

    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("Validation passed.")
    print(f"Coverage {sources['date_coverage']['start']} to {sources['date_coverage']['end']}, {sources['date_coverage']['months']} months.")
    print(f"Holdout MAPE {snapshot['literals']['holdout_mape']} versus seasonal naive {snapshot['literals']['seasonal_naive_mape']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
