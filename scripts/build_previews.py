"""Render the four executive preview images from the generated star schema.

The numbers on the cards are the same display strings written to
``forecast_metrics.json``, so the pictures, the README, and the CSVs agree.
Colors are the corporate-finance theme used by the Power BI report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from forecast_model import bps, money_m, pct  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ASSETS = ROOT / "assets"

NAVY = "#0E1C36"
TEAL = "#0E7C7B"
GOLD = "#C4A35A"
BLUE = "#1F4E79"
GREEN = "#1F7A4D"
RED = "#A33B32"
SLATE = "#5C6B73"
INK = "#1A2332"
MUTED = "#5C6B73"
LINE = "#E2E8F0"
WHITE = "#FFFFFF"
CANVAS = "#F4F6F8"
SOFT = "#F8FAFC"

for font_path in (
    "/usr/share/fonts/truetype/macos/Inter-Regular.ttf",
    "/usr/share/fonts/truetype/macos/Inter-Medium.ttf",
    "/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf",
    "/usr/share/fonts/truetype/macos/Inter-Bold.ttf",
):
    font_manager.fontManager.addfont(font_path)

plt.rcParams.update(
    {
        "font.family": "Inter",
        "text.color": INK,
        "axes.unicode_minus": False,
        "figure.facecolor": CANVAS,
    }
)


def load() -> dict:
    actuals = pd.read_csv(DATA / "fact_revenue_actuals.csv", parse_dates=["Date"])
    plan = pd.read_csv(DATA / "fact_budget_forecast.csv", parse_dates=["Date"])
    regions = pd.read_csv(DATA / "dim_region.csv")
    products = pd.read_csv(DATA / "dim_product_line.csv")
    segments = pd.read_csv(DATA / "dim_customer_segment.csv")
    metrics = json.loads((DATA / "forecast_metrics.json").read_text())
    for frame in (actuals, plan):
        frame["Year"] = frame["Date"].dt.year
        frame["Quarter"] = frame["Date"].dt.quarter
        frame["YearQuarter"] = frame["Date"].dt.to_period("Q").astype(str)
    actuals = actuals.merge(regions, on="RegionKey").merge(products, on="ProductLineKey").merge(segments, on="SegmentKey")
    plan = plan.merge(regions, on="RegionKey").merge(products, on="ProductLineKey").merge(segments, on="SegmentKey")
    return {"actuals": actuals, "plan": plan, "metrics": metrics}


def new_figure():
    fig = plt.figure(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor(CANVAS)
    header(fig)
    return fig


def header(fig, eyebrow: str, title: str) -> None:
    fig.patches.append(
        plt.Rectangle((0, 0.925), 1, 0.075, transform=fig.transFigure, facecolor=NAVY, edgecolor="none", zorder=0)
    )
    fig.patches.append(
        plt.Rectangle((0, 0.925), 1, 0.006, transform=fig.transFigure, facecolor=GOLD, edgecolor="none", zorder=2)
    )
    fig.text(0.018, 0.968, "VANTAGE PROCESS GROUP", color=GOLD, fontsize=8, fontweight="semibold", va="center")
    fig.text(0.018, 0.942, title, color=WHITE, fontsize=16, fontweight="semibold", va="center")
    fig.text(0.982, 0.955, eyebrow, color="#D6DEE8", fontsize=8, ha="right", va="center")


def footer(fig, note: str) -> None:
    fig.text(
        0.018,
        0.012,
        "Synthetic portfolio dataset  ·  Not actual financial results  ·  Tanner Allred",
        color=MUTED,
        fontsize=7.5,
        va="center",
    )
    fig.text(0.982, 0.012, note, color=MUTED, fontsize=7.5, ha="right", va="center")


def rounded(fig, x, y, w, h, *, face=WHITE, edge=LINE, radius=0.008, z=1):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        transform=fig.transFigure,
        facecolor=face,
        edgecolor=edge,
        linewidth=0.8,
        mutation_aspect=fig.get_figheight() / fig.get_figwidth(),
        zorder=z,
        clip_on=False,
    )
    fig.patches.append(patch)
    return patch


def kpi(fig, x, y, w, h, label: str, value: str, note: str, note_color: str) -> None:
    rounded(fig, x, y, w, h)
    fig.patches.append(
        plt.Rectangle((x, y), 0.0045, h, transform=fig.transFigure, facecolor=note_color, edgecolor="none", zorder=3)
    )
    fig.text(x + 0.012, y + h - 0.028, label.upper(), color=MUTED, fontsize=7, fontweight="semibold", va="center")
    value_size = 16 if len(value) <= 10 else 12 if len(value) <= 16 else 9
    fig.text(x + 0.012, y + h * 0.48, value, color=NAVY, fontsize=value_size, fontweight="semibold", va="center")
    fig.text(x + 0.012, y + 0.02, note, color=note_color, fontsize=8, fontweight="medium", va="center")


def panel(fig, x, y, w, h, title: str, *, left=0.07, bottom=0.16, right=0.04, top=0.22):
    """Insets are fractions of the card, so axis labels stay inside the card."""
    rounded(fig, x, y, w, h)
    fig.text(x + 0.012, y + h - 0.028, title, color=NAVY, fontsize=10, fontweight="semibold", va="center")
    ax = fig.add_axes(
        [x + w * left, y + h * bottom, w * (1 - left - right), h * (1 - top - bottom)],
        zorder=3,
    )
    ax.set_facecolor(WHITE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(LINE)
        ax.spines[spine].set_linewidth(0.6)
    ax.tick_params(colors=MUTED, labelsize=7.5, length=0)
    ax.grid(axis="y", color="#EEF2F6", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    return ax


def quarterly(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        frame.groupby(["Year", "Quarter"], as_index=False)[["Revenue", "GrossProfit", "OpEx", "EBITDA"]]
        .sum()
        .sort_values(["Year", "Quarter"])
    )
    grouped["Label"] = grouped.apply(lambda row: f"Q{int(row.Quarter)} '{str(int(row.Year))[2:]}", axis=1)
    return grouped


def margin_bridge(actuals: pd.DataFrame) -> tuple[float, float, float, float]:
    def parts(year: int):
        sub = actuals[actuals["Year"] == year]
        grouped = sub.groupby("ProductLine")[["Revenue", "GrossProfit"]].sum()
        weight = grouped["Revenue"] / grouped["Revenue"].sum()
        margin = grouped["GrossProfit"] / grouped["Revenue"]
        return weight, margin

    weight_0, margin_0 = parts(2022)
    weight_1, margin_1 = parts(2025)
    aligned = pd.concat(
        [weight_0.rename("w0"), weight_1.rename("w1"), margin_0.rename("m0"), margin_1.rename("m1")],
        axis=1,
    ).fillna(0.0)
    mix = float(((aligned["w1"] - aligned["w0"]) * aligned["m0"]).sum())
    rate = float((aligned["w1"] * (aligned["m1"] - aligned["m0"])).sum())
    start = float(margin_0.mul(weight_0).sum())
    end = float(margin_1.mul(weight_1).sum())
    return start, mix, rate, end


def save(fig, name: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig.savefig(ASSETS / name, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


def page_executive(bundle: dict) -> None:
    actuals = bundle["actuals"]
    budget = bundle["plan"]
    budget = budget[budget["Scenario"] == "Budget"]
    metrics = bundle["metrics"]
    display = metrics["display"]
    fig = plt.figure(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor(CANVAS)
    header(fig, "FY2022 – FY2025", "Executive summary")
    footer(fig, "Actuals through December 2025")

    fy = display["fy2025"]
    vs = metrics["fy2025_vs_budget"]
    cards = [
        ("FY2025 revenue", fy["revenue"], f"{metrics['yoy']['2025']['revenue']} vs FY2024", TEAL),
        ("Vs FY2025 budget", vs["revenue"], vs["revenue_pct"], RED),
        ("Gross margin", fy["gross_margin"], f"{vs['gross_margin_bps']} vs budget", GREEN),
        ("EBITDA", fy["ebitda"], f"{vs['ebitda_pct']} vs budget", GREEN),
        ("EBITDA margin", fy["ebitda_margin"], f"{metrics['ebitda_margin_expansion_bps']} vs FY2022", TEAL),
        ("Operating expense", fy["opex"], f"{vs['opex']} vs budget", GREEN),
    ]
    for index, (label, value, note, color) in enumerate(cards):
        kpi(fig, 0.018 + index * 0.163, 0.785, 0.155, 0.125, label, value, note, color)

    act_q = quarterly(actuals)
    bud_q = quarterly(budget[budget["Year"] <= 2025])
    ax = panel(fig, 0.018, 0.40, 0.62, 0.36, "Quarterly revenue and EBITDA margin", left=0.08, right=0.10, bottom=0.18)
    x = np.arange(len(act_q))
    width = 0.38
    ax.bar(x - width / 2, act_q["Revenue"] / 1e6, width, color=TEAL, label="Actual", zorder=2)
    ax.bar(x + width / 2, bud_q["Revenue"].to_numpy() / 1e6, width, color=GOLD, label="Budget", zorder=2)
    ax.set_ylabel("Revenue ($M)", color=MUTED, fontsize=7.5)
    ax.set_xticks(x)
    ax.set_xticklabels(act_q["Label"], fontsize=6.5)
    ax.set_xlim(-0.6, len(act_q) - 0.4)
    twin = ax.twinx()
    margin = act_q["EBITDA"] / act_q["Revenue"] * 100
    twin.plot(x, margin, color=NAVY, linewidth=1.6, marker="o", markersize=3, label="EBITDA margin", zorder=3)
    twin.set_ylim(0, 32)
    twin.set_ylabel("EBITDA margin", color=MUTED, fontsize=7.5)
    twin.tick_params(colors=MUTED, labelsize=7, length=0)
    twin.spines["top"].set_visible(False)
    twin.spines["right"].set_color(LINE)
    twin.spines["left"].set_visible(False)
    twin.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0f}%")
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = twin.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, frameon=False, fontsize=7.5, loc="upper left", ncol=3)

    fy2025 = actuals[actuals["Year"] == 2025]
    product = fy2025.groupby("ProductLine")[["Revenue", "GrossProfit"]].sum().sort_values("Revenue")
    ax = panel(fig, 0.655, 0.40, 0.327, 0.36, "FY2025 revenue and gross margin by product", left=0.42, right=0.12, bottom=0.16, top=0.22)
    y = np.arange(len(product))
    ax.barh(y, product["Revenue"] / 1e6, color=TEAL, height=0.62, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(product.index, fontsize=7.5)
    ax.set_xlabel("$ millions", color=MUTED, fontsize=7.5)
    for index, (revenue, gp) in enumerate(zip(product["Revenue"], product["GrossProfit"])):
        ax.text(revenue / 1e6 + 0.4, index, f"{gp / revenue:.0%}", va="center", ha="left", color=NAVY, fontsize=7.5)
    ax.set_xlim(0, product["Revenue"].max() / 1e6 * 1.22)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#EEF2F6", linewidth=0.6)

    years = [2022, 2023, 2024, 2025]
    rounded(fig, 0.018, 0.045, 0.62, 0.33)
    fig.text(0.03, 0.342, "Annual P&L", color=NAVY, fontsize=10, fontweight="semibold")
    columns = ["", "FY2022", "FY2023", "FY2024", "FY2025"]
    rows = ["Revenue", "YoY", "vs Budget", "Gross margin", "EBITDA", "EBITDA margin"]
    table = []
    for year in years:
        block = display[f"fy{year}"]
        yoy = "—" if year == 2022 else metrics["yoy"][str(year)]["revenue"]
        versus = pct(
            metrics["annual_actuals"][str(year)]["revenue"] / metrics["annual_budget"][str(year)]["revenue"] - 1,
            signed=True,
        )
        table.append([block["revenue"], yoy, versus, block["gross_margin"], block["ebitda"], block["ebitda_margin"]])
    ax = fig.add_axes([0.03, 0.06, 0.59, 0.27], zorder=3)
    ax.axis("off")
    rendered = ax.table(
        cellText=[[rows[r]] + [table[c][r] for c in range(4)] for r in range(6)],
        colLabels=columns,
        loc="upper left",
        cellLoc="right",
        colLoc="right",
        bbox=[0, 0, 1, 1],
    )
    rendered.auto_set_font_size(False)
    rendered.set_fontsize(8)
    for (row, col), cell in rendered.get_celld().items():
        cell.set_edgecolor(WHITE)
        cell.set_linewidth(0)
        cell.set_facecolor(WHITE if row % 2 == 0 else SOFT)
        cell.get_text().set_color(NAVY if col == 0 or row == 0 else INK)
        if row == 0:
            cell.set_facecolor(NAVY)
            cell.get_text().set_color(WHITE)
            cell.get_text().set_fontweight("semibold")
        if col == 0 and row > 0:
            cell.get_text().set_ha("left")
            cell.set_text_props(fontweight="medium")

    region = (
        fy2025.groupby("Region")[["Revenue", "EBITDA"]]
        .sum()
        .reindex(["North America", "EMEA", "Asia Pacific", "Latin America"])
    )
    prior = (
        actuals[actuals["Year"] == 2024]
        .groupby("Region")["Revenue"]
        .sum()
        .reindex(region.index)
    )
    ax = panel(fig, 0.655, 0.045, 0.327, 0.33, "FY2025 revenue by region", left=0.36, right=0.28, bottom=0.16, top=0.24)
    y = np.arange(len(region))
    ax.barh(y, region["Revenue"] / 1e6, color=[TEAL, BLUE, GOLD, SLATE], height=0.62, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(region.index, fontsize=7.5)
    ax.set_xlabel("$ millions", color=MUTED, fontsize=7.5)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#EEF2F6", linewidth=0.6)
    for index, (name, revenue) in enumerate(region["Revenue"].items()):
        growth = revenue / prior.loc[name] - 1
        margin = region.loc[name, "EBITDA"] / revenue
        ax.text(
            revenue / 1e6 + 0.6,
            index,
            f"{growth:+.0%}   {margin:.0%} margin",
            va="center",
            color=NAVY,
            fontsize=7,
        )
    ax.set_xlim(0, region["Revenue"].max() / 1e6 * 1.48)
    save(fig, "01_executive_summary.png")


def page_forecast(bundle: dict) -> None:
    actuals = bundle["actuals"]
    plan = bundle["plan"]
    metrics = bundle["metrics"]
    display = metrics["display"]
    fig = plt.figure(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor(CANVAS)
    header(fig, "Origin: December 2025 close", "Revenue forecast and scenarios")
    footer(fig, "80% interval is the 10th to 90th percentile of simulated FY2026 revenue")

    forecast = metrics["forecast_2026"]
    backtest = metrics["backtest"]
    cards = [
        ("FY2026 base", display["fy2026_base"]["revenue"], f"{forecast['base_vs_fy2025']} vs FY2025", TEAL),
        ("Vs FY2026 budget", forecast["base_vs_budget"], forecast["base_vs_budget_pct"], TEAL),
        ("Upside", display["fy2026_upside"]["revenue"], display["fy2026_upside"]["ebitda_margin"] + " EBITDA margin", GREEN),
        ("Downside", display["fy2026_downside"]["revenue"], display["fy2026_downside"]["ebitda_margin"] + " EBITDA margin", RED),
        ("80% revenue interval", forecast["interval_80"].replace(" to ", "–"), "10th to 90th percentile", NAVY),
        ("Holdout accuracy", backtest["wape"] + " WAPE", backtest["mape"] + " MAPE   " + backtest["rmse"] + " RMSE", TEAL),
    ]
    # The interval card uses a shortened label; the full string is still the note.
    for index, (label, value, note, color) in enumerate(cards):
        kpi(fig, 0.018 + index * 0.163, 0.785, 0.155, 0.125, label, value, note, color)

    monthly_actual = actuals.groupby("Date")["Revenue"].sum().sort_index()
    monthly_budget = (
        plan[plan["Scenario"] == "Budget"].groupby("Date")["Revenue"].sum().sort_index()
    )
    paths = {}
    for scenario in ("Forecast - Base", "Forecast - Upside", "Forecast - Downside"):
        paths[scenario] = plan[plan["Scenario"] == scenario].groupby("Date")["Revenue"].sum().sort_index()

    ax = panel(fig, 0.018, 0.40, 0.964, 0.36, "Monthly revenue, budget, and the FY2026 fan", left=0.05, right=0.02, bottom=0.16)
    history = monthly_actual[monthly_actual.index >= "2023-01-01"]
    budget_line = monthly_budget[monthly_budget.index >= "2023-01-01"]
    ax.plot(history.index, history / 1e6, color=TEAL, linewidth=2.0, label="Actual", zorder=3)
    ax.plot(budget_line.index, budget_line / 1e6, color=GOLD, linewidth=1.4, linestyle="--", label="Budget", zorder=2)
    base = paths["Forecast - Base"]
    up = paths["Forecast - Upside"]
    down = paths["Forecast - Downside"]
    ax.fill_between(base.index, down / 1e6, up / 1e6, color=TEAL, alpha=0.15, linewidth=0, label="80% interval", zorder=1)
    ax.plot(base.index, base / 1e6, color=NAVY, linewidth=2.0, label="Base", zorder=3)
    ax.plot(up.index, up / 1e6, color=GREEN, linewidth=1.2, label="Upside", zorder=3)
    ax.plot(down.index, down / 1e6, color=RED, linewidth=1.2, label="Downside", zorder=3)
    ax.axvline(pd.Timestamp("2026-01-01"), color=LINE, linewidth=0.8)
    ax.set_xlim(pd.Timestamp("2023-01-01"), pd.Timestamp("2026-12-15"))
    ax.set_ylabel("$ millions", color=MUTED, fontsize=7.5)
    ax.legend(frameon=False, fontsize=7.5, ncol=6, loc="upper left")
    ax.set_ylim(0, 36)

    back = plan[plan["Scenario"] == "Backtest"].groupby("Date")["Revenue"].sum().sort_index()
    actual_2025 = monthly_actual[monthly_actual.index.year == 2025]
    ax = panel(
        fig,
        0.018,
        0.045,
        0.48,
        0.33,
        f"FY2025 holdout at the Dec 2024 close   ·   bias {backtest['bias']}",
        left=0.08,
        right=0.03,
        bottom=0.18,
    )
    ax.plot(actual_2025.index, actual_2025 / 1e6, color=TEAL, linewidth=2.0, marker="o", markersize=3.5, label="Actual")
    ax.plot(back.index, back / 1e6, color=NAVY, linewidth=1.5, linestyle="--", marker="o", markersize=3, label="Backtest")
    ax.set_ylabel("$ millions", color=MUTED, fontsize=7.5)
    ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax.set_ylim(10, 34)

    rounded(fig, 0.515, 0.045, 0.467, 0.33)
    fig.text(0.53, 0.342, "FY2026 scenario P&L", color=NAVY, fontsize=10, fontweight="semibold")
    scenario_rows = [
        ("Budget", display["fy2026_budget"]),
        ("Downside", display["fy2026_downside"]),
        ("Base", display["fy2026_base"]),
        ("Upside", display["fy2026_upside"]),
    ]
    ax = fig.add_axes([0.53, 0.07, 0.43, 0.25], zorder=3)
    ax.axis("off")
    body = [
        [name, block["revenue"], block["gross_margin"], block["ebitda"], block["ebitda_margin"]]
        for name, block in scenario_rows
    ]
    rendered = ax.table(
        cellText=body,
        colLabels=["Scenario", "Revenue", "Gross margin", "EBITDA", "EBITDA margin"],
        loc="upper center",
        cellLoc="right",
        bbox=[0, 0.05, 1, 0.92],
    )
    rendered.auto_set_font_size(False)
    rendered.set_fontsize(8)
    for (row, col), cell in rendered.get_celld().items():
        cell.set_edgecolor(WHITE)
        cell.set_facecolor(WHITE if row % 2 == 0 else SOFT)
        if row == 0:
            cell.set_facecolor(NAVY)
            cell.get_text().set_color(WHITE)
            cell.get_text().set_fontweight("semibold")
        elif col == 0:
            cell.get_text().set_ha("left")
            cell.get_text().set_color(NAVY)
            cell.get_text().set_fontweight("medium")
        if row == 3:
            cell.set_facecolor("#E7F2F2")
    save(fig, "02_forecast_scenarios.png")


def page_variance(bundle: dict) -> None:
    actuals = bundle["actuals"]
    budget = bundle["plan"]
    budget = budget[budget["Scenario"] == "Budget"]
    metrics = bundle["metrics"]
    display = bundle["metrics"]["display"]
    fig = plt.figure(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor(CANVAS)
    header(fig, "Budget set before each year", "Variance and margin drivers")
    footer(fig, "FY2025 missed revenue and beat profit")

    vs = metrics["fy2025_vs_budget"]
    cards = [
        ("FY2025 revenue var.", vs["revenue"], vs["revenue_pct"], RED),
        ("Gross margin vs budget", vs["gross_margin_bps"], display["fy2025"]["gross_margin"] + " actual", GREEN),
        ("EBITDA vs budget", vs["ebitda"], vs["ebitda_pct"], GREEN),
        ("OpEx vs budget", vs["opex"], "under plan is favorable", GREEN),
        ("Mix effect, FY22–FY25", metrics["margin_bridge_fy2022_fy2025"]["mix_effect"], "software, parts, and service", TEAL),
        ("Rate effect, FY22–FY25", metrics["margin_bridge_fy2022_fy2025"]["rate_effect"], "price and cost inside the line", BLUE),
    ]
    for index, (label, value, note, color) in enumerate(cards):
        kpi(fig, 0.018 + index * 0.163, 0.785, 0.155, 0.125, label, value, note, color)

    act_q = quarterly(actuals)
    bud_q = quarterly(budget[budget["Year"] <= 2025])
    variance = act_q["Revenue"].to_numpy() - bud_q["Revenue"].to_numpy()
    ax = panel(fig, 0.018, 0.40, 0.62, 0.36, "Quarterly revenue versus budget")
    colors = [GREEN if value >= 0 else RED for value in variance]
    ax.bar(np.arange(len(variance)), variance / 1e6, color=colors, width=0.72, zorder=2)
    ax.axhline(0, color=LINE, linewidth=0.8)
    ax.set_xticks(np.arange(len(variance)))
    ax.set_xticklabels(act_q["Label"], fontsize=6.5)
    ax.set_ylabel("Variance ($M)", color=MUTED, fontsize=7.5)

    start, mix, rate, end = margin_bridge(actuals)
    ax = panel(fig, 0.655, 0.40, 0.327, 0.36, "Gross-margin bridge, FY2022 to FY2025")
    steps = [start, mix, rate, end]
    labels = ["FY2022", "Mix", "Rate", "FY2025"]
    cumulative = start
    for index, value in enumerate(steps):
        if index in (0, 3):
            ax.bar(index, value * 100, color=NAVY, width=0.62, zorder=2)
            shown = value
        else:
            ax.bar(index, value * 100, bottom=cumulative * 100, color=TEAL if value >= 0 else RED, width=0.62, zorder=2)
            shown = cumulative + value
            cumulative += value
        ax.text(index, shown * 100 + 0.6, f"{shown * 100:.1f}%" if index in (0, 3) else bps(value), ha="center", color=NAVY, fontsize=7.5)
    ax.plot([0.3, 1], [start * 100, start * 100], color=LINE, linewidth=0.7)
    ax.plot([1.3, 2], [(start + mix) * 100, (start + mix) * 100], color=LINE, linewidth=0.7)
    ax.set_xticks(range(4))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 58)
    ax.set_ylabel("Gross margin", color=MUTED, fontsize=7.5)
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0f}%")

    ax = panel(fig, 0.018, 0.045, 0.50, 0.33, "Gross margin by product line", left=0.10, right=0.28, bottom=0.16)
    palette = {
        "Process Equipment": BLUE,
        "Aftermarket Parts": GOLD,
        "Field Service Contracts": TEAL,
        "Industrial Software": GREEN,
        "Professional Services": SLATE,
    }
    for name, color in palette.items():
        series = (
            actuals[actuals["ProductLine"] == name]
            .groupby("Year")[["Revenue", "GrossProfit"]]
            .sum()
            .sort_index()
        )
        ax.plot(series.index, series["GrossProfit"] / series["Revenue"] * 100, color=color, linewidth=1.8, marker="o", markersize=3.5)
    ax.set_ylabel("Gross margin", color=MUTED, fontsize=7.5)
    ax.set_xticks([2022, 2023, 2024, 2025])
    ax.set_xlim(2021.85, 2026.15)
    ax.yaxis.set_major_formatter(lambda value, _pos: f"{value:.0f}%")
    short = {
        "Process Equipment": "Equipment",
        "Aftermarket Parts": "Parts",
        "Field Service Contracts": "Service",
        "Industrial Software": "Software",
        "Professional Services": "Services",
    }
    for name, color in palette.items():
        series = actuals[actuals["ProductLine"] == name].groupby("Year")[["Revenue", "GrossProfit"]].sum()
        level = float(series.loc[2025, "GrossProfit"] / series.loc[2025, "Revenue"] * 100)
        ax.text(2025.12, level, short[name], color=color, fontsize=7, va="center")
    ax.set_ylim(20, 85)

    fy = actuals[actuals["Year"] == 2025].groupby("ProductLine")[["Revenue"]].sum()
    bud = budget[(budget["Year"] == 2025)].groupby("ProductLine")[["Revenue"]].sum()
    order = fy.sort_values("Revenue").index
    delta = (fy.loc[order, "Revenue"] - bud.loc[order, "Revenue"]) / 1e6
    ax = panel(fig, 0.535, 0.045, 0.447, 0.33, "FY2025 revenue variance by product line", left=0.38, right=0.06, bottom=0.16, top=0.24)
    y = np.arange(len(delta))
    ax.barh(y, delta, color=[GREEN if value >= 0 else RED for value in delta], height=0.62, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(order, fontsize=7.5)
    ax.axvline(0, color=LINE, linewidth=0.8)
    ax.set_xlabel("Variance ($M)", color=MUTED, fontsize=7.5)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#EEF2F6", linewidth=0.6)
    save(fig, "03_variance_and_margins.png")


def schema_box(fig, x, y, w, h, title: str, rows: list[str], accent: str, footnote: str | None = None) -> None:
    rounded(fig, x, y, w, h, z=2)
    fig.patches.append(
        plt.Rectangle((x, y + h - 0.032), w, 0.032, transform=fig.transFigure, facecolor=accent, edgecolor="none", zorder=3)
    )
    fig.text(x + 0.008, y + h - 0.016, title, color=WHITE, fontsize=8, fontweight="semibold", va="center", zorder=4)
    for index, row in enumerate(rows):
        fig.text(x + 0.008, y + h - 0.052 - index * 0.022, row, color=INK, fontsize=6.7, va="center", fontfamily="DejaVu Sans", zorder=4)
    if footnote:
        fig.text(x + 0.008, y + 0.016, footnote, color=MUTED, fontsize=6.4, va="center", zorder=4)


def connector(fig, start, end) -> None:
    arrow = FancyArrowPatch(
        start,
        end,
        transform=fig.transFigure,
        arrowstyle="-|>",
        mutation_scale=8,
        linewidth=0.8,
        color="#9AA8B5",
        connectionstyle="arc3,rad=0.0",
        zorder=1,
    )
    fig.add_artist(arrow)


def page_model(bundle: dict) -> None:
    metrics = bundle["metrics"]
    counts = metrics["row_counts"]
    fig = plt.figure(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor(CANVAS)
    header(fig, "PBIP  ·  TMDL semantic model", "Star schema")
    footer(fig, "Filter flows from the dimension to the fact  ·  single active path")

    fig.text(
        0.018,
        0.895,
        "Monthly grain   ·   region × product line × segment   ·   actuals separated from budget, backtest, and forecast",
        color=MUTED,
        fontsize=8.5,
    )

    schema_box(
        fig, 0.30, 0.72, 0.40, 0.17, "dim_date",
        ["Date   PK", "FiscalYearLabel  ·  YearQuarter", "MonthYear  ·  CalendarStage"],
        NAVY, f"{counts['dim_date']:,} days    2022-01-01 to 2026-12-31",
    )
    schema_box(
        fig, 0.02, 0.46, 0.24, 0.22, "dim_region",
        ["RegionKey   PK", "Region", "RegionCode", "ManagementGroup", "Currency"],
        BLUE, f"{counts['dim_region']} regions",
    )
    schema_box(
        fig, 0.02, 0.20, 0.24, 0.22, "dim_customer_segment",
        ["SegmentKey   PK", "Segment", "SegmentCode", "BuyingMotion"],
        BLUE, f"{counts['dim_customer_segment']} segments",
    )
    schema_box(
        fig, 0.74, 0.46, 0.24, 0.22, "dim_product_line",
        ["ProductLineKey   PK", "ProductLine", "RevenueType", "UnitOfMeasure", "PortfolioRole"],
        BLUE, f"{counts['dim_product_line']} product lines",
    )
    schema_box(
        fig, 0.74, 0.20, 0.24, 0.22, "Scenario",
        ["Scenario   PK", "Budget", "Backtest", "Forecast - Downside", "Forecast - Base / Upside"],
        GOLD, "Entered in Power Query",
    )
    schema_box(
        fig, 0.30, 0.42, 0.40, 0.26, "fact_revenue_actuals",
        ["Date, RegionKey, ProductLineKey, SegmentKey", "Revenue, COGS, GrossProfit", "OpEx, EBITDA", "VolumeUnits"],
        TEAL, f"{counts['fact_revenue_actuals']:,} rows   ·   FY2022–FY2025 actuals",
    )
    schema_box(
        fig, 0.30, 0.16, 0.40, 0.23, "fact_budget_forecast",
        ["Same keys, plus Scenario", "Budget FY2022–FY2026", "Backtest FY2025", "Base, Upside, Downside FY2026"],
        "#8A6A2F", f"{counts['fact_budget_forecast']:,} rows",
    )

    connector(fig, (0.50, 0.72), (0.50, 0.685))
    connector(fig, (0.26, 0.56), (0.30, 0.56))
    connector(fig, (0.26, 0.32), (0.30, 0.30))
    connector(fig, (0.74, 0.56), (0.70, 0.56))
    connector(fig, (0.74, 0.32), (0.70, 0.28))

    fig.text(0.018, 0.155, "_MEASURES", color=NAVY, fontsize=8, fontweight="semibold")
    folders = [
        ("Revenue", "YTD, PY, YoY, MoM, R3M, R12M"),
        ("Margin", "Gross profit, OpEx, EBITDA, bps"),
        ("Budget", "Variance $ and %"),
        ("Forecast", "Base, Upside, Downside"),
        ("Accuracy", "WAPE, MAPE, RMSE"),
    ]
    for index, (name, detail) in enumerate(folders):
        x = 0.018 + index * 0.196
        rounded(fig, x, 0.045, 0.186, 0.095, face=SOFT, edge=LINE)
        fig.text(x + 0.01, 0.112, name, color=NAVY, fontsize=8, fontweight="semibold")
        fig.text(x + 0.01, 0.075, detail, color=MUTED, fontsize=6.7)

    save(fig, "04_data_model_star_schema.png")


def main() -> None:
    bundle = load()
    page_executive(bundle)
    page_forecast(bundle)
    page_variance(bundle)
    page_model(bundle)
    for name in (
        "01_executive_summary.png",
        "02_forecast_scenarios.png",
        "03_variance_and_margins.png",
        "04_data_model_star_schema.png",
    ):
        path = ASSETS / name
        print(f"{name}  {path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
