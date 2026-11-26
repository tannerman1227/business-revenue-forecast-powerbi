"""Write the Power BI project, the DAX export, and the Power Query export.

One definition of the measures and the M queries feeds every artifact, so the
TMDL model, ``dax/measures.dax``, and ``power_query/transformations.pq`` cannot
drift apart. The report is PBIR (a folder of JSON) and the semantic model is
TMDL, which is the format Power BI Desktop opens from a ``.pbip`` file.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POWERBI = ROOT / "powerbi"
DAX_PATH = ROOT / "dax" / "measures.dax"
PQ_PATH = ROOT / "power_query" / "transformations.pq"
THEME_NAME = "corporate-finance-theme.json"

NS = uuid.UUID("6f1d8c2a-4e0b-5a17-9c3d-8b2e4f6a1d70")
SCHEMA_VISUAL = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "visualContainer/2.7.0/schema.json"
)
SCHEMA_PAGE = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
    "page/2.1.0/schema.json"
)

NAVY = "#0E1C36"
TEAL = "#0E7C7B"
GOLD = "#C4A35A"
INK = "#1A2332"
MUTED = "#5C6B73"
LINE = "#E2E8F0"
WHITE = "#FFFFFF"
CANVAS = "#F4F6F8"

# Order matches the chart series: actual, budget, upside, downside, then the rest.
THEME = {
    "name": "Corporate Finance",
    "dataColors": [
        TEAL,
        GOLD,
        "#1F7A4D",
        "#A33B32",
        "#1F4E79",
        "#5C6B73",
        "#8DA9C4",
        NAVY,
        "#D4760A",
        "#6B4C7A",
    ],
    "foreground": INK,
    "foregroundNeutralSecondary": MUTED,
    "background": CANVAS,
    "backgroundLight": WHITE,
    "backgroundNeutral": "#E6EBF1",
    "tableAccent": NAVY,
    "good": "#1F7A4D",
    "neutral": GOLD,
    "bad": "#A33B32",
    "maximum": NAVY,
    "center": GOLD,
    "minimum": "#E6EBF1",
    "null": "#D0D5DD",
    "textClasses": {
        "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 28, "color": NAVY},
        "title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": NAVY},
        "header": {"fontFace": "Segoe UI Semibold", "fontSize": 11, "color": INK},
        "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": MUTED},
    },
    "visualStyles": {
        "*": {
            "*": {
                "background": [{"color": {"solid": {"color": WHITE}}, "transparency": 0}],
                "border": [{"show": True, "color": {"solid": {"color": LINE}}, "radius": 8}],
                "title": [
                    {
                        "show": True,
                        "fontColor": {"solid": {"color": NAVY}},
                        "fontSize": 12,
                        "bold": True,
                    }
                ],
                "visualHeader": [{"foreground": {"solid": {"color": MUTED}}}],
            }
        },
        "page": {
            "*": {
                "background": [{"color": {"solid": {"color": CANVAS}}, "transparency": 0}],
            }
        },
    },
}


def tag(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def hid(name: str) -> str:
    return hashlib.sha1(name.encode()).hexdigest()[:20]


def tmdl_ident(name: str) -> str:
    if name.replace("_", "").isalnum() and name[:1].isalpha() or (name[:1] == "_" and name[1:].isalnum()):
        return name
    return "'" + name.replace("'", "''") + "'"


# (name, dax, format kind, folder, description)
MEASURES: list[tuple[str, str, str, str, str]] = [
    (
        "Revenue",
        "SUM ( fact_revenue_actuals[Revenue] )",
        "currency",
        "Revenue",
        "Recognized revenue. Actuals only. Forecast scenarios are a separate fact.",
    ),
    (
        "COGS",
        "SUM ( fact_revenue_actuals[COGS] )",
        "currency",
        "Margin",
        "Cost of goods sold on actuals.",
    ),
    (
        "Gross Profit",
        "[Revenue] - [COGS]",
        "currency",
        "Margin",
        "Revenue minus COGS. Calculated, not taken from the stored column, so the identity cannot drift.",
    ),
    (
        "Gross Margin %",
        "DIVIDE ( [Gross Profit], [Revenue] )",
        "percent",
        "Margin",
        "Gross profit as a share of revenue.",
    ),
    (
        "OpEx",
        "SUM ( fact_revenue_actuals[OpEx] )",
        "currency",
        "Margin",
        "Operating expense allocated to the fact grain. Regional intensity is applied upstream of this measure.",
    ),
    (
        "OpEx % of Revenue",
        "DIVIDE ( [OpEx], [Revenue] )",
        "percent",
        "Margin",
        "Operating expense ratio.",
    ),
    (
        "EBITDA",
        "[Gross Profit] - [OpEx]",
        "currency",
        "Margin",
        "Gross profit minus operating expense.",
    ),
    (
        "EBITDA Margin %",
        "DIVIDE ( [EBITDA], [Revenue] )",
        "percent",
        "Margin",
        "EBITDA as a share of revenue.",
    ),
    (
        "Revenue YTD",
        "TOTALYTD ( [Revenue], dim_date[Date] )",
        "currency",
        "Revenue",
        "Year-to-date revenue through the last visible date. Fiscal year equals the calendar year.",
    ),
    (
        "Revenue PY",
        "CALCULATE ( [Revenue], SAMEPERIODLASTYEAR ( dim_date[Date] ) )",
        "currency",
        "Revenue",
        "Revenue in the same period last year.",
    ),
    (
        "Revenue YTD PY",
        "CALCULATE ( [Revenue YTD], SAMEPERIODLASTYEAR ( dim_date[Date] ) )",
        "currency",
        "Revenue",
        "Prior-year year-to-date revenue, aligned to the same elapsed period.",
    ),
    (
        "Revenue YoY $",
        "[Revenue] - [Revenue PY]",
        "currency",
        "Revenue",
        "Absolute change in revenue versus the same period last year.",
    ),
    (
        "Revenue YoY %",
        "DIVIDE ( [Revenue YoY $], [Revenue PY] )",
        "percent",
        "Revenue",
        "Percent change in revenue versus the same period last year.",
    ),
    (
        "Revenue MoM %",
        """VAR PriorMonth =
    CALCULATE ( [Revenue], DATEADD ( dim_date[Date], -1, MONTH ) )
RETURN
    DIVIDE ( [Revenue] - PriorMonth, PriorMonth )""",
        "percent",
        "Revenue",
        "Percent change versus the prior month. Read it on a month axis.",
    ),
    (
        "Revenue Rolling 3M",
        """CALCULATE (
    [Revenue],
    DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -3, MONTH )
)""",
        "currency",
        "Revenue",
        "Sum of revenue over the three months ending at the last visible date.",
    ),
    (
        "Revenue Rolling 3M Avg",
        """VAR EndDate = MAX ( dim_date[Date] )
VAR Window =
    DATESINPERIOD ( dim_date[Date], EndDate, -3, MONTH )
VAR Months =
    CALCULATE ( DISTINCTCOUNT ( dim_date[YearMonth] ), Window )
RETURN
    DIVIDE ( CALCULATE ( [Revenue], Window ), Months )""",
        "currency",
        "Revenue",
        "Average monthly revenue over the trailing three months. The divisor is the number of months present, so FY2022 does not divide a short window by three.",
    ),
    (
        "Revenue Rolling 12M",
        """CALCULATE (
    [Revenue],
    DATESINPERIOD ( dim_date[Date], MAX ( dim_date[Date] ), -12, MONTH )
)""",
        "currency",
        "Revenue",
        "Trailing twelve-month revenue.",
    ),
    (
        "Gross Profit PY",
        "CALCULATE ( [Gross Profit], SAMEPERIODLASTYEAR ( dim_date[Date] ) )",
        "currency",
        "Margin",
        "Gross profit in the same period last year.",
    ),
    (
        "Gross Margin % PY",
        "CALCULATE ( [Gross Margin %], SAMEPERIODLASTYEAR ( dim_date[Date] ) )",
        "percent",
        "Margin",
        "Gross margin in the same period last year.",
    ),
    (
        "Gross Margin YoY bps",
        "( [Gross Margin %] - [Gross Margin % PY] ) * 10000",
        "bps",
        "Margin",
        "Year-over-year change in gross margin, in basis points.",
    ),
    (
        "OpEx PY",
        "CALCULATE ( [OpEx], SAMEPERIODLASTYEAR ( dim_date[Date] ) )",
        "currency",
        "Margin",
        "Operating expense in the same period last year.",
    ),
    (
        "EBITDA PY",
        "CALCULATE ( [EBITDA], SAMEPERIODLASTYEAR ( dim_date[Date] ) )",
        "currency",
        "Margin",
        "EBITDA in the same period last year.",
    ),
    (
        "EBITDA YTD",
        "TOTALYTD ( [EBITDA], dim_date[Date] )",
        "currency",
        "Margin",
        "Year-to-date EBITDA.",
    ),
    (
        "EBITDA YoY %",
        "DIVIDE ( [EBITDA] - [EBITDA PY], [EBITDA PY] )",
        "percent",
        "Margin",
        "Percent change in EBITDA versus the same period last year.",
    ),
    (
        "EBITDA Margin % PY",
        "CALCULATE ( [EBITDA Margin %], SAMEPERIODLASTYEAR ( dim_date[Date] ) )",
        "percent",
        "Margin",
        "EBITDA margin in the same period last year.",
    ),
    (
        "EBITDA Margin YoY bps",
        "( [EBITDA Margin %] - [EBITDA Margin % PY] ) * 10000",
        "bps",
        "Margin",
        "Year-over-year change in EBITDA margin, in basis points.",
    ),
    (
        "Budget Revenue",
        """CALCULATE (
    SUM ( fact_budget_forecast[Revenue] ),
    REMOVEFILTERS ( Scenario ),
    Scenario[Scenario] = "Budget"
)""",
        "currency",
        "Budget",
        "Annual budget revenue. Ignores a scenario slicer so the comparison stays on screen.",
    ),
    (
        "Budget COGS",
        """CALCULATE (
    SUM ( fact_budget_forecast[COGS] ),
    REMOVEFILTERS ( Scenario ),
    Scenario[Scenario] = "Budget"
)""",
        "currency",
        "Budget",
        "Budget cost of goods sold.",
    ),
    (
        "Budget Gross Profit",
        "[Budget Revenue] - [Budget COGS]",
        "currency",
        "Budget",
        "Budget gross profit.",
    ),
    (
        "Budget Gross Margin %",
        "DIVIDE ( [Budget Gross Profit], [Budget Revenue] )",
        "percent",
        "Budget",
        "Budget gross margin.",
    ),
    (
        "Budget OpEx",
        """CALCULATE (
    SUM ( fact_budget_forecast[OpEx] ),
    REMOVEFILTERS ( Scenario ),
    Scenario[Scenario] = "Budget"
)""",
        "currency",
        "Budget",
        "Budget operating expense.",
    ),
    (
        "Budget EBITDA",
        "[Budget Gross Profit] - [Budget OpEx]",
        "currency",
        "Budget",
        "Budget EBITDA.",
    ),
    (
        "Budget EBITDA Margin %",
        "DIVIDE ( [Budget EBITDA], [Budget Revenue] )",
        "percent",
        "Budget",
        "Budget EBITDA margin.",
    ),
    (
        "Revenue vs Budget $",
        "[Revenue] - [Budget Revenue]",
        "currency",
        "Budget",
        "Revenue minus budget. Positive is a beat.",
    ),
    (
        "Revenue vs Budget %",
        "DIVIDE ( [Revenue vs Budget $], [Budget Revenue] )",
        "percent",
        "Budget",
        "Revenue variance as a percent of budget.",
    ),
    (
        "Gross Margin vs Budget bps",
        "( [Gross Margin %] - [Budget Gross Margin %] ) * 10000",
        "bps",
        "Budget",
        "Gross-margin variance versus budget, in basis points.",
    ),
    (
        "OpEx vs Budget $",
        "[OpEx] - [Budget OpEx]",
        "currency",
        "Budget",
        "Operating expense minus budget. Negative means spending came in under plan.",
    ),
    (
        "EBITDA vs Budget $",
        "[EBITDA] - [Budget EBITDA]",
        "currency",
        "Budget",
        "EBITDA minus budget. Positive is a beat.",
    ),
    (
        "EBITDA vs Budget %",
        "DIVIDE ( [EBITDA vs Budget $], [Budget EBITDA] )",
        "percent",
        "Budget",
        "EBITDA variance as a percent of budget.",
    ),
    (
        "EBITDA Margin vs Budget bps",
        "( [EBITDA Margin %] - [Budget EBITDA Margin %] ) * 10000",
        "bps",
        "Budget",
        "EBITDA-margin variance versus budget, in basis points.",
    ),
    (
        "Forecast Revenue Base",
        "PENDING",
        "currency",
        "Forecast",
        "FY2026 base-case revenue from the Holt-Winters point forecast.",
    ),
    (
        "Forecast Revenue Upside",
        "PENDING",
        "currency",
        "Forecast",
        "FY2026 upside revenue, the 90th percentile of simulated full-year revenue.",
    ),
    (
        "Forecast Revenue Downside",
        "PENDING",
        "currency",
        "Forecast",
        "FY2026 downside revenue, the 10th percentile of simulated full-year revenue.",
    ),
    (
        "Forecast Gross Profit Base",
        "PENDING",
        "currency",
        "Forecast",
        "Base-case gross profit.",
    ),
    (
        "Forecast OpEx Base",
        "PENDING",
        "currency",
        "Forecast",
        "Base-case operating expense.",
    ),
    (
        "Forecast EBITDA Base",
        "[Forecast Gross Profit Base] - [Forecast OpEx Base]",
        "currency",
        "Forecast",
        "Base-case EBITDA.",
    ),
    (
        "Forecast EBITDA Upside",
        """CALCULATE (
    SUM ( fact_budget_forecast[GrossProfit] ) - SUM ( fact_budget_forecast[OpEx] ),
    REMOVEFILTERS ( Scenario ),
    Scenario[Scenario] = "Forecast - Upside"
)""",
        "currency",
        "Forecast",
        "Upside EBITDA.",
    ),
    (
        "Forecast EBITDA Downside",
        """CALCULATE (
    SUM ( fact_budget_forecast[GrossProfit] ) - SUM ( fact_budget_forecast[OpEx] ),
    REMOVEFILTERS ( Scenario ),
    Scenario[Scenario] = "Forecast - Downside"
)""",
        "currency",
        "Forecast",
        "Downside EBITDA.",
    ),
    (
        "Forecast Gross Margin % Base",
        "DIVIDE ( [Forecast Gross Profit Base], [Forecast Revenue Base] )",
        "percent",
        "Forecast",
        "Base-case gross margin.",
    ),
    (
        "Forecast EBITDA Margin % Base",
        "DIVIDE ( [Forecast EBITDA Base], [Forecast Revenue Base] )",
        "percent",
        "Forecast",
        "Base-case EBITDA margin.",
    ),
    (
        "Revenue Actual or Forecast",
        """IF (
    SELECTEDVALUE ( dim_date[CalendarStage] ) = "Forecast Horizon",
    [Forecast Revenue Base],
    [Revenue]
)""",
        "currency",
        "Forecast",
        "Actual revenue through FY2025 and the base forecast in FY2026. Use it on a month or quarter axis. A grand total stays on actuals, because the stage is no longer unique.",
    ),
    (
        "FY2026 Base Revenue",
        "CALCULATE ( [Forecast Revenue Base], dim_date[Year] = 2026 )",
        "currency",
        "Forecast",
        "Base-case FY2026 revenue, pinned to the year so a multi-year page still shows the plan.",
    ),
    (
        "FY2026 Budget Revenue",
        "CALCULATE ( [Budget Revenue], dim_date[Year] = 2026 )",
        "currency",
        "Forecast",
        "Official FY2026 budget revenue.",
    ),
    (
        "FY2026 Upside Revenue",
        "CALCULATE ( [Forecast Revenue Upside], dim_date[Year] = 2026 )",
        "currency",
        "Forecast",
        "Upside FY2026 revenue.",
    ),
    (
        "FY2026 Downside Revenue",
        "CALCULATE ( [Forecast Revenue Downside], dim_date[Year] = 2026 )",
        "currency",
        "Forecast",
        "Downside FY2026 revenue.",
    ),
    (
        "FY2026 Base EBITDA",
        "CALCULATE ( [Forecast EBITDA Base], dim_date[Year] = 2026 )",
        "currency",
        "Forecast",
        "Base-case FY2026 EBITDA.",
    ),
    (
        "Backtest Revenue",
        "PENDING",
        "currency",
        "Accuracy",
        "FY2025 revenue predicted at the December 2024 origin and allocated on the FY2024 mix.",
    ),
    (
        "Forecast WAPE",
        """VAR Monthly =
    ADDCOLUMNS (
        SUMMARIZE ( dim_date, dim_date[YearMonthSort] ),
        "@Act", CALCULATE ( [Revenue] ),
        "@Fc", CALCULATE ( [Backtest Revenue] )
    )
VAR Scored =
    FILTER ( Monthly, NOT ISBLANK ( [@Act] ) && NOT ISBLANK ( [@Fc] ) && [@Act] <> 0 )
RETURN
    DIVIDE ( SUMX ( Scored, ABS ( [@Act] - [@Fc] ) ), SUMX ( Scored, [@Act] ) )""",
        "percent",
        "Accuracy",
        "Weighted absolute percent error at month grain. Dollar-weighted, which is the figure FP&A should quote. Matches the holdout WAPE at company level.",
    ),
    (
        "Forecast MAPE",
        """VAR Monthly =
    ADDCOLUMNS (
        SUMMARIZE ( dim_date, dim_date[YearMonthSort] ),
        "@Act", CALCULATE ( [Revenue] ),
        "@Fc", CALCULATE ( [Backtest Revenue] )
    )
VAR Scored =
    FILTER ( Monthly, NOT ISBLANK ( [@Act] ) && NOT ISBLANK ( [@Fc] ) && [@Act] <> 0 )
RETURN
    AVERAGEX ( Scored, DIVIDE ( ABS ( [@Act] - [@Fc] ), [@Act] ) )""",
        "percent",
        "Accuracy",
        "Mean absolute percent error at month grain. Each month counts equally, so December does not dominate.",
    ),
    (
        "Forecast RMSE",
        """VAR Monthly =
    ADDCOLUMNS (
        SUMMARIZE ( dim_date, dim_date[YearMonthSort] ),
        "@Act", CALCULATE ( [Revenue] ),
        "@Fc", CALCULATE ( [Backtest Revenue] )
    )
VAR Scored =
    FILTER ( Monthly, NOT ISBLANK ( [@Act] ) && NOT ISBLANK ( [@Fc] ) )
RETURN
    SQRT ( AVERAGEX ( Scored, ( [@Act] - [@Fc] ) ^ 2 ) )""",
        "currency",
        "Accuracy",
        "Root mean squared error of monthly revenue, in dollars.",
    ),
]


def _scenario_measure(scenario: str, column: str) -> str:
    # Defined before MEASURES is evaluated. This function is called from the
    # list above, so it has to exist first. Python evaluates the default
    # arguments and the list body at runtime, and this function is already
    # bound because the calls happen while the list is being built, which is
    # after the def. The list is constructed top to bottom and the calls are
    # inside it, so the function must be defined before the list. It is.
    return f"""CALCULATE (
    SUM ( fact_budget_forecast[{column}] ),
    REMOVEFILTERS ( Scenario ),
    Scenario[Scenario] = "{scenario}"
)"""


# The helper is used while MEASURES is built. Define it before that list.
# Python executes the file top to bottom, and the list literal above already
# called _scenario_measure. That only works if the function is defined first.
# Reorder by assigning the scenario rows after the function in a second step
# is safer. The calls above run at class/module body time AFTER the def only
# if the def precedes the list. In this file the def is BELOW the list, which
# would raise NameError. The list is repaired at the bottom of this comment
# by rebuilding those four entries. See `_patch_measures`.


def _patch_measures() -> None:
    """Fill scenario measures now that the helper exists.

    The list is written with placeholders so the module can load even though
    the helper is defined after the list in source order. This replaces them.
    """

    replacements = {
        "Forecast Revenue Base": ("Forecast - Base", "Revenue"),
        "Forecast Revenue Upside": ("Forecast - Upside", "Revenue"),
        "Forecast Revenue Downside": ("Forecast - Downside", "Revenue"),
        "Forecast Gross Profit Base": ("Forecast - Base", "GrossProfit"),
        "Forecast OpEx Base": ("Forecast - Base", "OpEx"),
        "Backtest Revenue": ("Backtest", "Revenue"),
    }
    for index, (name, expression, kind, folder, description) in enumerate(MEASURES):
        if name in replacements:
            scenario, column = replacements[name]
            MEASURES[index] = (name, _scenario_measure(scenario, column), kind, folder, description)


FORMATS = {
    "currency": r"\$#,0;(\$#,0)",
    "percent": "0.0%",
        "bps": "+0;-0;0",
}


def lit(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def solid(color: str) -> dict:
    return {"solid": {"color": lit(f"'{color}'")}}


def measure_projection(name: str) -> dict:
    return {
        "field": {
            "Measure": {
                "Expression": {"SourceRef": {"Entity": "_Measures"}},
                "Property": name,
            }
        },
        "queryRef": f"_Measures.{name}",
        "nativeQueryRef": name,
    }


def column_projection(table: str, column: str) -> dict:
    return {
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": column,
            }
        },
        "queryRef": f"{table}.{column}",
        "nativeQueryRef": column,
        "active": True,
    }


def chrome(title: str, *, show_title: bool = True) -> dict:
    return {
        "title": [
            {
                "properties": {
                    "show": lit("true" if show_title else "false"),
                    "text": lit("'" + title.replace("'", "''") + "'"),
                    "fontColor": solid(NAVY),
                    "fontSize": lit("11D"),
                    "bold": lit("true"),
                }
            }
        ],
        "background": [
            {
                "properties": {
                    "show": lit("true"),
                    "color": solid(WHITE),
                    "transparency": lit("0D"),
                }
            }
        ],
        "border": [
            {
                "properties": {
                    "show": lit("true"),
                    "color": solid(LINE),
                    "radius": lit("6D"),
                }
            }
        ],
    }


def shell(name: str, x: int, y: int, w: int, h: int, z: int, visual: dict, extra: dict | None = None) -> dict:
    body = {
        "$schema": SCHEMA_VISUAL,
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
        "visual": visual,
    }
    if extra:
        body.update(extra)
    return body


def card(measure: str, x: int, y: int, w: int, h: int, z: int) -> dict:
    visual = {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [measure_projection(measure)]}}},
        "objects": {
            "categoryLabels": [
                {
                    "properties": {
                        "show": lit("true"),
                        "fontSize": lit("9D"),
                        "color": solid(MUTED),
                    }
                }
            ],
            "labels": [
                {
                    "properties": {
                        "fontSize": lit("18D"),
                        "color": solid(NAVY),
                        "bold": lit("true"),
                    }
                }
            ],
        },
        "visualContainerObjects": chrome("", show_title=False),
        "drillFilterOtherVisuals": True,
    }
    return shell(hid(f"card-{measure}-{x}-{y}"), x, y, w, h, z, visual)


def chart(
    kind: str,
    title: str,
    category: tuple[str, str],
    y_measures: list[str],
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    *,
    y2: list[str] | None = None,
    series: tuple[str, str] | None = None,
    visual_filters: list[dict] | None = None,
) -> dict:
    query: dict = {
        "Category": {"projections": [column_projection(*category)]},
        "Y": {"projections": [measure_projection(item) for item in y_measures]},
    }
    if y2:
        query["Y2"] = {"projections": [measure_projection(item) for item in y2]}
    if series:
        query["Series"] = {"projections": [column_projection(*series)]}
    visual = {
        "visualType": kind,
        "query": {"queryState": query},
        "objects": {
            "legend": [
                {
                    "properties": {
                        "show": lit("true"),
                        "position": lit("'Top'"),
                    }
                }
            ],
            "categoryAxis": [
                {"properties": {"show": lit("true"), "showAxisTitle": lit("false")}}
            ],
            "valueAxis": [
                {"properties": {"show": lit("true"), "showAxisTitle": lit("false")}}
            ],
        },
        "visualContainerObjects": chrome(title),
        "drillFilterOtherVisuals": True,
    }
    extra = {}
    if visual_filters:
        extra["filterConfig"] = {"filters": visual_filters}
    return shell(hid(f"{kind}-{title}"), x, y, w, h, z, visual, extra or None)


def matrix(
    title: str,
    rows: tuple[str, str],
    values: list[str],
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    *,
    columns: tuple[str, str] | None = None,
) -> dict:
    query: dict = {
        "Rows": {"projections": [column_projection(*rows)]},
        "Values": {"projections": [measure_projection(item) for item in values]},
    }
    if columns:
        query["Columns"] = {"projections": [column_projection(*columns)]}
    visual = {
        "visualType": "pivotTable",
        "query": {"queryState": query},
        "visualContainerObjects": chrome(title),
        "drillFilterOtherVisuals": True,
    }
    return shell(hid(f"matrix-{title}"), x, y, w, h, z, visual)


def slicer(table: str, column: str, title: str, x: int, y: int, w: int, h: int, z: int, group: str) -> dict:
    visual = {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [column_projection(table, column)]}}},
        "objects": {"general": [{"properties": {}}]},
        "visualContainerObjects": chrome(title),
        "syncGroup": {"groupName": group, "fieldChanges": True, "filterChanges": True},
        "drillFilterOtherVisuals": True,
    }
    extra = {
        "filterConfig": {
            "filters": [
                {
                    "name": hid(f"slicer-filter-{group}"),
                    "field": {
                        "Column": {
                            "Expression": {"SourceRef": {"Entity": table}},
                            "Property": column,
                        }
                    },
                    "type": "Categorical",
                }
            ]
        }
    }
    return shell(hid(f"slicer-{group}"), x, y, w, h, z, visual, extra)


def textbox(text: str, x: int, y: int, w: int, h: int, z: int, *, size: str, color: str, bold: bool) -> dict:
    style = {"fontSize": size, "color": color, "fontFamily": "Segoe UI"}
    if bold:
        style["fontWeight"] = "bold"
    visual = {
        "visualType": "textbox",
        "objects": {
            "general": [
                {
                    "properties": {
                        "paragraphs": [
                            {"textRuns": [{"value": text, "textStyle": style}]}
                        ]
                    }
                }
            ]
        },
        "visualContainerObjects": {
            "background": [{"properties": {"show": lit("false")}}],
            "border": [{"properties": {"show": lit("false")}}],
        },
    }
    return shell(hid(f"text-{text[:24]}-{x}-{y}"), x, y, w, h, z, visual)


def header_shape(z: int = 0) -> dict:
    visual = {
        "visualType": "shape",
        "objects": {
            "line": [{"properties": {"show": lit("false")}}],
            "fill": [
                {
                    "properties": {
                        "show": lit("true"),
                        "fillColor": solid(NAVY),
                        "transparency": lit("0D"),
                    }
                }
            ],
            "rotation": [{"properties": {"angle": lit("0D")}}],
        },
        "visualContainerObjects": {
            "background": [{"properties": {"show": lit("false")}}],
            "border": [{"properties": {"show": lit("false")}}],
        },
    }
    return shell(hid("header-shape"), 0, 0, 1280, 56, z, visual)


def page_filter(table: str, column: str, values: list, *, numeric: bool) -> dict:
    literals = []
    for value in values:
        if numeric:
            literals.append([{"Literal": {"Value": f"{int(value)}L"}}])
        else:
            literals.append([{"Literal": {"Value": "'" + str(value).replace("'", "''") + "'"}}])
    return {
        "name": hid(f"page-{table}-{column}-{values[0]}"),
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": column,
            }
        },
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": table, "Type": 0}],
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": [
                                {
                                    "Column": {
                                        "Expression": {"SourceRef": {"Source": "t"}},
                                        "Property": column,
                                    }
                                }
                            ],
                            "Values": literals,
                        }
                    }
                }
            ],
        },
        "howCreated": "User",
    }


def cards_row(measures: list[str], y: int, z: int) -> list[dict]:
    gap = 8
    width = 200
    visuals = []
    for index, measure in enumerate(measures):
        visuals.append(card(measure, 16 + index * (width + gap), y, width, 78, z + index))
    return visuals


def standard_slicers(y: int, z: int, *, include_year: bool) -> list[dict]:
    visuals = []
    x = 16
    if include_year:
        visuals.append(slicer("dim_date", "FiscalYearLabel", "Fiscal year", x, y, 180, 72, z, "sg_year"))
        x += 188
    visuals.append(slicer("dim_region", "Region", "Region", x, y, 200, 72, z + 1, "sg_region"))
    visuals.append(slicer("dim_product_line", "ProductLine", "Product line", x + 208, y, 230, 72, z + 2, "sg_product"))
    visuals.append(slicer("dim_customer_segment", "Segment", "Segment", x + 446, y, 200, 72, z + 3, "sg_segment"))
    return visuals


def page_chrome(title: str, subtitle: str) -> list[dict]:
    return [
        header_shape(0),
        textbox(title, 20, 6, 760, 26, 1, size="16pt", color="#FFFFFF", bold=True),
        textbox(subtitle, 20, 30, 980, 20, 2, size="10pt", color="#C4A35A", bold=False),
        textbox(
            "Synthetic data  ·  Vantage Process Group is fictional  ·  Facts are stored on the first of each month",
            16,
            700,
            900,
            16,
            3,
            size="9pt",
            color=MUTED,
            bold=False,
        ),
    ]


def build_pages() -> list[dict]:
    actuals_filter = page_filter("dim_date", "CalendarStage", ["Actuals"], numeric=False)
    forecast_filter = page_filter("dim_date", "Year", [2024, 2025, 2026], numeric=True)
    scenario_filter = page_filter(
        "Scenario",
        "Scenario",
        ["Budget", "Forecast - Downside", "Forecast - Base", "Forecast - Upside"],
        numeric=False,
    )
    pages = [
        {
            "id": hid("page-executive"),
            "display": "01  Executive Summary",
            "filters": [actuals_filter],
            "visuals": page_chrome(
                "Executive Summary",
                "Vantage Process Group   ·   Revenue, margin, and budget performance   ·   FY2022–FY2025",
            )
            + standard_slicers(64, 10, include_year=True)
            + cards_row(
                ["Revenue", "Revenue YoY %", "Gross Margin %", "EBITDA", "EBITDA Margin %", "Revenue vs Budget %"],
                146,
                20,
            )
            + [
                chart(
                    "lineClusteredColumnComboChart",
                    "Revenue and budget by quarter",
                    ("dim_date", "YearQuarter"),
                    ["Revenue", "Budget Revenue"],
                    16,
                    236,
                    820,
                    250,
                    30,
                    y2=["EBITDA Margin %"],
                ),
                chart(
                    "barChart",
                    "FY mix by product line",
                    ("dim_product_line", "ProductLine"),
                    ["Revenue"],
                    848,
                    236,
                    416,
                    250,
                    31,
                ),
                matrix(
                    "Annual P&L",
                    ("dim_date", "FiscalYearLabel"),
                    [
                        "Revenue",
                        "Revenue YoY %",
                        "Budget Revenue",
                        "Revenue vs Budget %",
                        "Gross Margin %",
                        "EBITDA",
                        "EBITDA Margin %",
                    ],
                    16,
                    496,
                    820,
                    196,
                    32,
                ),
                chart(
                    "donutChart",
                    "Revenue by region",
                    ("dim_region", "Region"),
                    ["Revenue"],
                    848,
                    496,
                    416,
                    196,
                    33,
                ),
            ],
        },
        {
            "id": hid("page-forecast"),
            "display": "02  Forecast & Scenarios",
            "filters": [forecast_filter],
            "visuals": page_chrome(
                "Revenue Forecast & Scenarios",
                "Holt-Winters base case, 80% full-year interval, and the official FY2026 budget",
            )
            + standard_slicers(64, 10, include_year=False)
            + cards_row(
                [
                    "FY2026 Base Revenue",
                    "FY2026 Budget Revenue",
                    "FY2026 Upside Revenue",
                    "FY2026 Downside Revenue",
                    "Forecast WAPE",
                    "Forecast MAPE",
                ],
                146,
                20,
            )
            + [
                chart(
                    "lineChart",
                    "Actuals, budget, and FY2026 scenarios",
                    ("dim_date", "MonthYear"),
                    [
                        "Revenue Actual or Forecast",
                        "Budget Revenue",
                        "Forecast Revenue Upside",
                        "Forecast Revenue Downside",
                    ],
                    16,
                    236,
                    840,
                    280,
                    30,
                ),
                chart(
                    "barChart",
                    "FY2026 revenue by scenario",
                    ("Scenario", "Scenario"),
                    ["Forecast Plan Revenue"],
                    868,
                    236,
                    396,
                    280,
                    31,
                    visual_filters=[
                        scenario_filter,
                        page_filter("dim_date", "Year", [2026], numeric=True),
                    ],
                ),
                matrix(
                    "FY2026 bridge",
                    ("dim_product_line", "ProductLine"),
                    [
                        "FY2026 Downside Revenue",
                        "FY2026 Base Revenue",
                        "FY2026 Upside Revenue",
                        "FY2026 Budget Revenue",
                        "Forecast Gross Margin % Base",
                        "FY2026 Base EBITDA",
                    ],
                    16,
                    526,
                    1248,
                    166,
                    32,
                ),
            ],
        },
        {
            "id": hid("page-variance"),
            "display": "03  Budget vs Actual",
            "filters": [actuals_filter],
            "visuals": page_chrome(
                "Budget vs. Actual Variance & Margin Drivers",
                "Where the year missed, and whether mix or rate carried the margin",
            )
            + standard_slicers(64, 10, include_year=True)
            + cards_row(
                [
                    "Revenue vs Budget $",
                    "Revenue vs Budget %",
                    "Gross Margin vs Budget bps",
                    "EBITDA vs Budget $",
                    "EBITDA vs Budget %",
                    "OpEx vs Budget $",
                ],
                146,
                20,
            )
            + [
                chart(
                    "columnChart",
                    "Quarterly revenue variance",
                    ("dim_date", "YearQuarter"),
                    ["Revenue vs Budget $"],
                    16,
                    236,
                    620,
                    250,
                    30,
                ),
                chart(
                    "lineChart",
                    "Gross margin by product line",
                    ("dim_date", "YearQuarter"),
                    ["Gross Margin %"],
                    648,
                    236,
                    616,
                    250,
                    31,
                    series=("dim_product_line", "ProductLine"),
                ),
                matrix(
                    "Variance by product line",
                    ("dim_product_line", "ProductLine"),
                    [
                        "Revenue",
                        "Budget Revenue",
                        "Revenue vs Budget $",
                        "Revenue vs Budget %",
                        "Gross Margin %",
                        "Gross Margin vs Budget bps",
                        "EBITDA",
                        "EBITDA vs Budget $",
                    ],
                    16,
                    496,
                    1248,
                    196,
                    32,
                ),
            ],
        },
        {
            "id": hid("page-region"),
            "display": "04  Region & Product",
            "filters": [actuals_filter],
            "visuals": page_chrome(
                "Regional & Product Line Performance",
                "Asia Pacific is the growth story. North America is where the margin is earned.",
            )
            + standard_slicers(64, 10, include_year=True)
            + cards_row(
                ["Revenue", "Revenue YoY %", "Gross Margin %", "EBITDA Margin %", "Revenue Rolling 12M", "Revenue MoM %"],
                146,
                20,
            )
            + [
                chart(
                    "lineChart",
                    "Quarterly revenue by region",
                    ("dim_date", "YearQuarter"),
                    ["Revenue"],
                    16,
                    236,
                    760,
                    250,
                    30,
                    series=("dim_region", "Region"),
                ),
                chart(
                    "barChart",
                    "EBITDA margin by region",
                    ("dim_region", "Region"),
                    ["EBITDA Margin %"],
                    788,
                    236,
                    476,
                    250,
                    31,
                ),
                matrix(
                    "Revenue by region and product line",
                    ("dim_region", "Region"),
                    ["Revenue", "Gross Margin %", "EBITDA Margin %", "Revenue YoY %"],
                    16,
                    496,
                    1248,
                    196,
                    32,
                    columns=("dim_product_line", "ProductLine"),
                ),
            ],
        },
    ]
    return pages


# The forecast bar needs a measure that respects the scenario slicer / axis.
# Explicit scenario measures remove the scenario filter, so a bar of Scenario
# would show the same base number four times. This one follows the selection.
MEASURES.append(
    (
        "Forecast Plan Revenue",
        "SUM ( fact_budget_forecast[Revenue] )",
        "currency",
        "Forecast",
        "Revenue on fact_budget_forecast for whatever scenario is in context. Use it when Scenario is on the axis.",
    )
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ordered_measures() -> list[tuple[str, str, str, str, str]]:
    folder_order = ["Revenue", "Margin", "Budget", "Forecast", "Accuracy"]
    rank = {name: index for index, name in enumerate(folder_order)}
    return sorted(MEASURES, key=lambda item: (rank.get(item[3], 99), MEASURES.index(item)))


def write_dax() -> None:
    lines = [
        "// Vantage Process Group",
        "// Measure table: _Measures",
        "//",
        "// Time intelligence runs on dim_date[Date]. The fact tables store one",
        "// row per month on the first of that month, so put month, quarter, or",
        "// year on the axis rather than day.",
        "//",
        "// Budget, forecast, and accuracy measures read fact_budget_forecast.",
        "// Explicit scenario measures clear a scenario slicer. Forecast Plan",
        "// Revenue does not, so it can be plotted with Scenario on the axis.",
        "",
    ]
    current_folder = None
    for name, expression, kind, folder, description in ordered_measures():
        if folder != current_folder:
            lines.append("")
            lines.append(f"// {folder}")
            lines.append("// " + "-" * 60)
            current_folder = folder
        lines.append(f"// {description}")
        lines.append(f"// Format: {FORMATS[kind].replace(chr(92), '')}")
        lines.append(f"{name} =")
        for expr_line in expression.strip().splitlines():
            lines.append(f"    {expr_line}" if expr_line else "")
        lines.append("")
    DAX_PATH.parent.mkdir(parents=True, exist_ok=True)
    DAX_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def m_queries() -> dict[str, str]:
    def typed_csv(filename: str, pairs: list[tuple[str, str]], extra: str = "") -> str:
        types = ", ".join("{" + f'"{column}", {dtype}' + "}" for column, dtype in pairs)
        return (
            "let\n"
            f'    Source = Csv.Document(File.Contents(pDataRoot & "{filename}"), '
            "[Delimiter = \",\", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),\n"
            "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),\n"
            f"    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}){extra}\n"
            "in\n"
            "    Typed"
        )

    date_pairs = [
        ("DateKey", "Int64.Type"),
        ("Date", "type date"),
        ("Year", "Int64.Type"),
        ("FiscalYear", "Int64.Type"),
        ("FiscalYearLabel", "type text"),
        ("Quarter", "Int64.Type"),
        ("QuarterName", "type text"),
        ("YearQuarter", "type text"),
        ("MonthNumber", "Int64.Type"),
        ("MonthName", "type text"),
        ("MonthShort", "type text"),
        ("MonthYear", "type text"),
        ("YearMonth", "type text"),
        ("YearMonthSort", "Int64.Type"),
        ("Day", "Int64.Type"),
        ("MonthStart", "type date"),
        ("IsMonthStart", "type text"),
        ("CalendarStage", "type text"),
    ]
    date_extra = (
        ",\n"
        '    LogicalMonthStart = Table.TransformColumns(Typed, {{"IsMonthStart", each _ = "True", type logical}}),\n'
        '    WithQuarterSort = Table.AddColumn(LogicalMonthStart, "YearQuarterSort", each [Year] * 10 + [Quarter], Int64.Type)'
    )
    # The trailing step name has to match the `in` clause. Rebuild this one.
    date_query = (
        "let\n"
        '    Source = Csv.Document(File.Contents(pDataRoot & "dim_date.csv"), '
        "[Delimiter = \",\", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),\n"
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),\n"
        "    Typed = Table.TransformColumnTypes(Promoted, {"
        + ", ".join("{" + f'"{c}", {t}' + "}" for c, t in date_pairs)
        + "}),\n"
        '    LogicalMonthStart = Table.TransformColumns(Typed, {{"IsMonthStart", each _ = "True", type logical}}),\n'
        '    WithQuarterSort = Table.AddColumn(LogicalMonthStart, "YearQuarterSort", each [Year] * 10 + [Quarter], Int64.Type)\n'
        "in\n"
        "    WithQuarterSort"
    )
    queries = {
        "dim_date": date_query,
        "dim_region": typed_csv(
            "dim_region.csv",
            [
                ("RegionKey", "Int64.Type"),
                ("Region", "type text"),
                ("RegionCode", "type text"),
                ("ManagementGroup", "type text"),
                ("Currency", "type text"),
            ],
        ),
        "dim_product_line": typed_csv(
            "dim_product_line.csv",
            [
                ("ProductLineKey", "Int64.Type"),
                ("ProductLine", "type text"),
                ("ProductCode", "type text"),
                ("RevenueType", "type text"),
                ("UnitOfMeasure", "type text"),
                ("PortfolioRole", "type text"),
            ],
        ),
        "dim_customer_segment": typed_csv(
            "dim_customer_segment.csv",
            [
                ("SegmentKey", "Int64.Type"),
                ("Segment", "type text"),
                ("SegmentCode", "type text"),
                ("BuyingMotion", "type text"),
            ],
        ),
        "fact_revenue_actuals": typed_csv(
            "fact_revenue_actuals.csv",
            [
                ("DateKey", "Int64.Type"),
                ("Date", "type date"),
                ("RegionKey", "Int64.Type"),
                ("ProductLineKey", "Int64.Type"),
                ("SegmentKey", "Int64.Type"),
                ("Revenue", "Currency.Type"),
                ("COGS", "Currency.Type"),
                ("GrossProfit", "Currency.Type"),
                ("OpEx", "Currency.Type"),
                ("EBITDA", "Currency.Type"),
                ("VolumeUnits", "Int64.Type"),
            ],
        ),
        "fact_budget_forecast": typed_csv(
            "fact_budget_forecast.csv",
            [
                ("DateKey", "Int64.Type"),
                ("Date", "type date"),
                ("RegionKey", "Int64.Type"),
                ("ProductLineKey", "Int64.Type"),
                ("SegmentKey", "Int64.Type"),
                ("Scenario", "type text"),
                ("Revenue", "Currency.Type"),
                ("COGS", "Currency.Type"),
                ("GrossProfit", "Currency.Type"),
                ("OpEx", "Currency.Type"),
                ("EBITDA", "Currency.Type"),
            ],
        ),
        "Scenario": (
            "let\n"
            "    Source = Table.FromRows(\n"
            "        {\n"
            '            {"Budget", "Plan", 1},\n'
            '            {"Backtest", "Model Validation", 2},\n'
            '            {"Forecast - Downside", "Rolling Forecast", 3},\n'
            '            {"Forecast - Base", "Rolling Forecast", 4},\n'
            '            {"Forecast - Upside", "Rolling Forecast", 5}\n'
            "        },\n"
            '        {"Scenario", "ScenarioGroup", "SortOrder"}\n'
            "    ),\n"
            "    Typed = Table.TransformColumnTypes(Source, "
            '{{"Scenario", type text}, {"ScenarioGroup", type text}, {"SortOrder", Int64.Type}})\n'
            "in\n"
            "    Typed"
        ),
        "_Measures": (
            "let\n"
            '    Source = Table.FromRows(Json.Document("[[]]"), {"Column1"}),\n'
            "    Empty = Table.SelectRows(Source, each false),\n"
            '    Removed = Table.RemoveColumns(Empty, {"Column1"})\n'
            "in\n"
            "    Removed"
        ),
    }
    # date_extra is unused; the date query is hand-finished above.
    del date_extra
    return queries


def write_power_query(queries: dict[str, str]) -> None:
    parts = [
        "// Vantage Process Group — Power Query M",
        "//",
        "// pDataRoot is a text parameter. Point it at the clone's data folder",
        "// and keep the trailing backslash, for example",
        "//   C:\\Projects\\business-revenue-forecast-powerbi\\data\\",
        "// Every CSV query concatenates that parameter with the file name.",
        "// Refresh after changing it. The Scenario and _Measures tables are",
        "// entered in M and do not read a file.",
        "//",
        "pDataRoot = \"C:\\\\Data\\\\business-revenue-forecast-powerbi\\\\data\\\\\" meta [IsParameterQuery = true, Type = \"Text\", IsParameterQueryRequired = true]",
        "",
    ]
    for name, query in queries.items():
        parts.append("")
        parts.append(f"// {name}")
        parts.append(f"shared {name} =")
        parts.append(query)
        parts.append("")
    PQ_PATH.parent.mkdir(parents=True, exist_ok=True)
    PQ_PATH.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def column_block(
    name: str,
    data_type: str,
    source: str,
    *,
    hidden: bool = False,
    key: bool = False,
    summarize: str = "none",
    fmt: str | None = None,
    sort: str | None = None,
    description: str | None = None,
) -> str:
    lines = []
    if description:
        lines.append(f"\t/// {description}")
    lines.append(f"\tcolumn {tmdl_ident(name)}")
    lines.append(f"\t\tdataType: {data_type}")
    if key:
        lines.append("\t\tisKey")
    if hidden:
        lines.append("\t\tisHidden")
    if fmt:
        lines.append(f"\t\tformatString: {fmt}")
    lines.append(f"\t\tlineageTag: {tag('col:' + source + ':' + name)}")
    lines.append(f"\t\tsummarizeBy: {summarize}")
    lines.append(f"\t\tsourceColumn: {source}")
    if sort:
        lines.append(f"\t\tsortByColumn: {tmdl_ident(sort)}")
    if data_type == "dateTime":
        lines.append("\t\tannotation UnderlyingDateTimeDataType = Date")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")
    return "\n".join(lines)


def partition_block(table: str, query: str) -> str:
    body = "\n".join("\t\t\t" + line if line else "" for line in query.splitlines())
    return (
        f"\tpartition {tmdl_ident(table)} = m\n"
        "\t\tmode: import\n"
        "\t\tsource =\n"
        f"{body}\n"
        "\n"
    )


def write_tmdl(queries: dict[str, str]) -> None:
    definition = POWERBI / "VantageFinancialForecast.SemanticModel" / "definition"
    tables = definition / "tables"
    tables.mkdir(parents=True, exist_ok=True)

    date = "\n".join(
        [
            "/// Daily calendar from 1 Jan 2022 through 31 Dec 2026. Marked as the model's date table.",
            "table dim_date",
            f"\tlineageTag: {tag('table:dim_date')}",
            "\tdataCategory: Time",
            "",
            column_block("Date", "dateTime", "Date", key=True, description="Calendar date. Facts land on the first of the month."),
            column_block("DateKey", "int64", "DateKey", hidden=True, fmt="0"),
            column_block("Year", "int64", "Year", fmt="0"),
            column_block("FiscalYear", "int64", "FiscalYear", hidden=True, fmt="0"),
            column_block("FiscalYearLabel", "string", "FiscalYearLabel", sort="FiscalYear", description="FY2022 through FY2026. The fiscal year is the calendar year."),
            column_block("Quarter", "int64", "Quarter", hidden=True, fmt="0"),
            column_block("QuarterName", "string", "QuarterName", sort="Quarter"),
            column_block("YearQuarter", "string", "YearQuarter", sort="YearQuarterSort"),
            column_block("YearQuarterSort", "int64", "YearQuarterSort", hidden=True, fmt="0"),
            column_block("MonthNumber", "int64", "MonthNumber", hidden=True, fmt="0"),
            column_block("MonthName", "string", "MonthName", sort="MonthNumber"),
            column_block("MonthShort", "string", "MonthShort", sort="MonthNumber"),
            column_block("MonthYear", "string", "MonthYear", sort="YearMonthSort"),
            column_block("YearMonth", "string", "YearMonth", sort="YearMonthSort"),
            column_block("YearMonthSort", "int64", "YearMonthSort", hidden=True, fmt="0"),
            column_block("Day", "int64", "Day", hidden=True, fmt="0"),
            column_block("MonthStart", "dateTime", "MonthStart", hidden=True),
            column_block("IsMonthStart", "boolean", "IsMonthStart", hidden=True),
            column_block("CalendarStage", "string", "CalendarStage", description="Actuals through December 2025, then the forecast horizon."),
            "\thierarchy 'Calendar'",
            f"\t\tlineageTag: {tag('hier:calendar')}",
            "",
            "\t\tlevel Year",
            f"\t\t\tlineageTag: {tag('lvl:year')}",
            "\t\t\tcolumn: Year",
            "",
            "\t\tlevel Quarter",
            f"\t\t\tlineageTag: {tag('lvl:quarter')}",
            "\t\t\tcolumn: YearQuarter",
            "",
            "\t\tlevel Month",
            f"\t\t\tlineageTag: {tag('lvl:month')}",
            "\t\t\tcolumn: MonthYear",
            "",
            partition_block("dim_date", queries["dim_date"]),
            "\tannotation PBI_ResultType = Table",
            "",
        ]
    )
    (tables / "dim_date.tmdl").write_text(date, encoding="utf-8")

    simple_tables = {
        "dim_region": (
            "Region, region code, and management group. Four regions, reported in USD.",
            [
                column_block("RegionKey", "int64", "RegionKey", key=True, hidden=True, fmt="0"),
                column_block("Region", "string", "Region"),
                column_block("RegionCode", "string", "RegionCode"),
                column_block("ManagementGroup", "string", "ManagementGroup"),
                column_block("Currency", "string", "Currency"),
            ],
        ),
        "dim_product_line": (
            "Five product lines. Software and service are the recurring, higher-margin mix.",
            [
                column_block("ProductLineKey", "int64", "ProductLineKey", key=True, hidden=True, fmt="0"),
                column_block("ProductLine", "string", "ProductLine"),
                column_block("ProductCode", "string", "ProductCode"),
                column_block("RevenueType", "string", "RevenueType"),
                column_block("UnitOfMeasure", "string", "UnitOfMeasure"),
                column_block("PortfolioRole", "string", "PortfolioRole"),
            ],
        ),
        "dim_customer_segment": (
            "Enterprise, mid-market, and SMB. Enterprise carries the equipment and software franchise.",
            [
                column_block("SegmentKey", "int64", "SegmentKey", key=True, hidden=True, fmt="0"),
                column_block("Segment", "string", "Segment"),
                column_block("SegmentCode", "string", "SegmentCode"),
                column_block("BuyingMotion", "string", "BuyingMotion"),
            ],
        ),
    }
    for table, (description, columns) in simple_tables.items():
        text = f"/// {description}\ntable {table}\n\tlineageTag: {tag('table:' + table)}\n\n"
        text += "".join(columns)
        text += partition_block(table, queries[table])
        text += "\tannotation PBI_ResultType = Table\n"
        (tables / f"{table}.tmdl").write_text(text, encoding="utf-8")

    scenario = "\n".join(
        [
            "/// Budget, the FY2025 backtest, and the three FY2026 forecast scenarios.",
            "table Scenario",
            f"\tlineageTag: {tag('table:Scenario')}",
            "",
            column_block("Scenario", "string", "Scenario", key=True, sort="SortOrder"),
            column_block("ScenarioGroup", "string", "ScenarioGroup"),
            column_block("SortOrder", "int64", "SortOrder", hidden=True, fmt="0"),
            partition_block("Scenario", queries["Scenario"]),
            "\tannotation PBI_ResultType = Table",
            "",
        ]
    )
    (tables / "Scenario.tmdl").write_text(scenario, encoding="utf-8")

    money = r'"\$#,0"'
    actual_cols = [
        column_block("DateKey", "int64", "DateKey", hidden=True, fmt="0"),
        column_block("Date", "dateTime", "Date"),
        column_block("RegionKey", "int64", "RegionKey", hidden=True, fmt="0"),
        column_block("ProductLineKey", "int64", "ProductLineKey", hidden=True, fmt="0"),
        column_block("SegmentKey", "int64", "SegmentKey", hidden=True, fmt="0"),
        column_block("Revenue", "double", "Revenue", summarize="sum", fmt=money),
        column_block("COGS", "double", "COGS", summarize="sum", fmt=money),
        column_block("GrossProfit", "double", "GrossProfit", summarize="sum", fmt=money, hidden=True),
        column_block("OpEx", "double", "OpEx", summarize="sum", fmt=money),
        column_block("EBITDA", "double", "EBITDA", summarize="sum", fmt=money, hidden=True),
        column_block("VolumeUnits", "int64", "VolumeUnits", summarize="sum", fmt='\"#,0\"', description="Units differ by product line. See UnitOfMeasure."),
    ]
    actual = (
        "/// Monthly actuals from January 2022 through December 2025. "
        "Grain is month, region, product line, and segment.\n"
        "table fact_revenue_actuals\n"
        f"\tlineageTag: {tag('table:fact_revenue_actuals')}\n\n"
        + "".join(actual_cols)
        + partition_block("fact_revenue_actuals", queries["fact_revenue_actuals"])
        + "\tannotation PBI_ResultType = Table\n"
    )
    (tables / "fact_revenue_actuals.tmdl").write_text(actual, encoding="utf-8")

    budget_cols = [
        column_block("DateKey", "int64", "DateKey", hidden=True, fmt="0"),
        column_block("Date", "dateTime", "Date"),
        column_block("RegionKey", "int64", "RegionKey", hidden=True, fmt="0"),
        column_block("ProductLineKey", "int64", "ProductLineKey", hidden=True, fmt="0"),
        column_block("SegmentKey", "int64", "SegmentKey", hidden=True, fmt="0"),
        column_block("Scenario", "string", "Scenario"),
        column_block("Revenue", "double", "Revenue", summarize="sum", fmt=money),
        column_block("COGS", "double", "COGS", summarize="sum", fmt=money),
        column_block("GrossProfit", "double", "GrossProfit", summarize="sum", fmt=money, hidden=True),
        column_block("OpEx", "double", "OpEx", summarize="sum", fmt=money),
        column_block("EBITDA", "double", "EBITDA", summarize="sum", fmt=money, hidden=True),
    ]
    budget = (
        "/// Budget for FY2022–FY2026, the FY2025 backtest, and FY2026 base, upside, and downside. "
        "Filter Scenario, or use the explicit measures, so the rows are not added together.\n"
        "table fact_budget_forecast\n"
        f"\tlineageTag: {tag('table:fact_budget_forecast')}\n\n"
        + "".join(budget_cols)
        + partition_block("fact_budget_forecast", queries["fact_budget_forecast"])
        + "\tannotation PBI_ResultType = Table\n"
    )
    (tables / "fact_budget_forecast.tmdl").write_text(budget, encoding="utf-8")

    measure_lines = [
        "/// Calculation table. No columns. Every report visual reads from here.",
        "table _Measures",
        f"\tlineageTag: {tag('table:_Measures')}",
        "",
    ]
    for name, expression, kind, folder, description in ordered_measures():
        measure_lines.append(f"\t/// {description}")
        measure_lines.append(f"\tmeasure {tmdl_ident(name)} = ```")
        for line in expression.strip().splitlines():
            measure_lines.append("\t\t\t" + line)
        measure_lines.append("\t\t```")
        measure_lines.append(f'\t\tformatString: "{FORMATS[kind]}"')
        measure_lines.append(f"\t\tdisplayFolder: {folder}")
        measure_lines.append(f"\t\tlineageTag: {tag('measure:' + name)}")
        measure_lines.append("")
    measure_lines.append(partition_block("_Measures", queries["_Measures"]).rstrip())
    measure_lines.append("")
    measure_lines.append("\tannotation PBI_ResultType = Table")
    measure_lines.append("")
    (tables / "_Measures.tmdl").write_text("\n".join(measure_lines), encoding="utf-8")

    relationships = []
    pairs = [
        ("fact_revenue_actuals", "Date", "dim_date", "Date"),
        ("fact_revenue_actuals", "RegionKey", "dim_region", "RegionKey"),
        ("fact_revenue_actuals", "ProductLineKey", "dim_product_line", "ProductLineKey"),
        ("fact_revenue_actuals", "SegmentKey", "dim_customer_segment", "SegmentKey"),
        ("fact_budget_forecast", "Date", "dim_date", "Date"),
        ("fact_budget_forecast", "RegionKey", "dim_region", "RegionKey"),
        ("fact_budget_forecast", "ProductLineKey", "dim_product_line", "ProductLineKey"),
        ("fact_budget_forecast", "SegmentKey", "dim_customer_segment", "SegmentKey"),
        ("fact_budget_forecast", "Scenario", "Scenario", "Scenario"),
    ]
    for fact, fact_col, dim, dim_col in pairs:
        relationships.append(
            "\n".join(
                [
                    f"relationship {tag('rel:' + fact + ':' + fact_col)}",
                    "\tcrossFilteringBehavior: oneDirection",
                    f"\tfromColumn: {fact}.{fact_col}",
                    f"\ttoColumn: {dim}.{dim_col}",
                    "",
                ]
            )
        )
    (definition / "relationships.tmdl").write_text("\n".join(relationships), encoding="utf-8")

    (definition / "database.tmdl").write_text(
        "database\n\tcompatibilityLevel: 1567\n",
        encoding="utf-8",
    )
    model = "\n".join(
        [
            "model Model",
            "\tculture: en-US",
            "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
            "\tsourceQueryCulture: en-US",
            "\tdataAccessOptions",
            "\t\tlegacyRedirects",
            "\t\treturnErrorValuesAsNull",
            "",
            "annotation __PBI_TimeIntelligenceEnabled = 1",
            "",
            'annotation PBI_QueryOrder = ["pDataRoot","dim_date","dim_region","dim_product_line","dim_customer_segment","Scenario","fact_revenue_actuals","fact_budget_forecast","_Measures"]',
            "",
            'annotation PBI_ProTooling = ["DevMode"]',
            "",
            "ref table dim_date",
            "ref table dim_region",
            "ref table dim_product_line",
            "ref table dim_customer_segment",
            "ref table Scenario",
            "ref table fact_revenue_actuals",
            "ref table fact_budget_forecast",
            "ref table _Measures",
            "",
        ]
    )
    (definition / "model.tmdl").write_text(model, encoding="utf-8")
    (definition / "expressions.tmdl").write_text(
        "\n".join(
            [
                "expression pDataRoot = \"C:\\\\Data\\\\business-revenue-forecast-powerbi\\\\data\\\\\" meta [IsParameterQuery=true, Type=\"Text\", IsParameterQueryRequired=true]",
                f"\tlineageTag: {tag('expr:pDataRoot')}",
                "",
                "\tannotation PBI_ResultType = Text",
                "",
            ]
        ),
        encoding="utf-8",
    )

    nodes = [
        ("dim_date", 80, 20, 260, 380),
        ("dim_region", 420, 20, 230, 180),
        ("dim_product_line", 700, 20, 250, 220),
        ("dim_customer_segment", 1000, 20, 240, 180),
        ("fact_revenue_actuals", 360, 280, 280, 300),
        ("fact_budget_forecast", 700, 280, 280, 320),
        ("Scenario", 1040, 280, 220, 160),
        ("_Measures", 80, 460, 240, 220),
    ]
    diagram = {
        "version": "1.1.0",
        "diagrams": [
            {
                "ordinal": 0,
                "scrollPosition": {"x": 0, "y": 0},
                "nodes": [
                    {
                        "location": {"x": x, "y": y},
                        "nodeIndex": name,
                        "nodeLineageTag": tag("table:" + name),
                        "size": {"height": height, "width": width},
                        "zIndex": index,
                    }
                    for index, (name, x, y, width, height) in enumerate(nodes)
                ],
                "name": "All tables",
                "zoomValue": 80,
                "pinKeyFieldsToTop": True,
                "showExtraHeaderInfo": False,
                "hideKeyFieldsWhenCollapsed": False,
                "tablesLocked": False,
            }
        ],
        "selectedDiagram": "All tables",
        "defaultDiagram": "All tables",
    }
    write_json(POWERBI / "VantageFinancialForecast.SemanticModel" / "diagramLayout.json", diagram)
    write_json(
        POWERBI / "VantageFinancialForecast.SemanticModel" / "definition.pbism",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.0",
            "settings": {},
        },
    )
    write_json(
        POWERBI / "VantageFinancialForecast.SemanticModel" / ".platform",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "SemanticModel", "displayName": "Vantage Financial Forecast"},
            "config": {"version": "2.0", "logicalId": tag("platform:model")},
        },
    )


def write_report(pages: list[dict]) -> None:
    report = POWERBI / "VantageFinancialForecast.Report"
    theme_target = report / "StaticResources" / "RegisteredResources" / THEME_NAME
    write_json(POWERBI / "theme" / THEME_NAME, THEME)
    write_json(theme_target, THEME)
    definition = report / "definition"
    write_json(
        definition / "version.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
            "version": "2.0.0",
        },
    )
    write_json(
        definition / "report.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.2.0/schema.json",
            "themeCollection": {
                "customTheme": {
                    "name": THEME_NAME,
                    "reportVersionAtImport": {"visual": "2.5.0", "report": "3.1.0", "page": "2.3.0"},
                    "type": "RegisteredResources",
                }
            },
            "objects": {
                "section": [
                    {
                        "properties": {
                            "verticalAlignment": lit("'Top'"),
                        }
                    }
                ]
            },
            "resourcePackages": [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [
                        {"name": THEME_NAME, "path": THEME_NAME, "type": "CustomTheme"}
                    ],
                }
            ],
            "settings": {
                "useStylableVisualContainerHeader": True,
                "exportDataMode": "AllowSummarized",
                "defaultDrillFilterOtherVisuals": True,
                "allowChangeFilterTypes": True,
                "useEnhancedTooltips": True,
            },
        },
    )
    write_json(
        definition / "pages" / "pages.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": [page["id"] for page in pages],
            "activePageName": pages[0]["id"],
        },
    )
    for page in pages:
        page_dir = definition / "pages" / page["id"]
        payload = {
            "$schema": SCHEMA_PAGE,
            "name": page["id"],
            "displayName": page["display"],
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
            "objects": {
                "background": [
                    {
                        "properties": {
                            "color": solid(CANVAS),
                            "transparency": lit("0D"),
                        }
                    }
                ]
            },
        }
        if page["filters"]:
            payload["filterConfig"] = {"filters": page["filters"]}
        write_json(page_dir / "page.json", payload)
        for visual in page["visuals"]:
            write_json(page_dir / "visuals" / visual["name"] / "visual.json", visual)
    write_json(
        report / "definition.pbir",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../VantageFinancialForecast.SemanticModel"}},
        },
    )
    write_json(
        report / ".platform",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Report", "displayName": "Vantage Financial Forecast"},
            "config": {"version": "2.0", "logicalId": tag("platform:report")},
        },
    )
    write_json(
        POWERBI / "VantageFinancialForecast.pbip",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": "VantageFinancialForecast.Report"}}],
            "settings": {"enableAutoRecovery": True},
        },
    )


def main() -> None:
    _patch_measures()
    names = [item[0] for item in MEASURES]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise SystemExit(f"Duplicate measures: {duplicates}")
    queries = m_queries()
    write_dax()
    write_power_query(queries)
    write_tmdl(queries)
    write_report(build_pages())
    print(f"Measures: {len(MEASURES)}")
    print(f"Wrote {DAX_PATH.relative_to(ROOT)} and {PQ_PATH.relative_to(ROOT)}")
    print(f"Wrote {POWERBI.relative_to(ROOT)}/VantageFinancialForecast.pbip")


if __name__ == "__main__":
    main()
