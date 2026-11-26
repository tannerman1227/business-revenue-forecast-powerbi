"""Download U.S. Census retail sales and write the star-schema CSVs.

The history file and the latest advance release are ordinary Excel workbooks.
No API key and no login are required.

    python scripts/fetch_data.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import pandas as pd

from retail_lib import (
    CENSUS_ADVANCE_URL,
    CENSUS_HISTORY_URL,
    CENSUS_METHODS_PAGE,
    CENSUS_SALES_PAGE,
    DATA_DIR,
    DETAIL_KEYS,
    FORWARD_MONTHS,
    MONTH_FULL,
    MONTH_SHORT,
    RETAIL_TRADE_KEYS,
    SECTORS,
    USER_AGENT,
    fred_page_url,
    write_json,
)

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
DETAIL_CODES = {sector["kind_of_business"]: sector["sector_key"] for sector in SECTORS}
TOTAL_NAME = "retail and food services sales, total"
RETAIL_NAME = "retail sales, total"


def download_file(url: str, destination: Path) -> None:
    commands = [
        ["wget", "-q", "-O", str(destination), "--timeout=60", "--tries=3", "--waitretry=2", f"--user-agent={USER_AGENT}", url],
        ["curl", "-fL", "--retry", "3", "--max-time", "90", "-A", USER_AGENT, "-o", str(destination), url],
    ]
    errors = []
    for command in commands:
        try:
            result = subprocess.run(command, check=False, capture_output=True)
        except FileNotFoundError:
            errors.append(f"{command[0]} is not installed")
            continue
        if result.returncode == 0 and destination.exists() and destination.stat().st_size > 0:
            return
        errors.append(result.stderr.decode("utf-8", errors="replace").strip()[:240])
    raise RuntimeError(f"Could not download {url}: {' | '.join(errors)}")


def norm_code(value) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text if text.isdigit() else None


def as_number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def parse_month_label(label, fallback_year=None):
    if not isinstance(label, str):
        return None
    cleaned = label.replace("(p)", "").replace("(r)", "").replace("(a)", "")
    match = re.match(r"([A-Za-z]+)\.?\s*(\d{4})?", cleaned.strip())
    if not match:
        return None
    month = MONTHS.get(match.group(1)[:3].lower())
    if month is None:
        return None
    year = int(match.group(2)) if match.group(2) else fallback_year
    if year is None:
        return None
    return pd.Timestamp(year=year, month=month, day=1)


def empty_store():
    return {"nsa": {}, "sa": {}}


def put_value(store, section, code, stamp, value):
    key = DETAIL_CODES.get(code)
    bucket = "total" if code == "TOTAL" else "retail" if code == "RETAIL" else key
    if bucket is None:
        return
    store[section].setdefault(bucket, {})
    store[section][bucket][stamp] = value


def parse_history(path: Path) -> dict:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    store = empty_store()
    try:
        for sheet_name in workbook.sheetnames:
            if not re.fullmatch(r"\d{4}", str(sheet_name)):
                continue
            rows = list(workbook[sheet_name].iter_rows(values_only=True))
            markers = [
                index
                for index, row in enumerate(rows)
                if len(row) > 1 and isinstance(row[1], str) and "ADJUST" in row[1].upper()
            ]
            if len(markers) < 2:
                raise RuntimeError(f"Sheet {sheet_name} is missing the adjusted and not-adjusted blocks")
            nsa_at, sa_at = markers[0], markers[1]
            header = rows[nsa_at - 1]
            months = []
            for index, label in enumerate(header):
                stamp = parse_month_label(label)
                if stamp is not None:
                    months.append((index, stamp))
            minimum_months = 12 if int(sheet_name) < datetime.now().year else 1
            if len(months) < minimum_months:
                raise RuntimeError(f"Sheet {sheet_name} did not have a full set of months")
            sections = (("nsa", nsa_at, sa_at), ("sa", sa_at, len(rows)))
            for section, start, stop in sections:
                for row in rows[start + 1 : stop]:
                    name = row[1].strip().lower() if isinstance(row[1], str) else ""
                    code = norm_code(row[0])
                    if name == TOTAL_NAME:
                        code = "TOTAL"
                    elif name == RETAIL_NAME:
                        code = "RETAIL"
                    if code is None:
                        continue
                    for index, stamp in months:
                        value = as_number(row[index]) if index < len(row) else None
                        if value is None:
                            token = row[index] if index < len(row) else None
                            if code in DETAIL_CODES and token not in (None, ""):
                                raise RuntimeError(
                                    f"Missing {section} value for {code} on {stamp.date()} in {sheet_name}: {token!r}"
                                )
                            continue
                        put_value(store, section, code, stamp, value)
    finally:
        workbook.close()
    return store


def parse_advance(path: Path) -> dict:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(workbook[workbook.sheetnames[0]].iter_rows(values_only=True))
    finally:
        workbook.close()
    if len(rows) < 12:
        raise RuntimeError("Advance workbook is shorter than expected")
    section_row = rows[5]
    year_row = rows[6]
    month_row = rows[7]
    section = None
    year = None
    columns = []
    for index in range(max(len(section_row), len(year_row), len(month_row))):
        label = section_row[index] if index < len(section_row) else None
        if isinstance(label, str) and "NOT ADJUSTED" in label.upper():
            section = "nsa"
        elif isinstance(label, str) and "ADJUST" in label.upper():
            section = "sa"
        year_cell = year_row[index] if index < len(year_row) else None
        if isinstance(year_cell, (int, float)) and not isinstance(year_cell, bool):
            year = int(year_cell)
        elif isinstance(year_cell, str) and year_cell.strip().isdigit():
            year = int(year_cell.strip())
        month_cell = month_row[index] if index < len(month_row) else None
        stamp = parse_month_label(month_cell, year)
        if section in {"nsa", "sa"} and stamp is not None:
            columns.append((index, section, stamp))
    if len(columns) < 8:
        raise RuntimeError("Could not read the advance release month columns")

    store = empty_store()
    pending = None
    previous_name = ""
    for row in rows[8:]:
        code = norm_code(row[0]) if len(row) else None
        name = row[1].strip().lower() if len(row) > 1 and isinstance(row[1], str) else ""
        present = [index for index, _, _ in columns if index < len(row) and as_number(row[index]) is not None]
        if code in DETAIL_CODES and not present:
            pending = code
            previous_name = name
            continue
        use = code if code in DETAIL_CODES else pending if present else None
        combined = re.sub(r"[^a-z]", "", f"{previous_name} {name}")
        own = re.sub(r"[^a-z]", "", name)
        if use is None and present and "food" in combined and "total" in combined and "excl" not in combined:
            use = "TOTAL"
        elif use is None and present and own == "retail":
            use = "RETAIL"
        previous_name = name
        pending = None if present or not name else pending
        if use is None:
            continue
        for index, section, stamp in columns:
            value = as_number(row[index]) if index < len(row) else None
            if value is None:
                continue
            put_value(store, section, use, stamp, value)
    if any(len(store["nsa"].get(key, {})) == 0 for key in DETAIL_KEYS):
        missing = [key for key in DETAIL_KEYS if not store["nsa"].get(key)]
        raise RuntimeError(f"Advance file did not include sectors: {', '.join(missing)}")
    return store


def overlay(base: dict, extra: dict) -> None:
    for section in ("nsa", "sa"):
        for key, values in extra[section].items():
            base[section].setdefault(key, {}).update(values)


def to_series(values: dict) -> pd.Series:
    series = pd.Series(values, dtype=float).sort_index()
    series.index = pd.DatetimeIndex(series.index)
    return series


def require_complete(panel: pd.DataFrame, label: str) -> None:
    expected = pd.date_range(panel.index.min(), panel.index.max(), freq="MS")
    if not panel.index.equals(expected):
        missing = expected.difference(panel.index)
        raise RuntimeError(f"{label} is missing months: {list(missing[:6])}")
    if panel.isna().any().any():
        raise RuntimeError(f"{label} has blank cells")


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for stamp in pd.date_range(start, end, freq="MS"):
        rows.append(
            {
                "Date": stamp.strftime("%Y-%m-%d"),
                "Year": int(stamp.year),
                "Quarter": int((stamp.month - 1) // 3 + 1),
                "QuarterLabel": f"{stamp.year} Q{(stamp.month - 1) // 3 + 1}",
                "MonthNumber": int(stamp.month),
                "MonthName": MONTH_FULL[stamp.month - 1],
                "MonthShort": MONTH_SHORT[stamp.month - 1],
                "YearMonth": stamp.strftime("%Y-%m"),
                "MonthYearLabel": f"{MONTH_SHORT[stamp.month - 1]} {stamp.year}",
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        history_path = Path(folder) / "mrtssales92-present.xlsx"
        advance_path = Path(folder) / "marts_current.xlsx"
        print("Downloading the Census history workbook...")
        download_file(CENSUS_HISTORY_URL, history_path)
        print("Downloading the latest advance release...")
        download_file(CENSUS_ADVANCE_URL, advance_path)
        print("Reading workbooks...")
        store = parse_history(history_path)
        advance = parse_advance(advance_path)
        overlay(store, advance)

    nsa = pd.DataFrame({key: to_series(store["nsa"][key]) for key in DETAIL_KEYS}).sort_index()
    sa = pd.DataFrame({key: to_series(store["sa"][key]) for key in DETAIL_KEYS}).sort_index()
    total_nsa = to_series(store["nsa"]["total"])
    total_sa = to_series(store["sa"]["total"])
    retail_nsa = to_series(store["nsa"]["retail"])
    retail_sa = to_series(store["sa"]["retail"])
    # The advance total is overwritten for recent months. History already has the
    # published total for every older month. Reindex to the detail calendar.
    require_complete(nsa, "Not adjusted detail")
    require_complete(sa, "Seasonally adjusted detail")
    if not nsa.index.equals(sa.index):
        raise RuntimeError("Not-adjusted and adjusted calendars do not match")
    for label, detail, official in (
        ("not adjusted total", nsa.sum(axis=1), total_nsa.reindex(nsa.index)),
        ("adjusted total", sa.sum(axis=1), total_sa.reindex(sa.index)),
        ("not adjusted retail trade", nsa[RETAIL_TRADE_KEYS].sum(axis=1), retail_nsa.reindex(nsa.index)),
        ("adjusted retail trade", sa[RETAIL_TRADE_KEYS].sum(axis=1), retail_sa.reindex(sa.index)),
    ):
        if official.isna().any():
            raise RuntimeError(f"Published {label} is missing months")
        gap = (detail - official).abs().max()
        if gap > 0.1:
            raise RuntimeError(f"Sector sum does not match the published {label}. Max gap: {gap}")
    print(
        f"Reconciliation passed for {nsa.index.min().date()} to {nsa.index.max().date()} "
        f"({len(nsa)} months)."
    )

    fact_rows = []
    for sector in SECTORS:
        key = sector["sector_key"]
        for stamp in nsa.index:
            fact_rows.append(
                {
                    "Date": stamp.strftime("%Y-%m-%d"),
                    "SectorKey": key,
                    "SalesNSA": int(round(float(nsa.at[stamp, key]))),
                    "SalesSA": int(round(float(sa.at[stamp, key]))),
                }
            )
    fact = pd.DataFrame(fact_rows)
    dim_sector = pd.DataFrame(
        [
            {
                "SectorKey": sector["sector_key"],
                "SectorName": sector["sector_name"],
                "SectorShort": sector["sector_short"],
                "SectorGroup": sector["sector_group"],
                "Channel": sector["channel"],
                "KindOfBusiness": sector["kind_of_business"],
                "FredSeriesNSA": sector["fred_nsa"],
                "FredSeriesSA": sector["fred_sa"],
                "FredUrlNSA": fred_page_url(sector["fred_nsa"]),
                "FredUrlSA": fred_page_url(sector["fred_sa"]),
                "SortOrder": sector["sort_order"],
            }
            for sector in SECTORS
        ]
    )
    history_end = nsa.index.max()
    dim_date = build_dim_date(nsa.index.min(), history_end + pd.DateOffset(months=FORWARD_MONTHS))
    reference = pd.DataFrame(
        {
            "Date": [stamp.strftime("%Y-%m-%d") for stamp in nsa.index],
            "TotalNSA": total_nsa.reindex(nsa.index).round().astype(int).to_numpy(),
            "TotalSA": total_sa.reindex(sa.index).round().astype(int).to_numpy(),
            "RetailTradeNSA": retail_nsa.reindex(nsa.index).round().astype(int).to_numpy(),
            "RetailTradeSA": retail_sa.reindex(sa.index).round().astype(int).to_numpy(),
        }
    )
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    series = []
    for sector in SECTORS:
        series.append(
            {
                "sector_key": sector["sector_key"],
                "sector_name": sector["sector_name"],
                "kind_of_business": sector["kind_of_business"],
                "fred_series_nsa": sector["fred_nsa"],
                "fred_series_sa": sector["fred_sa"],
                "fred_page_nsa": fred_page_url(sector["fred_nsa"]),
                "fred_page_sa": fred_page_url(sector["fred_sa"]),
                "observation_start": nsa.index.min().strftime("%Y-%m-%d"),
                "observation_end": history_end.strftime("%Y-%m-%d"),
                "observations": int(len(nsa)),
            }
        )
    sources = {
        "retrieved_at": retrieved_at,
        "access": "Free public Excel download. No API key and no login.",
        "publisher": "U.S. Census Bureau",
        "program": "Monthly Retail Trade Survey and Advance Monthly Retail Trade Survey",
        "units": "Millions of current dollars (nominal, not inflation adjusted)",
        "frequency": "Monthly",
        "primary_seasonal_adjustment": "Not Seasonally Adjusted",
        "companion_seasonal_adjustment": "Seasonally Adjusted",
        "date_coverage": {
            "start": nsa.index.min().strftime("%Y-%m-%d"),
            "end": history_end.strftime("%Y-%m-%d"),
            "months": int(len(nsa)),
        },
        "reconciliation": {
            "detail_sectors_sum_to": "Retail and food services sales, total",
            "retail_trade_sectors_sum_to": "Retail sales, total",
            "max_absolute_gap_millions": 0,
        },
        "files": [
            {
                "role": "full_history",
                "title": "Estimates of Monthly Retail and Food Services Sales by Kind of Business",
                "url": CENSUS_HISTORY_URL,
                "covers": "January 1992 through the latest month published in the history workbook",
            },
            {
                "role": "latest_advance_release",
                "title": "Advance Monthly Sales for Retail and Food Services",
                "url": CENSUS_ADVANCE_URL,
                "covers": "Any month in the advance release that is newer than the history workbook, plus the overlapping recent months",
            },
        ],
        "census_sales_page": CENSUS_SALES_PAGE,
        "census_methods_page": CENSUS_METHODS_PAGE,
        "fred_note": (
            "FRED redistributes these Census series. The workbook links below are the files "
            "this project downloads. The FRED pages are a convenient chart for the same category."
        ),
        "series": series,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fact.to_csv(DATA_DIR / "fact_retail_sales.csv", index=False)
    dim_sector.to_csv(DATA_DIR / "dim_sector.csv", index=False)
    dim_date.to_csv(DATA_DIR / "dim_date.csv", index=False)
    reference.to_csv(DATA_DIR / "reference_total.csv", index=False)
    write_json(DATA_DIR / "data_sources.json", sources)
    print(f"Wrote {len(fact):,} fact rows and data/data_sources.json")
    print(f"Retrieved {retrieved_at}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
