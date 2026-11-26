"""Generate the Vantage Process Group star schema.

The company is fictional. Every figure in this dataset is synthetic and is
produced from a fixed seed so a fresh run recreates the same files byte for
byte. The generator is the source of the business story:

* FY2022–FY2025 actuals at month x region x product line x segment.
* Annual budgets for FY2022–FY2026, set independently of in-year shocks.
* Seasonality of a capital-equipment business (quarter-end and December flush).
* A mix shift out of process equipment and into software, parts, and service.
* Gross-margin expansion from that mix, partly given back by deal discounting.
* Operating expense with mild operating leverage and a 2025 cost discipline
  that the original budget did not assume.

2026 rolling-forecast scenarios are not invented here. They are written by
``forecast_model.py`` after the Holt-Winters backtest, and appended to
``fact_budget_forecast.csv`` alongside these budget rows.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pandas as pd

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

REGIONS = [
    {
        "RegionKey": 1,
        "Region": "North America",
        "RegionCode": "NA",
        "ManagementGroup": "Americas",
        "Currency": "USD",
    },
    {
        "RegionKey": 2,
        "Region": "EMEA",
        "RegionCode": "EMEA",
        "ManagementGroup": "International",
        "Currency": "USD",
    },
    {
        "RegionKey": 3,
        "Region": "Asia Pacific",
        "RegionCode": "APAC",
        "ManagementGroup": "International",
        "Currency": "USD",
    },
    {
        "RegionKey": 4,
        "Region": "Latin America",
        "RegionCode": "LATAM",
        "ManagementGroup": "Americas",
        "Currency": "USD",
    },
]

PRODUCTS = [
    {
        "ProductLineKey": 1,
        "ProductLine": "Process Equipment",
        "ProductCode": "EQUIP",
        "RevenueType": "Transactional",
        "UnitOfMeasure": "Systems",
        "PortfolioRole": "Core capital franchise",
    },
    {
        "ProductLineKey": 2,
        "ProductLine": "Aftermarket Parts",
        "ProductCode": "PARTS",
        "RevenueType": "Recurring",
        "UnitOfMeasure": "Orders",
        "PortfolioRole": "Installed-base annuity",
    },
    {
        "ProductLineKey": 3,
        "ProductLine": "Field Service Contracts",
        "ProductCode": "SVC",
        "RevenueType": "Recurring",
        "UnitOfMeasure": "Contracts",
        "PortfolioRole": "Contracted service annuity",
    },
    {
        "ProductLineKey": 4,
        "ProductLine": "Industrial Software",
        "ProductCode": "SW",
        "RevenueType": "Recurring",
        "UnitOfMeasure": "Seats",
        "PortfolioRole": "Growth and margin engine",
    },
    {
        "ProductLineKey": 5,
        "ProductLine": "Professional Services",
        "ProductCode": "PS",
        "RevenueType": "Project",
        "UnitOfMeasure": "Engagements",
        "PortfolioRole": "Implementation attach",
    },
]

SEGMENTS = [
    {
        "SegmentKey": 1,
        "Segment": "Enterprise",
        "SegmentCode": "ENT",
        "BuyingMotion": "Multi-year framework agreements",
    },
    {
        "SegmentKey": 2,
        "Segment": "Mid-Market",
        "SegmentCode": "MM",
        "BuyingMotion": "Annual contracts and repeat orders",
    },
    {
        "SegmentKey": 3,
        "Segment": "SMB",
        "SegmentCode": "SMB",
        "BuyingMotion": "Transactional and price sensitive",
    },
]

# Quarter-end billing with a December capital flush. Weights sum to 12,
# so they are the number of "average months" in each calendar month.
SEASONALITY = {
    1: 0.78,
    2: 0.82,
    3: 1.08,
    4: 0.88,
    5: 0.92,
    6: 1.10,
    7: 0.84,
    8: 0.86,
    9: 1.12,
    10: 0.96,
    11: 1.05,
    12: 1.59,
}

# Pre-shock annualized run-rate anchors. Shocks and noise move the realized
# total off these figures on purpose.
ACTUAL_ANCHOR = {
    2022: 168_000_000.0,
    2023: 183_200_000.0,
    2024: 200_400_000.0,
    2025: 219_800_000.0,
}

# Annual budgets locked before each year. They do not contain the supply-chain,
# Europe, enterprise-pause, or 2025 cost-discipline outcomes.
BUDGET_ANCHOR = {
    2022: 173_400_000.0,
    2023: 187_100_000.0,
    2024: 196_200_000.0,
    2025: 225_600_000.0,
}

# FY2026 budget growth versus realized FY2025 revenue. Planning assumption
# set in the November 2025 cycle.
BUDGET_2026_GROWTH = 0.080

REG_START = {"NA": 0.488, "EMEA": 0.302, "APAC": 0.142, "LATAM": 0.068}
REG_END = {"NA": 0.452, "EMEA": 0.252, "APAC": 0.218, "LATAM": 0.078}
BUD_REG_START = {"NA": 0.492, "EMEA": 0.308, "APAC": 0.132, "LATAM": 0.068}
BUD_REG_END = {"NA": 0.460, "EMEA": 0.262, "APAC": 0.202, "LATAM": 0.076}

PROD_START = {"EQUIP": 0.445, "PARTS": 0.180, "SVC": 0.215, "SW": 0.070, "PS": 0.090}
PROD_END = {"EQUIP": 0.328, "PARTS": 0.198, "SVC": 0.236, "SW": 0.162, "PS": 0.076}
BUD_PROD_START = {"EQUIP": 0.462, "PARTS": 0.176, "SVC": 0.208, "SW": 0.064, "PS": 0.090}
BUD_PROD_END = {"EQUIP": 0.348, "PARTS": 0.194, "SVC": 0.228, "SW": 0.148, "PS": 0.082}

SEG_START = {"ENT": 0.575, "MM": 0.305, "SMB": 0.120}
SEG_END = {"ENT": 0.548, "MM": 0.322, "SMB": 0.130}
BUD_SEG_START = {"ENT": 0.582, "MM": 0.300, "SMB": 0.118}
BUD_SEG_END = {"ENT": 0.560, "MM": 0.314, "SMB": 0.126}

# How far each pair departs from an independent mix. Iterative proportional
# fitting then restores the target marginals, so these shape the conditionals
# (software over-indexes to North America and Enterprise) without fighting
# the planned regional and product trajectory.
AFFINITY_REGION_PRODUCT = {
    "NA": {"EQUIP": 0.94, "PARTS": 1.00, "SVC": 1.06, "SW": 1.32, "PS": 0.94},
    "EMEA": {"EQUIP": 1.16, "PARTS": 1.06, "SVC": 1.00, "SW": 0.84, "PS": 0.90},
    "APAC": {"EQUIP": 1.06, "PARTS": 0.90, "SVC": 0.96, "SW": 1.22, "PS": 1.08},
    "LATAM": {"EQUIP": 1.22, "PARTS": 1.12, "SVC": 0.84, "SW": 0.48, "PS": 1.16},
}
AFFINITY_SEGMENT_PRODUCT = {
    "ENT": {"EQUIP": 1.16, "PARTS": 0.84, "SVC": 1.10, "SW": 1.28, "PS": 0.78},
    "MM": {"EQUIP": 0.96, "PARTS": 1.10, "SVC": 1.04, "SW": 0.90, "PS": 1.06},
    "SMB": {"EQUIP": 0.68, "PARTS": 1.32, "SVC": 0.74, "SW": 0.52, "PS": 1.42},
}

# Gross margin rate at the start of FY2022 and the end of FY2025, before
# deal-season, supply-chain, and segment discounts.
GM_START = {"EQUIP": 0.314, "PARTS": 0.554, "SVC": 0.400, "SW": 0.710, "PS": 0.264}
GM_END = {"EQUIP": 0.322, "PARTS": 0.566, "SVC": 0.428, "SW": 0.734, "PS": 0.270}
# Budget margin plan lags the realized mix and price realization.
GM_BUDGET_END = {"EQUIP": 0.328, "PARTS": 0.568, "SVC": 0.428, "SW": 0.732, "PS": 0.272}

# January 2022 fixed operating expense (cash G&A, base R&D, sales ops).
FIXED_OPEX_JAN_2022 = 3_240_000.0
# Actuals: ~5.5% fixed-cost growth, then a 2025 hiring pause.
ACTUAL_FIXED_MONTHLY_GROWTH = 0.00450
ACTUAL_FIXED_GROWTH_2025 = 0.00180
# Budget never assumed the 2025 pause, and assumed a richer variable rate
# (the commission redesign and delivery productivity were not in the plan).
BUDGET_FIXED_MONTHLY_GROWTH = 0.00470
VARIABLE_RATE_ACTUAL = {2022: 0.067, 2023: 0.064, 2024: 0.061, 2025: 0.058}
VARIABLE_RATE_BUDGET = 0.068

# Regional opex intensity relative to revenue. Asia Pacific is in investment
# mode, so it consumes more of the opex pool than its revenue share.
OPEX_INTENSITY = {"NA": 0.86, "EMEA": 1.06, "APAC": 1.34, "LATAM": 1.20}

ASP_START = {"EQUIP": 86_000.0, "PARTS": 4_400.0, "SVC": 2_650.0, "SW": 195.0, "PS": 46_000.0}
ASP_GROWTH = 0.025

MONTHS = pd.date_range("2022-01-01", "2025-12-01", freq="MS")
BUDGET_MONTHS = pd.date_range("2022-01-01", "2026-12-01", freq="MS")


def normal(key: str, sigma: float) -> float:
    """Deterministic standard-normal draw keyed by seed and business key.

    Hashing the key avoids any dependence on loop order or on the numpy
    bit-generator, so the CSVs stay stable across machines.
    """

    if sigma == 0:
        return 0.0
    digest = hashlib.sha256(f"{SEED}|{key}".encode()).digest()
    u1 = int.from_bytes(digest[:8], "little") / 2**64
    u2 = int.from_bytes(digest[8:16], "little") / 2**64
    u1 = min(max(u1, 1e-12), 1 - 1e-12)
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return sigma * z


def lerp_shares(start: dict[str, float], end: dict[str, float], pos: float) -> dict[str, float]:
    pos = min(max(pos, 0.0), 1.0)
    blended = {k: start[k] + (end[k] - start[k]) * pos for k in start}
    total = sum(blended.values())
    return {k: v / total for k, v in blended.items()}


def fit_marginals(
    region_shares: dict[str, float],
    product_shares: dict[str, float],
    segment_shares: dict[str, float],
) -> dict[tuple[str, str, str], float]:
    weights: dict[tuple[str, str, str], float] = {}
    for region in region_shares:
        for product in product_shares:
            for segment in segment_shares:
                weights[(region, product, segment)] = (
                    region_shares[region]
                    * product_shares[product]
                    * segment_shares[segment]
                    * AFFINITY_REGION_PRODUCT[region][product]
                    * AFFINITY_SEGMENT_PRODUCT[segment][product]
                )

    def scale(level: int, targets: dict[str, float]) -> None:
        for code, target in targets.items():
            current = sum(value for key, value in weights.items() if key[level] == code)
            if current <= 0:
                continue
            factor = target / current
            for key in weights:
                if key[level] == code:
                    weights[key] *= factor

    for _ in range(12):
        scale(0, region_shares)
        scale(1, product_shares)
        scale(2, segment_shares)

    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def shock_multiplier(year: int, month: int, region: str, product: str, segment: str) -> float:
    """Named operating events. Each one is a revenue multiplier on a slice."""

    multiplier = 1.0
    # H1 FY2022: component shortages held equipment shipments; expedited freight
    # also nicked parts. The backlog shipped in the autumn.
    if year == 2022 and month <= 6 and product == "EQUIP":
        multiplier *= 0.90
    if year == 2022 and month <= 6 and product == "PARTS":
        multiplier *= 0.96
    if year == 2022 and month >= 9 and product == "EQUIP":
        multiplier *= 1.065
    # FY2023: European industrial production softened. Equipment demand in
    # EMEA took the largest cut; software was insulated.
    if year == 2023 and region == "EMEA":
        multiplier *= 0.965
        if product == "EQUIP":
            multiplier *= 0.955
    # Q2 FY2024: a cluster of enterprise capex committees paused equipment
    # releases. Most of the volume returned in late Q3.
    if year == 2024 and month in (4, 5, 6) and segment == "ENT" and product == "EQUIP":
        multiplier *= 0.84
    if year == 2024 and month in (8, 9, 10) and segment == "ENT" and product == "EQUIP":
        multiplier *= 1.09
    # Software attach ran ahead of the plan in FY2024 and FY2025.
    if product == "SW" and year == 2024:
        multiplier *= 1.055
    if product == "SW" and year == 2025:
        multiplier *= 1.040
    # H1 FY2025: customers delayed equipment orders on a softer macro print.
    # H2: service-contract wins and parts pull-through offset part of it.
    if year == 2025 and month <= 5:
        multiplier *= 0.978
        if product == "EQUIP":
            multiplier *= 0.955
    if year == 2025 and month >= 7 and product == "SVC":
        multiplier *= 1.055
    if year == 2025 and month >= 7 and product == "PARTS":
        multiplier *= 1.030
    return multiplier


def margin_rate(
    year: int,
    month: int,
    product: str,
    segment: str,
    *,
    budget: bool,
) -> float:
    if budget:
        # Budget curve runs Jan 2022 -> Dec 2026 (59 steps).
        pos = ((year - 2022) * 12 + (month - 1)) / 59
        base = GM_START[product] + (GM_BUDGET_END[product] - GM_START[product]) * pos
    else:
        pos = ((year - 2022) * 12 + (month - 1)) / 47
        base = GM_START[product] + (GM_END[product] - GM_START[product]) * pos
        if year == 2022 and month <= 6 and product == "EQUIP":
            base -= 0.030
        if year == 2022 and month <= 6 and product == "PARTS":
            base -= 0.014
        if year == 2025 and month >= 7 and product == "SW":
            base += 0.005
    # Year-end equipment and services deals are discounted in both the plan
    # and the actuals. The budget already "knows" about this pattern.
    if month in (11, 12) and product == "EQUIP":
        base -= 0.011
    if month in (11, 12) and product == "PS":
        base -= 0.007
    if segment == "ENT":
        base += 0.003
    if segment == "SMB":
        base -= 0.008
    if not budget:
        base += normal(f"gm|{year}|{month}|{product}|{segment}", 0.0012)
    return float(min(max(base, 0.15), 0.82))


def fixed_opex(year: int, month: int, *, budget: bool) -> float:
    step = (year - 2022) * 12 + (month - 1)
    if budget:
        growth = (1 + BUDGET_FIXED_MONTHLY_GROWTH) ** step
    elif step < 36:
        growth = (1 + ACTUAL_FIXED_MONTHLY_GROWTH) ** step
    else:
        growth = (1 + ACTUAL_FIXED_MONTHLY_GROWTH) ** 36
        growth *= (1 + ACTUAL_FIXED_GROWTH_2025) ** (step - 36)
    return FIXED_OPEX_JAN_2022 * growth


def allocate_cents(weights: dict[tuple, float], pool: float) -> dict[tuple, float]:
    """Split a dollar pool in proportion to weights and reconcile to the cent."""

    total = sum(max(value, 0.0) for value in weights.values())
    if total <= 0 or pool == 0:
        return {key: 0.0 for key in weights}
    raw = {key: pool * max(value, 0.0) / total for key, value in weights.items()}
    rounded = {key: round(value, 2) for key, value in raw.items()}
    drift = round(round(pool, 2) - sum(rounded.values()), 2)
    largest = max(weights, key=lambda key: weights[key])
    rounded[largest] = round(rounded[largest] + drift, 2)
    return rounded


def build_fact(months: pd.DatetimeIndex, *, budget: bool, anchors: dict[int, float]) -> pd.DataFrame:
    region_by_code = {row["RegionCode"]: row["RegionKey"] for row in REGIONS}
    product_by_code = {row["ProductCode"]: row["ProductLineKey"] for row in PRODUCTS}
    segment_by_code = {row["SegmentCode"]: row["SegmentKey"] for row in SEGMENTS}

    # First pass: revenue and gross margin. OpEx needs the month's revenue.
    staged: dict[pd.Timestamp, list[dict]] = {}
    for date in months:
        year = int(date.year)
        month = int(date.month)
        if budget:
            pos = ((year - 2022) * 12 + (month - 1)) / 59
            region_shares = lerp_shares(BUD_REG_START, BUD_REG_END, pos)
            product_shares = lerp_shares(BUD_PROD_START, BUD_PROD_END, pos)
            segment_shares = lerp_shares(BUD_SEG_START, BUD_SEG_END, pos)
        else:
            pos = ((year - 2022) * 12 + (month - 1)) / 47
            region_shares = lerp_shares(REG_START, REG_END, pos)
            product_shares = lerp_shares(PROD_START, PROD_END, pos)
            segment_shares = lerp_shares(SEG_START, SEG_END, pos)
        shares = fit_marginals(region_shares, product_shares, segment_shares)
        company = anchors[year] * SEASONALITY[month] / 12.0
        company *= 1.0 + (0.0 if budget else normal(f"co|{year}|{month}", 0.0055))

        slices = []
        for (region, product, segment), share in shares.items():
            revenue = company * share
            if not budget:
                revenue *= shock_multiplier(year, month, region, product, segment)
                revenue *= 1.0 + normal(
                    f"slice|{year}|{month}|{region}|{product}|{segment}",
                    0.0025,
                )
            revenue = round(max(revenue, 0.0), 2)
            gm = margin_rate(year, month, product, segment, budget=budget)
            cogs = round(revenue * (1.0 - gm), 2)
            gross_profit = round(revenue - cogs, 2)
            years_out = (year - 2022) + (month - 1) / 12.0
            asp = ASP_START[product] * ((1 + ASP_GROWTH) ** years_out)
            units = int(round(revenue / asp)) if asp else 0
            slices.append(
                {
                    "DateKey": int(date.strftime("%Y%m%d")),
                    "Date": date.date().isoformat(),
                    "RegionKey": region_by_code[region],
                    "ProductLineKey": product_by_code[product],
                    "SegmentKey": segment_by_code[segment],
                    "_region": region,
                    "Revenue": revenue,
                    "COGS": cogs,
                    "GrossProfit": gross_profit,
                    "VolumeUnits": units,
                }
            )
        staged[date] = slices

    rows: list[dict] = []
    for date, slices in staged.items():
        year = int(date.year)
        month = int(date.month)
        company_revenue = sum(slice_["Revenue"] for slice_ in slices)
        variable_rate = VARIABLE_RATE_BUDGET if budget else VARIABLE_RATE_ACTUAL[year]
        pool = fixed_opex(year, month, budget=budget) + variable_rate * company_revenue
        weights = {}
        for slice_ in slices:
            weights[
                (slice_["RegionKey"], slice_["ProductLineKey"], slice_["SegmentKey"])
            ] = slice_["Revenue"] * OPEX_INTENSITY[slice_["_region"]]
        opex_map = allocate_cents(weights, pool)
        for slice_ in slices:
            key = (slice_["RegionKey"], slice_["ProductLineKey"], slice_["SegmentKey"])
            opex = opex_map[key]
            slice_["OpEx"] = opex
            slice_["EBITDA"] = round(slice_["GrossProfit"] - opex, 2)
            del slice_["_region"]
            rows.append(slice_)

    frame = pd.DataFrame(rows)
    return frame.sort_values(
        ["Date", "RegionKey", "ProductLineKey", "SegmentKey"]
    ).reset_index(drop=True)


def build_date_dimension() -> pd.DataFrame:
    dates = pd.date_range("2022-01-01", "2026-12-31", freq="D")
    month_short = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    rows = []
    for date in dates:
        stage = "Actuals" if date <= pd.Timestamp("2025-12-31") else "Forecast Horizon"
        rows.append(
            {
                "DateKey": int(date.strftime("%Y%m%d")),
                "Date": date.date().isoformat(),
                "Year": int(date.year),
                "FiscalYear": int(date.year),
                "FiscalYearLabel": f"FY{date.year}",
                "Quarter": int(date.quarter),
                "QuarterName": f"Q{date.quarter}",
                "YearQuarter": f"{date.year} Q{date.quarter}",
                "MonthNumber": int(date.month),
                "MonthName": date.strftime("%B"),
                "MonthShort": month_short[date.month - 1],
                "MonthYear": f"{month_short[date.month - 1]} {date.year}",
                "YearMonth": date.strftime("%Y-%m"),
                "YearMonthSort": int(date.strftime("%Y%m")),
                "Day": int(date.day),
                "MonthStart": date.replace(day=1).date().isoformat(),
                "IsMonthStart": bool(date.day == 1),
                "CalendarStage": stage,
            }
        )
    return pd.DataFrame(rows)


def accounting_ok(frame: pd.DataFrame) -> None:
    gp_gap = (frame["Revenue"] - frame["COGS"] - frame["GrossProfit"]).abs().max()
    ebitda_gap = (frame["GrossProfit"] - frame["OpEx"] - frame["EBITDA"]).abs().max()
    if gp_gap > 0.001 or ebitda_gap > 0.001:
        raise SystemExit(f"Accounting identity failed: GP {gp_gap} EBITDA {ebitda_gap}")
    if (frame["Revenue"] < 0).any() or (frame["COGS"] < 0).any() or (frame["OpEx"] < 0).any():
        raise SystemExit("Negative revenue, COGS, or OpEx in generated facts")


def annual_statement(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["Year"] = pd.to_datetime(work["Date"]).dt.year
    grouped = work.groupby("Year", as_index=True)[["Revenue", "COGS", "GrossProfit", "OpEx", "EBITDA"]].sum()
    grouped["GrossMargin"] = grouped["GrossProfit"] / grouped["Revenue"]
    grouped["EbitdaMargin"] = grouped["EBITDA"] / grouped["Revenue"]
    return grouped


def write_csv(frame: pd.DataFrame, name: str) -> None:
    path = DATA / name
    frame.to_csv(path, index=False, lineterminator="\n")


def main() -> None:
    if abs(sum(SEASONALITY.values()) - 12.0) > 1e-9:
        raise SystemExit("Seasonality weights must sum to 12")

    DATA.mkdir(parents=True, exist_ok=True)

    dim_date = build_date_dimension()
    dim_region = pd.DataFrame(REGIONS)
    dim_product = pd.DataFrame(PRODUCTS)
    dim_segment = pd.DataFrame(SEGMENTS)

    actuals = build_fact(MONTHS, budget=False, anchors=ACTUAL_ANCHOR)
    budget = build_fact(
        BUDGET_MONTHS[BUDGET_MONTHS.year < 2026],
        budget=True,
        anchors=BUDGET_ANCHOR,
    )

    actual_2025 = float(actuals.loc[pd.to_datetime(actuals["Date"]).dt.year == 2025, "Revenue"].sum())
    budget_2026_anchor = {2026: actual_2025 * (1.0 + BUDGET_2026_GROWTH)}
    budget_2026 = build_fact(
        pd.date_range("2026-01-01", "2026-12-01", freq="MS"),
        budget=True,
        anchors=budget_2026_anchor,
    )
    budget = pd.concat([budget, budget_2026], ignore_index=True)
    budget.insert(5, "Scenario", "Budget")
    budget = budget.drop(columns=["VolumeUnits"])

    accounting_ok(actuals)
    accounting_ok(budget)

    actual_stmt = annual_statement(actuals)
    budget_stmt = annual_statement(budget)

    # Narrative guards. These are the claims the README is allowed to make.
    # If a future edit breaks the story, fail here rather than publish a
    # dashboard that contradicts itself.
    revenue = actual_stmt["Revenue"]
    if not (revenue[2025] > revenue[2024] > revenue[2023] > revenue[2022]):
        raise SystemExit("Revenue is not growing every year")
    gm = actual_stmt["GrossMargin"]
    if not (gm[2025] > gm[2024] > gm[2023] > gm[2022]):
        raise SystemExit("Gross margin is not expanding every year")
    if not (0.36 <= gm[2022] <= 0.43 and 0.43 <= gm[2025] <= 0.50):
        raise SystemExit(f"Gross margin out of expected band: {gm[2022]:.3%} -> {gm[2025]:.3%}")
    em = actual_stmt["EbitdaMargin"]
    if not (em[2025] > em[2022] + 0.035):
        raise SystemExit("EBITDA margin did not expand by at least 350 bps")
    if not (0.08 <= em[2022] <= 0.15 and 0.155 <= em[2025] <= 0.205):
        raise SystemExit(f"EBITDA margin out of expected band: {em[2022]:.3%} -> {em[2025]:.3%}")

    def var_pct(year: int) -> float:
        return revenue[year] / budget_stmt.loc[year, "Revenue"] - 1.0

    if not (revenue[2022] < budget_stmt.loc[2022, "Revenue"]):
        raise SystemExit("FY2022 should miss the revenue budget (supply chain)")
    if not (revenue[2024] > budget_stmt.loc[2024, "Revenue"]):
        raise SystemExit("FY2024 should beat the revenue budget (software)")
    if not (-0.045 <= var_pct(2025) <= -0.005):
        raise SystemExit(f"FY2025 revenue variance {var_pct(2025):.2%} is outside a modest miss")
    if not (actual_stmt.loc[2025, "EBITDA"] > budget_stmt.loc[2025, "EBITDA"]):
        raise SystemExit("FY2025 EBITDA should beat budget despite the revenue miss")

    actual_work = actuals.copy()
    actual_work["Year"] = pd.to_datetime(actual_work["Date"]).dt.year
    product_codes = {row["ProductLineKey"]: row["ProductCode"] for row in PRODUCTS}
    region_codes = {row["RegionKey"]: row["RegionCode"] for row in REGIONS}
    actual_work["ProductCode"] = actual_work["ProductLineKey"].map(product_codes)
    actual_work["RegionCode"] = actual_work["RegionKey"].map(region_codes)

    def share(year: int, column: str, code: str) -> float:
        year_rows = actual_work[actual_work["Year"] == year]
        return float(year_rows.loc[year_rows[column] == code, "Revenue"].sum() / year_rows["Revenue"].sum())

    if not (share(2025, "ProductCode", "SW") > share(2022, "ProductCode", "SW") + 0.06):
        raise SystemExit("Software mix did not expand enough to carry the margin story")
    if not (share(2025, "RegionCode", "APAC") > share(2022, "RegionCode", "APAC") + 0.04):
        raise SystemExit("Asia Pacific mix did not expand enough")

    # Referential integrity against the date dimension's month starts.
    month_starts = set(dim_date.loc[dim_date["IsMonthStart"], "DateKey"])
    for name, frame in ("actuals", actuals), ("budget", budget):
        missing = set(frame["DateKey"]) - month_starts
        if missing:
            raise SystemExit(f"{name} has DateKeys that are not month starts: {sorted(missing)[:3]}")

    write_csv(dim_date, "dim_date.csv")
    write_csv(dim_region, "dim_region.csv")
    write_csv(dim_product, "dim_product_line.csv")
    write_csv(dim_segment, "dim_customer_segment.csv")
    write_csv(actuals, "fact_revenue_actuals.csv")
    write_csv(budget, "fact_budget_forecast.csv")

    print("Vantage Process Group — synthetic annual statements (USD)")
    print("\nActuals")
    _print_statement(actual_stmt)
    print("\nBudget")
    _print_statement(budget_stmt)
    print("\nRevenue vs budget")
    for year in (2022, 2023, 2024, 2025, 2026):
        if year not in revenue.index and year != 2026:
            continue
        actual = revenue[year] if year in revenue.index else float("nan")
        plan = budget_stmt.loc[year, "Revenue"]
        if year == 2026:
            print(f"  FY{year}  budget {plan/1e6:8.2f}M   (no actuals)")
        else:
            print(f"  FY{year}  actual {actual/1e6:8.2f}M  budget {plan/1e6:8.2f}M  var {actual/plan-1:7.2%}")
    print("\nFY2025 EBITDA vs budget")
    print(
        f"  actual {actual_stmt.loc[2025, 'EBITDA']/1e6:.2f}M"
        f"  budget {budget_stmt.loc[2025, 'EBITDA']/1e6:.2f}M"
        f"  var {actual_stmt.loc[2025, 'EBITDA']/budget_stmt.loc[2025, 'EBITDA']-1:.2%}"
    )
    print("\nMix, software and APAC")
    print(f"  software {share(2022, 'ProductCode', 'SW'):.1%} -> {share(2025, 'ProductCode', 'SW'):.1%}")
    print(f"  APAC     {share(2022, 'RegionCode', 'APAC'):.1%} -> {share(2025, 'RegionCode', 'APAC'):.1%}")
    print(f"\nRows  actuals {len(actuals):,}   budget {len(budget):,}   dates {len(dim_date):,}")
    print(f"FY2026 budget anchor {budget_2026_anchor[2026]/1e6:.2f}M ({BUDGET_2026_GROWTH:.1%} on FY2025 actual)")


def _print_statement(statement: pd.DataFrame) -> None:
    for year, row in statement.iterrows():
        print(
            f"  FY{year}  rev {row['Revenue']/1e6:8.2f}M"
            f"  GM {row['GrossMargin']:6.1%}"
            f"  opex {row['OpEx']/1e6:7.2f}M"
            f"  EBITDA {row['EBITDA']/1e6:7.2f}M"
            f"  {row['EbitdaMargin']:6.1%}"
        )


if __name__ == "__main__":
    main()
