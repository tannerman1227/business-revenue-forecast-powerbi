"""Build the Power BI project from the query script and the DAX measures.

    python scripts/build_pbip.py
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBIP = ROOT / "powerbi"
QUERY_PATH = ROOT / "power_query" / "transformations.pq"
MEASURE_PATH = ROOT / "dax" / "measures.dax"
NS = uuid.UUID("6f1e2d3c-4b5a-6978-8e9d-0a1b2c3d4e5f")

PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json"
VISUAL_CONFIG_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualConfiguration/2.2.0/schema.json"


def tag(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def parse_queries(text: str) -> list[dict]:
    pattern = re.compile(r"(?m)^// ===== Query: ([A-Za-z0-9]+) \| (table|expression) \| ([A-Za-z]+) =====\s*$")
    matches = list(pattern.finditer(text))
    if not matches:
        raise RuntimeError("No queries found in transformations.pq")
    queries = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        queries.append(
            {
                "name": match.group(1),
                "kind": match.group(2),
                "result": match.group(3),
                "body": body,
            }
        )
    return queries


def parse_measures(text: str) -> list[dict]:
    chunks = re.split(r"(?m)^//// ", text)
    measures = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        header, _, body = chunk.partition("\n")
        parts = [part.strip() for part in header.split("|")]
        if len(parts) < 4:
            raise RuntimeError(f"Measure header needs four fields: {header}")
        name, folder, fmt, description = parts[0], parts[1], parts[2], "|".join(parts[3:]).strip()
        expression = body.split("=", 1)[1].strip()
        measures.append(
            {"name": name, "folder": folder, "format": fmt, "description": description, "expression": expression}
        )
    return measures


def indent(text: str, tabs: int) -> str:
    prefix = "\t" * tabs
    lines = text.splitlines() or [""]
    return "\n".join(prefix + (line if line.strip() else "") for line in lines)


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


COLUMN_PLANS = {
    "DimDate": [
        ("Date", "dateTime", "none", "yyyy-mm-dd", True, None),
        ("Year", "int64", "none", "0", False, None),
        ("Quarter", "int64", "none", "0", False, None),
        ("QuarterLabel", "string", "none", None, False, None),
        ("MonthNumber", "int64", "none", "0", False, None),
        ("MonthName", "string", "none", None, False, "MonthNumber"),
        ("MonthShort", "string", "none", None, False, "MonthNumber"),
        ("YearMonth", "string", "none", None, False, "Date"),
        ("MonthYearLabel", "string", "none", None, False, "Date"),
    ],
    "DimSector": [
        ("SectorKey", "string", "none", None, True, None),
        ("SectorName", "string", "none", None, False, "SortOrder"),
        ("SectorShort", "string", "none", None, False, "SortOrder"),
        ("SectorGroup", "string", "none", None, False, None),
        ("Channel", "string", "none", None, False, None),
        ("KindOfBusiness", "string", "none", None, False, None),
        ("FredSeriesNSA", "string", "none", None, False, None),
        ("FredSeriesSA", "string", "none", None, False, None),
        ("FredUrlNSA", "string", "none", None, False, None),
        ("FredUrlSA", "string", "none", None, False, None),
        ("SortOrder", "int64", "none", "0", False, None),
    ],
    "FactRetailSales": [
        ("Date", "dateTime", "none", "yyyy-mm-dd", False, None),
        ("SectorKey", "string", "none", None, False, None),
        ("SalesNSA", "double", "sum", "#,0", False, None),
        ("SalesSA", "double", "sum", "#,0", False, None),
    ],
    "FactForecast": [
        ("Date", "dateTime", "none", "yyyy-mm-dd", False, None),
        ("SectorKey", "string", "none", None, False, None),
        ("Horizon", "int64", "none", "0", False, None),
        ("ForecastNSA", "double", "sum", "#,0.00", False, None),
        ("Lower80", "double", "none", "#,0.00", False, None),
        ("Upper80", "double", "none", "#,0.00", False, None),
        ("ReconcileFactor", "double", "none", "0.000000", False, None),
        ("Model", "string", "none", None, False, None),
    ],
    "ForecastTotal": [
        ("Date", "dateTime", "none", "yyyy-mm-dd", False, None),
        ("Horizon", "int64", "none", "0", False, None),
        ("ForecastNSA", "double", "sum", "#,0.00", False, None),
        ("Lower80", "double", "none", "#,0.00", False, None),
        ("Upper80", "double", "none", "#,0.00", False, None),
        ("Model", "string", "none", None, False, None),
    ],
    "FactBacktest": [
        ("Date", "dateTime", "none", "yyyy-mm-dd", False, None),
        ("SectorKey", "string", "none", None, False, None),
        ("Horizon", "int64", "none", "0", False, None),
        ("ActualNSA", "int64", "sum", "#,0", False, None),
        ("ForecastNSA", "double", "sum", "#,0.00", False, None),
        ("SeasonalNaiveNSA", "int64", "sum", "#,0", False, None),
        ("Lower80", "double", "none", "#,0.00", False, None),
        ("Upper80", "double", "none", "#,0.00", False, None),
        ("ReconcileFactor", "double", "none", "0.000000", False, None),
        ("Error", "double", "sum", "#,0.00", False, None),
        ("AbsError", "double", "sum", "#,0.00", False, None),
        ("AbsPctError", "double", "none", "0.00%", False, None),
        ("Model", "string", "none", None, False, None),
    ],
    "BacktestTotal": [
        ("Date", "dateTime", "none", "yyyy-mm-dd", False, None),
        ("Horizon", "int64", "none", "0", False, None),
        ("ForecastNSA", "double", "sum", "#,0.00", False, None),
        ("Lower80", "double", "none", "#,0.00", False, None),
        ("Upper80", "double", "none", "#,0.00", False, None),
        ("Model", "string", "none", None, False, None),
        ("ActualNSA", "int64", "sum", "#,0", False, None),
        ("SeasonalNaiveNSA", "int64", "sum", "#,0", False, None),
        ("Error", "double", "sum", "#,0.00", False, None),
        ("AbsError", "double", "sum", "#,0.00", False, None),
        ("AbsPctError", "double", "none", "0.00%", False, None),
    ],
}

TABLE_NOTES = {
    "DimDate": "Month-start calendar covering published sales and the 12-month forecast.",
    "DimSector": "Census kind-of-business categories that add up to retail and food services.",
    "FactRetailSales": "Monthly sales by sector, in millions of dollars.",
    "FactForecast": "12-month sector forecast. The sectors add up to the total forecast.",
    "ForecastTotal": "12-month forecast for all retail and food services, with an 80 percent range.",
    "FactBacktest": "Sector forecast compared with the latest 12 published months.",
    "BacktestTotal": "Total forecast compared with the latest 12 published months.",
}


def emit_column(table: str, spec: tuple) -> str:
    name, data_type, summarize, fmt, is_key, sort_by = spec
    lines = [f"\tcolumn {name}"]
    lines.append(f"\t\tdataType: {data_type}")
    if fmt:
        lines.append(f"\t\tformatString: {quote(fmt)}")
    lines.append(f"\t\tlineageTag: {tag(table + '.' + name)}")
    lines.append(f"\t\tsummarizeBy: {summarize}")
    lines.append(f"\t\tsourceColumn: {name}")
    if is_key:
        lines.append("\t\tisKey")
    if name == "MetricsKey":
        lines.append("\t\tisHidden")
    if sort_by:
        lines.append(f"\t\tsortByColumn: {sort_by}")
    lines.append("")
    lines.append("\t\tannotation SummarizationSetBy = Automatic")
    lines.append("")
    return "\n".join(lines)


def emit_measure(measure: dict) -> str:
    lines = [f"\tmeasure '{measure['name']}' = ```"]
    for line in measure["expression"].splitlines():
        lines.append("\t\t" + line)
    lines.append("\t\t```")
    if measure["format"]:
        lines.append(f"\t\tformatString: {quote(measure['format'])}")
    lines.append(f"\t\tdisplayFolder: {quote(measure['folder'])}")
    lines.append(f"\t\tlineageTag: {tag('measure.' + measure['name'])}")
    if measure["name"] == "Use Sector Detail":
        lines.append("\t\tisHidden")
    if measure["description"]:
        lines.append(f"\t\tdescription = {quote(measure['description'])}")
    return "\n".join(lines)


def emit_table(query: dict, measures: list[dict] | None = None) -> str:
    name = query["name"]
    lines = [f"table {name}", f"\tlineageTag: {tag('table.' + name)}"]
    if name in TABLE_NOTES:
        lines.append(f"\tdescription = {quote(TABLE_NOTES[name])}")
    lines.append("")
    if name == "Metrics":
        lines.append(emit_column("Metrics", ("MetricsKey", "int64", "none", "0", False, None)))
        for measure in measures or []:
            lines.append(emit_measure(measure))
            lines.append("")
        body = "let\n    Source = #table(type table [MetricsKey = Int64.Type], {{1}})\nin\n    Source"
    else:
        for spec in COLUMN_PLANS[name]:
            lines.append(emit_column(name, spec))
        body = query["body"]
    lines.append(f"\tpartition {name} = m")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append(indent(body, 3))
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    lines.append("")
    return "\n".join(lines)


def emit_expressions(queries: list[dict]) -> str:
    blocks = []
    for query in queries:
        if query["kind"] != "expression":
            continue
        blocks.append(
            "\n".join(
                [
                    f"expression {query['name']} =",
                    indent(query["body"], 2),
                    f"\tlineageTag: {tag('expression.' + query['name'])}",
                    "",
                    f"\tannotation PBI_ResultType = {query['result']}",
                    "",
                ]
            )
        )
    return "\n".join(blocks)


def emit_relationships() -> str:
    pairs = [
        ("FactRetailSales", "Date", "DimDate", "Date", True),
        ("FactRetailSales", "SectorKey", "DimSector", "SectorKey", False),
        ("FactForecast", "Date", "DimDate", "Date", True),
        ("FactForecast", "SectorKey", "DimSector", "SectorKey", False),
        ("FactBacktest", "Date", "DimDate", "Date", True),
        ("FactBacktest", "SectorKey", "DimSector", "SectorKey", False),
        ("ForecastTotal", "Date", "DimDate", "Date", True),
        ("BacktestTotal", "Date", "DimDate", "Date", True),
    ]
    blocks = []
    for source, source_col, target, target_col, is_date in pairs:
        name = tag(f"rel.{source}.{source_col}.{target}.{target_col}")
        lines = [f"relationship {name}"]
        if is_date:
            lines.append("\tjoinOnDateBehavior: datePartOnly")
        lines.append(f"\tfromColumn: {source}.{source_col}")
        lines.append(f"\ttoColumn: {target}.{target_col}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def lit(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value}D"
    return "'" + str(value).replace("'", "''") + "'"


def expr_literal(value) -> dict:
    return {"expr": {"Literal": {"Value": lit(value)}}}


def measure_projection(name: str) -> dict:
    return {
        "field": {"Measure": {"Expression": {"SourceRef": {"Entity": "Metrics"}}, "Property": name}},
        "queryRef": f"Metrics.{name}",
        "nativeQueryRef": name,
    }


def column_projection(table: str, column: str) -> dict:
    return {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}},
        "queryRef": f"{table}.{column}",
        "nativeQueryRef": column,
    }


def visual(name: str, visual_type: str, x: int, y: int, w: int, h: int, z: int, projections: dict, title: str, sort_field=None, direction: str = "Descending") -> dict:
    query = {"queryState": projections}
    if sort_field is not None:
        query["sortDefinition"] = {"sort": [{"field": sort_field, "direction": direction}], "isDefaultSort": False}
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {
            "$schema": VISUAL_CONFIG_SCHEMA,
            "visualType": visual_type,
            "query": query,
            "visualContainerObjects": {
                "title": [
                    {
                        "properties": {
                            "show": expr_literal(True),
                            "text": expr_literal(title),
                            "fontColor": {"solid": {"color": expr_literal("#0B1F33")}},
                            "bold": expr_literal(True),
                        }
                    }
                ]
            },
        },
    }


def card(name: str, measure: str, title: str, x: int, y: int, w: int, h: int, z: int) -> dict:
    return visual(
        name,
        "card",
        x,
        y,
        w,
        h,
        z,
        {"Values": {"projections": [measure_projection(measure)]}},
        title,
    )


def page(name: str, display: str, visuals: list[dict]) -> dict:
    return {
        "$schema": PAGE_SCHEMA,
        "name": name,
        "displayName": display,
        "displayOption": "FitToPage",
        "height": 720,
        "width": 1280,
        "objects": {
            "background": [
                {
                    "properties": {
                        "color": {"solid": {"color": expr_literal("#F4F7FB")}},
                        "transparency": expr_literal(0),
                    }
                }
            ]
        },
    }, visuals


def build_pages() -> list[tuple[dict, list[dict]]]:
    yoy = measure_projection("Latest Month YoY")["field"]
    ttm = measure_projection("TTM Sales")["field"]
    mape = measure_projection("Backtest MAPE")["field"]
    forward = measure_projection("Forward 12 Forecast")["field"]
    pages = []
    pages.append(
        page(
            "executive",
            "Executive Overview",
            [
                card("execLatest", "Latest Month Sales", "Latest month (millions of dollars)", 16, 16, 304, 110, 0),
                card("execYoy", "Latest Month YoY", "Change from last year", 332, 16, 304, 110, 1),
                card("execMom", "Latest Month MoM", "Change from last month", 648, 16, 304, 110, 2),
                card("execTtm", "TTM Sales", "Last 12 months (millions)", 964, 16, 300, 110, 3),
                visual(
                    "execLine",
                    "lineChart",
                    16,
                    140,
                    760,
                    430,
                    4,
                    {
                        "Category": {"projections": [column_projection("DimDate", "MonthYearLabel")]},
                        "Y": {
                            "projections": [
                                measure_projection("Sales NSA Last 8 Years"),
                                measure_projection("Sales SA Last 8 Years"),
                            ]
                        },
                    },
                    "Monthly sales, last 8 years",
                    column_projection("DimDate", "MonthYearLabel")["field"],
                    "Ascending",
                ),
                visual(
                    "execBar",
                    "clusteredBarChart",
                    788,
                    140,
                    476,
                    430,
                    5,
                    {
                        "Category": {"projections": [column_projection("DimSector", "SectorShort")]},
                        "Y": {"projections": [measure_projection("Latest Month YoY")]},
                    },
                    "Latest month vs the same month last year",
                    yoy,
                ),
                card("execSource", "Source Note", "Source", 16, 584, 1248, 120, 6),
            ],
        )
    )
    pages.append(
        page(
            "sectors",
            "Sector Performance",
            [
                visual(
                    "sectorSlicer",
                    "slicer",
                    16,
                    16,
                    240,
                    688,
                    0,
                    {"Values": {"projections": [column_projection("DimSector", "SectorGroup")]}},
                    "Sector group",
                ),
                visual(
                    "sectorSales",
                    "clusteredBarChart",
                    270,
                    16,
                    490,
                    340,
                    1,
                    {
                        "Category": {"projections": [column_projection("DimSector", "SectorShort")]},
                        "Y": {"projections": [measure_projection("TTM Sales")]},
                    },
                    "Last 12 months by sector",
                    ttm,
                ),
                visual(
                    "sectorYoy",
                    "clusteredBarChart",
                    772,
                    16,
                    492,
                    340,
                    2,
                    {
                        "Category": {"projections": [column_projection("DimSector", "SectorShort")]},
                        "Y": {"projections": [measure_projection("TTM YoY Growth")]},
                    },
                    "Last 12 months vs the year before",
                    measure_projection("TTM YoY Growth")["field"],
                ),
                visual(
                    "sectorTable",
                    "tableEx",
                    270,
                    370,
                    994,
                    334,
                    3,
                    {
                        "Values": {
                            "projections": [
                                column_projection("DimSector", "SectorShort"),
                                measure_projection("Latest Month Sales"),
                                measure_projection("Latest Month YoY"),
                                measure_projection("TTM Sales"),
                                measure_projection("TTM Sector Share"),
                                measure_projection("TTM YoY Growth"),
                            ]
                        }
                    },
                    "Sector scorecard",
                ),
            ],
        )
    )
    pages.append(
        page(
            "forecast",
            "12-Month Forecast",
            [
                card("fcForward", "Forward 12 Forecast", "Next 12 months (millions)", 16, 16, 304, 100, 0),
                card("fcGrowth", "Forward vs Prior 12", "Vs the latest 12 months", 332, 16, 304, 100, 1),
                card("fcPrior", "Prior 12 Actual", "Latest 12 months (millions)", 648, 16, 304, 100, 2),
                card("fcMape", "Backtest MAPE", "Average miss on the test year", 964, 16, 300, 100, 3),
                visual(
                    "fcLine",
                    "lineChart",
                    16,
                    130,
                    1248,
                    300,
                    4,
                    {
                        "Category": {"projections": [column_projection("DimDate", "MonthYearLabel")]},
                        "Y": {
                            "projections": [
                                measure_projection("Sales NSA Last 8 Years"),
                                measure_projection("Forecast Outlook NSA"),
                                measure_projection("Forecast Band Lower"),
                                measure_projection("Forecast Band Upper"),
                            ]
                        },
                    },
                    "Recent sales and the next 12 months",
                    column_projection("DimDate", "MonthYearLabel")["field"],
                    "Ascending",
                ),
                visual(
                    "fcBar",
                    "clusteredBarChart",
                    16,
                    444,
                    1248,
                    260,
                    5,
                    {
                        "Category": {"projections": [column_projection("DimSector", "SectorShort")]},
                        "Y": {"projections": [measure_projection("Forward 12 Forecast")]},
                    },
                    "Next 12 months by sector",
                    forward,
                ),
            ],
        )
    )
    pages.append(
        page(
            "accuracy",
            "Forecast Accuracy",
            [
                card("accMape", "Backtest MAPE", "Average percent miss", 16, 16, 200, 96, 0),
                card("accNaive", "Backtest Naive MAPE", "Same month last year", 224, 16, 200, 96, 1),
                card("accRmse", "Backtest RMSE", "Root mean squared error", 432, 16, 200, 96, 2),
                card("accMae", "Backtest MAE", "Average absolute miss", 640, 16, 200, 96, 3),
                card("accBias", "Backtest Bias", "Average gap", 848, 16, 200, 96, 4),
                card("accCover", "Backtest Coverage", "Inside the 80% range", 1056, 16, 208, 96, 5),
                visual(
                    "accLine",
                    "lineChart",
                    16,
                    126,
                    1248,
                    280,
                    6,
                    {
                        "Category": {"projections": [column_projection("DimDate", "MonthYearLabel")]},
                        "Y": {
                            "projections": [
                                measure_projection("Backtest Actual"),
                                measure_projection("Backtest Forecast"),
                                measure_projection("Backtest Naive"),
                            ]
                        },
                    },
                    "Test year: actual, forecast, and same month last year",
                    column_projection("DimDate", "MonthYearLabel")["field"],
                    "Ascending",
                ),
                visual(
                    "accBar",
                    "clusteredBarChart",
                    16,
                    420,
                    1248,
                    284,
                    7,
                    {
                        "Category": {"projections": [column_projection("DimSector", "SectorShort")]},
                        "Y": {"projections": [measure_projection("Backtest MAPE")]},
                    },
                    "Average percent miss by sector",
                    mape,
                ),
            ],
        )
    )
    return pages


def main() -> None:
    queries = parse_queries(QUERY_PATH.read_text(encoding="utf-8"))
    measures = parse_measures(MEASURE_PATH.read_text(encoding="utf-8"))
    report = PBIP / "USRetailForecast.Report"
    model = PBIP / "USRetailForecast.SemanticModel"
    if report.exists():
        for path in report.rglob("*"):
            if path.is_file():
                path.unlink()
    if model.exists():
        for path in model.rglob("*"):
            if path.is_file():
                path.unlink()

    write(
        PBIP / "USRetailForecast.pbip",
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
                "version": "1.0",
                "artifacts": [{"report": {"path": "USRetailForecast.Report"}}],
                "settings": {"enableAutoRecovery": True},
            },
            indent=2,
        )
        + "\n",
    )
    write(
        report / "definition.pbir",
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                "version": "4.0",
                "datasetReference": {"byPath": {"path": "../USRetailForecast.SemanticModel"}},
            },
            indent=2,
        )
        + "\n",
    )
    write(
        report / "definition" / "version.json",
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
                "version": "2.0.0",
            },
            indent=2,
        )
        + "\n",
    )
    write(
        report / "definition" / "report.json",
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.1.0/schema.json",
                "themeCollection": {
                    "baseTheme": {
                        "name": "CY24SU10",
                        "reportVersionAtImport": {"visual": "2.9.0", "page": "2.1.0", "report": "3.1.0"},
                        "type": "SharedResources",
                    }
                },
                "resourcePackages": [
                    {
                        "name": "SharedResources",
                        "type": "SharedResources",
                        "items": [
                            {"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}
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
            indent=2,
        )
        + "\n",
    )
    pages = build_pages()
    write(
        report / "definition" / "pages" / "pages.json",
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
                "pageOrder": [item[0]["name"] for item in pages],
                "activePageName": pages[0][0]["name"],
            },
            indent=2,
        )
        + "\n",
    )
    for page_json, visuals in pages:
        folder = report / "definition" / "pages" / page_json["name"]
        write(folder / "page.json", json.dumps(page_json, indent=2) + "\n")
        for item in visuals:
            write(folder / "visuals" / item["name"] / "visual.json", json.dumps(item, indent=2) + "\n")

    write(
        model / "definition.pbism",
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
                "version": "4.2",
                "settings": {},
            },
            indent=2,
        )
        + "\n",
    )
    table_names = [
        "DimDate",
        "DimSector",
        "FactRetailSales",
        "FactForecast",
        "ForecastTotal",
        "FactBacktest",
        "BacktestTotal",
        "Metrics",
    ]
    by_name = {query["name"]: query for query in queries}
    model_tmdl = "\n".join(
        [
            "model Model",
            "\tculture: en-US",
            "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
            "\tsourceQueryCulture: en-US",
            "\tdataAccessOptions",
            "\t\tlegacyRedirects",
            "\t\treturnErrorValuesAsNull",
            "",
            "\tannotation __PBI_TimeIntelligenceEnabled = 0",
            "",
            "\tannotation PBI_ProTooling = [\"DevMode\"]",
            "",
            *[f"\tref table {name}" for name in table_names],
            "",
            "\tref cultureInfo en-US",
            "",
        ]
    )
    write(model / "definition" / "model.tmdl", model_tmdl)
    write(model / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1567\n")
    write(model / "definition" / "relationships.tmdl", emit_relationships())
    write(model / "definition" / "expressions.tmdl", emit_expressions(queries))
    write(model / "definition" / "cultures" / "en-US.tmdl", "cultureInfo en-US\n")
    for name in table_names:
        if name == "Metrics":
            query = {"name": "Metrics", "body": ""}
            text = emit_table(query, measures)
        else:
            text = emit_table(by_name[name])
        write(model / "definition" / "tables" / f"{name}.tmdl", text + "\n")
    print(f"Built {PBIP / 'USRetailForecast.pbip'}")
    print(f"Measures: {len(measures)}")


if __name__ == "__main__":
    main()
