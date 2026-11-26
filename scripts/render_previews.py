"""Draw the four dashboard previews from the published Census figures.

    python scripts/render_previews.py
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["text.parse_math"] = False
import pandas as pd
from matplotlib.patches import FancyBboxPatch, Rectangle

from retail_lib import ASSETS_DIR, DATA_DIR, load_sales_panel, month_label, read_csv

NAVY = "#0B1F33"
TEAL = "#0F6E7A"
GOLD = "#A16207"
INK = "#142033"
MUTED = "#5E6E80"
GREEN = "#0E7A45"
RED = "#B42318"
GRID = "#E2E8F0"
SA = "#8AA0B8"
BAND = "#D7EEF2"


def load() -> dict:
    panel = load_sales_panel("SalesNSA")
    sa = load_sales_panel("SalesSA")
    sectors = read_csv("dim_sector.csv").sort_values("SortOrder")
    names = dict(zip(sectors["SectorKey"], sectors["SectorShort"]))
    forecast = read_csv("fact_forecast.csv")
    total_fc = read_csv("forecast_total.csv")
    backtest = read_csv("fact_backtest.csv")
    total_bt = read_csv("backtest_total.csv")
    snapshot = json.loads((DATA_DIR / "kpi_snapshot.json").read_text(encoding="utf-8"))
    sources = json.loads((DATA_DIR / "data_sources.json").read_text(encoding="utf-8"))
    return {
        "panel": panel,
        "sa": sa,
        "names": names,
        "order": list(sectors["SectorKey"]),
        "forecast": forecast,
        "total_fc": total_fc,
        "backtest": backtest,
        "total_bt": total_bt,
        "literals": snapshot["literals"],
        "retrieved": sources["retrieved_at"],
    }


def billions(series: pd.Series) -> pd.Series:
    return series.astype(float) / 1000.0


def new_figure(title: str, subtitle: str):
    fig = plt.figure(figsize=(20, 11.25), dpi=160)
    fig.patch.set_facecolor("#F4F7FB")
    header = fig.add_axes([0, 0.905, 1, 0.095])
    header.set_xlim(0, 1)
    header.set_ylim(0, 1)
    header.axis("off")
    header.add_patch(Rectangle((0, 0), 1, 1, color=NAVY))
    header.add_patch(Rectangle((0, 0), 0.008, 1, color=GOLD))
    header.text(0.028, 0.64, title, color="white", fontsize=22, fontweight="bold", va="center")
    header.text(0.028, 0.26, subtitle, color="#D5E4EA", fontsize=11, va="center")
    return fig


def footer(fig, retrieved: str) -> None:
    foot = fig.add_axes([0, 0, 1, 0.038])
    foot.set_xlim(0, 1)
    foot.set_ylim(0, 1)
    foot.axis("off")
    foot.add_patch(Rectangle((0, 0), 1, 1, color="#E7EEF5"))
    foot.text(
        0.02,
        0.5,
        "U.S. Census Bureau, Monthly Retail Trade Survey and Advance Monthly Retail Trade Survey. "
        f"Nominal millions of dollars. Retrieved {retrieved}.",
        color=MUTED,
        fontsize=8.5,
        va="center",
    )


def card(fig, x, y, w, h, eyebrow, value, note, accent=TEAL):
    ax = fig.add_axes([x, y, w, h])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(
        FancyBboxPatch(
            (0.0, 0.02),
            1.0,
            0.96,
            boxstyle="round,pad=0.012,rounding_size=0.04",
            facecolor="white",
            edgecolor="#E2E8F0",
            linewidth=1.0,
        )
    )
    ax.add_patch(Rectangle((0.0, 0.08), 0.015, 0.84, color=accent))
    ax.text(0.07, 0.74, eyebrow.upper(), color=MUTED, fontsize=8.2, fontweight="bold", va="center")
    ax.text(0.07, 0.42, value, color=NAVY, fontsize=16, fontweight="bold", va="center")
    ax.text(0.07, 0.16, note, color=MUTED, fontsize=8.2, va="center")
    return ax


def style_axis(ax, title: str) -> None:
    ax.set_facecolor("white")
    ax.set_title(title, loc="left", color=NAVY, fontsize=13, fontweight="bold", pad=10)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(INK)


def save(fig, name: str) -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(ASSETS_DIR / name, dpi=160)
    plt.close(fig)


def executive(data: dict) -> None:
    lit = data["literals"]
    fig = new_figure("Executive Overview", "U.S. retail and food services  ·  not seasonally adjusted")
    card(fig, 0.025, 0.755, 0.23, 0.13, "Latest month", f"${lit['latest_sales_billions']}B", lit["latest_month_label"])
    card(fig, 0.265, 0.755, 0.23, 0.13, "Vs last year", lit["latest_yoy"], f"October prior year {lit['latest_prior_year_millions']} million", GREEN)
    card(fig, 0.505, 0.755, 0.23, 0.13, "Vs last month", lit["latest_mom"], "Month to month", TEAL)
    card(fig, 0.745, 0.755, 0.23, 0.13, "Last 12 months", f"${lit['ttm_billions']}B", f"Year over year {lit['ttm_yoy']}", GOLD)

    total = billions(data["panel"].sum(axis=1))
    sa = billions(data["sa"].sum(axis=1))
    recent = total.loc[total.index >= total.index.max() - pd.DateOffset(months=95)]
    sa_recent = sa.reindex(recent.index)
    ax = fig.add_axes([0.04, 0.30, 0.55, 0.40])
    ax.plot(recent.index, recent.values, color=TEAL, linewidth=2.2, label="Not adjusted")
    ax.plot(sa_recent.index, sa_recent.values, color=SA, linewidth=1.8, label="Seasonally adjusted")
    style_axis(ax, "Monthly sales, last 8 years")
    ax.set_ylabel("Billion dollars", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_ylim(bottom=0)

    last = data["panel"].index.max()
    prev = last - pd.DateOffset(years=1)
    yoy = (data["panel"].loc[last] / data["panel"].loc[prev] - 1).sort_values()
    labels = [data["names"][key] for key in yoy.index]
    colors = [GREEN if value >= 0 else RED for value in yoy.values]
    ax2 = fig.add_axes([0.64, 0.30, 0.32, 0.40])
    ax2.barh(labels, yoy.values * 100, color=colors, height=0.72)
    ax2.axvline(0, color=NAVY, linewidth=0.8)
    style_axis(ax2, f"Change from {month_label(prev, full=True)}")
    ax2.set_xlabel("Percent", color=MUTED, fontsize=9)
    ax2.grid(axis="x", color=GRID, linewidth=0.8)
    ax2.grid(axis="y", visible=False)

    note = fig.add_axes([0.04, 0.07, 0.92, 0.18])
    note.set_xlim(0, 1)
    note.set_ylim(0, 1)
    note.axis("off")
    note.add_patch(
        FancyBboxPatch((0, 0.08), 1, 0.84, boxstyle="round,pad=0.008,rounding_size=0.02", facecolor="white", edgecolor="#E2E8F0")
    )
    note.text(
        0.03,
        0.62,
        f"Year to date is ${lit['ytd_billions']}B, {lit['ytd_yoy']} from last year. "
        f"{lit['largest_sector']} is the largest category at ${lit['largest_sector_billions']}B ({lit['largest_sector_share']}).",
        color=INK,
        fontsize=11,
        va="center",
    )
    note.text(
        0.03,
        0.30,
        f"{lit['fastest_sector']} grew the fastest ({lit['fastest_sector_yoy']}). "
        f"{lit['slowest_sector']} was slowest ({lit['slowest_sector_yoy']}). "
        "Gasoline moves with fuel prices.",
        color=MUTED,
        fontsize=11,
        va="center",
    )
    footer(fig, data["retrieved"])
    save(fig, "01-executive-overview.png")


def sectors(data: dict) -> None:
    lit = data["literals"]
    fig = new_figure(
        "Sector Performance",
        f"Last 12 months: ${lit['ttm_billions']}B, {lit['ttm_yoy']} from the year before",
    )
    last = data["panel"].index.max()
    start = last - pd.DateOffset(months=11)
    prior_end = start - pd.DateOffset(months=1)
    prior_start = prior_end - pd.DateOffset(months=11)
    ttm = data["panel"].loc[start:last].sum().sort_values()
    prior = data["panel"].loc[prior_start:prior_end].sum()
    yoy = (ttm / prior.reindex(ttm.index) - 1).sort_values()
    labels = [data["names"][key] for key in ttm.index]
    ax = fig.add_axes([0.08, 0.10, 0.40, 0.74])
    ax.barh(labels, billions(ttm).values, color=TEAL, height=0.72)
    style_axis(ax, "Last 12 months")
    ax.set_xlabel("Billion dollars", color=MUTED, fontsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)

    labels2 = [data["names"][key] for key in yoy.index]
    colors = [GREEN if value >= 0 else RED for value in yoy.values]
    ax2 = fig.add_axes([0.58, 0.10, 0.38, 0.74])
    ax2.barh(labels2, yoy.values * 100, color=colors, height=0.72)
    ax2.axvline(0, color=NAVY, linewidth=0.8)
    style_axis(ax2, "Last 12 months vs the prior 12")
    ax2.set_xlabel("Percent", color=MUTED, fontsize=9)
    ax2.grid(axis="x", color=GRID, linewidth=0.8)
    ax2.grid(axis="y", visible=False)
    footer(fig, data["retrieved"])
    save(fig, "02-sector-performance.png")


def forecast(data: dict) -> None:
    lit = data["literals"]
    fig = new_figure("12-Month Forecast", f"{lit['forecast_window']}  ·  sectors add up to the total")
    card(fig, 0.025, 0.755, 0.23, 0.13, "Next 12 months", f"${lit['forward_12_billions']}B", lit["forecast_window"])
    card(fig, 0.265, 0.755, 0.23, 0.13, "Vs latest 12 months", lit["forward_vs_prior"], f"Latest 12 months ${lit['prior_12_billions']}B", GREEN)
    card(fig, 0.505, 0.755, 0.23, 0.13, "Test-year miss", lit["holdout_mape"], f"Same month last year {lit['seasonal_naive_mape']}", GOLD)
    season_word = "multiplicative" if lit["model_seasonal"] == "mul" else "additive"
    card(fig, 0.745, 0.755, 0.23, 0.13, "Setup", lit["model_window"], f"{season_word}, {lit['model_damped']} trend")

    history = billions(data["panel"].sum(axis=1))
    history = history.loc[history.index >= history.index.max() - pd.DateOffset(months=71)]
    fc = data["total_fc"].copy()
    fc["Date"] = pd.to_datetime(fc["Date"])
    fc = fc.sort_values("Date")
    ax = fig.add_axes([0.06, 0.50, 0.88, 0.23])
    ax.fill_between(fc["Date"], fc["Lower80"] / 1000, fc["Upper80"] / 1000, color=BAND, label="80% range")
    ax.plot(history.index, history.values, color=TEAL, linewidth=2.2, label="Actual")
    ax.plot(fc["Date"], fc["ForecastNSA"] / 1000, color=GOLD, linewidth=2.2, label="Forecast")
    style_axis(ax, "Recent sales and the next 12 months")
    ax.set_ylabel("Billion dollars", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8.5, ncol=3, loc="upper left")
    ax.set_ylim(bottom=0)

    last = data["panel"].index.max()
    prior = data["panel"].loc[last - pd.DateOffset(months=11) : last].sum()
    forward = data["forecast"].groupby("SectorKey")["ForecastNSA"].sum()
    order = forward.sort_values().index
    labels = [data["names"][key] for key in order]
    ax2 = fig.add_axes([0.10, 0.055, 0.84, 0.36])
    ypos = range(len(order))
    ax2.barh([y - 0.16 for y in ypos], billions(prior.reindex(order)).values, height=0.32, color=SA, label="Latest 12 months")
    ax2.barh([y + 0.16 for y in ypos], billions(forward.reindex(order)).values, height=0.32, color=TEAL, label="Next 12 months")
    ax2.set_yticks(list(ypos), labels)
    style_axis(ax2, "Next 12 months against the latest 12, by sector")
    ax2.legend(frameon=False, fontsize=8, loc="lower right")
    ax2.grid(axis="x", color=GRID, linewidth=0.8)
    ax2.grid(axis="y", visible=False)
    footer(fig, data["retrieved"])
    save(fig, "03-forecast-outlook.png")


def accuracy(data: dict) -> None:
    lit = data["literals"]
    fig = new_figure("Forecast Accuracy", f"Tested on {lit['holdout_window']}, after the setup was chosen")
    card(fig, 0.02, 0.755, 0.155, 0.13, "Average miss", lit["holdout_mape"], "MAPE")
    card(fig, 0.185, 0.755, 0.155, 0.13, "Weighted miss", lit["holdout_wape"], "WAPE", TEAL)
    card(fig, 0.35, 0.755, 0.155, 0.13, "Last-year guess", lit["seasonal_naive_mape"], f"{lit['mape_skill']} less error", GREEN)
    card(fig, 0.515, 0.755, 0.155, 0.13, "Typical miss", lit["holdout_mae"], "Million dollars", GOLD)
    card(fig, 0.68, 0.755, 0.155, 0.13, "Average gap", lit["holdout_bias"], "Forecast minus actual", RED)
    card(fig, 0.845, 0.755, 0.135, 0.13, "Inside 80% range", lit["interval_coverage"], "Of test months", TEAL)

    bt = data["total_bt"].copy()
    bt["Date"] = pd.to_datetime(bt["Date"])
    bt = bt.sort_values("Date")
    ax = fig.add_axes([0.06, 0.50, 0.88, 0.23])
    ax.fill_between(bt["Date"], bt["Lower80"] / 1000, bt["Upper80"] / 1000, color=BAND, label="80% range")
    ax.plot(bt["Date"], bt["ActualNSA"] / 1000, color=NAVY, marker="o", linewidth=2.1, label="Actual")
    ax.plot(bt["Date"], bt["ForecastNSA"] / 1000, color=GOLD, marker="o", linewidth=2.1, label="Forecast")
    ax.plot(bt["Date"], bt["SeasonalNaiveNSA"] / 1000, color=SA, marker="o", linewidth=1.6, label="Same month last year")
    style_axis(ax, "The test year")
    ax.set_ylabel("Billion dollars", color=MUTED, fontsize=9)
    ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper left")

    rows = []
    for key, part in data["backtest"].groupby("SectorKey"):
        ape = (part["ForecastNSA"] - part["ActualNSA"]).abs() / part["ActualNSA"]
        rows.append((data["names"][key], float(ape.mean()) * 100))
    rows.sort()
    ax2 = fig.add_axes([0.12, 0.055, 0.82, 0.36])
    ax2.barh([row[0] for row in rows], [row[1] for row in rows], color=TEAL, height=0.7)
    ax2.axvline(float(lit["holdout_mape"].rstrip("%")), color=GOLD, linewidth=1.4, label="All-sector average")
    style_axis(ax2, "Average percent miss by sector")
    ax2.set_xlabel("Percent", color=MUTED, fontsize=9)
    ax2.legend(frameon=False, fontsize=8, loc="lower right")
    ax2.grid(axis="x", color=GRID, linewidth=0.8)
    ax2.grid(axis="y", visible=False)
    footer(fig, data["retrieved"])
    save(fig, "04-forecast-accuracy.png")


def main() -> None:
    data = load()
    executive(data)
    sectors(data)
    forecast(data)
    accuracy(data)
    print(f"Wrote four previews in {ASSETS_DIR}")


if __name__ == "__main__":
    main()
