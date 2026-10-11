"""Render retained Azure query results; this is an export, not a Portal screenshot."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

THAILAND = timezone(timedelta(hours=7))


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(THAILAND)


def main():
    data = json.loads(Path("reports/dashboard-cloud-data.json").read_text())
    panels = data["panels"]
    evidence = json.loads(Path("reports/injected-drift-evidence.json").read_text())
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, grid = plt.subplots(3, 2, figsize=(15, 11), constrained_layout=True)
    axes = grid.ravel()
    fig.suptitle("ITCS355 Lab 4 | Actual Azure log dashboard export\n"
                 "Endpoint: itcs355-6688012-lab4 | 12 October 2026 | Thailand time (UTC+7)",
                 fontsize=17, fontweight="bold")
    for index in range(4):
        rows = sorted(panels[index]["rows"], key=lambda row: row["TimeGenerated"])
        dates = [timestamp(row["TimeGenerated"]) for row in rows]
        axis = axes[index]
        if index == 0:
            axis.bar(dates, [row["RequestsPerSecond"] for row in rows], width=0.0005, color="#1768ac")
            axis.set_ylabel("Requests / second (batch requests)")
        elif index == 1:
            for field, color in (("Error4xx", "#c98100"), ("Error5xx", "#bf2a2a")):
                axis.scatter(dates, [100 * row[field] for row in rows], label=field, color=color)
            axis.set_ylabel("Error fraction (%)")
            axis.set_ylim(-0.05, 1.05)
            axis.legend()
        elif index == 2:
            for field, color in (("p50", "#29916d"), ("p95", "#1768ac"), ("p99", "#bf2a2a")):
                axis.scatter(dates, [row[field] for row in rows], label=field, color=color)
            axis.set_ylabel("Gateway latency (ms)")
            axis.legend()
        else:
            axis.scatter(dates, [row["MeanTemperature"] for row in rows], color="#1768ac")
            axis.set_ylabel("temp_c mean (C), trailing 5-minute window")
        axis.set_title(panels[index]["title"])
        axis.axvline(timestamp(evidence["injection_started_at"]), color="#c98100", linestyle="--", alpha=0.7)
        axis.axvline(timestamp(evidence["alert_accepted_at"]), color="#29916d", linestyle=":", alpha=0.7)
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=THAILAND))
        axis.set_xlim(timestamp("2026-10-11T22:00:00Z"), timestamp("2026-10-11T22:55:00Z"))
        axis.grid(alpha=0.2)
    axes[4].axis("off")
    axes[4].set_title("Model versions observed during the experiment")
    versions = panels[4]["rows"]
    table = axes[4].table(cellText=[[row["ModelVersion"], row["Requests"],
                                   timestamp(row["LastSeen"]).strftime("%H:%M:%S")] for row in versions],
                          colLabels=["Model version", "Logged scoring requests", "Last observed (TH)"],
                          loc="center", cellLoc="center")
    table.scale(1, 2)
    axes[5].axis("off")
    axes[5].text(0, 0.92, "Scheduled drift outcome", fontsize=14, fontweight="bold")
    temp = next(row for row in evidence["features"] if row["feature"] == "temp_c")
    axes[5].text(0, 0.78,
                 f"temp_c PSI: {temp['psi']:.4f} | threshold: {evidence['threshold']:.4f}\n"
                 f"Injection to Discord acceptance: {evidence['injection_to_webhook_seconds']:.2f} s\n"
                 "Discord HTTP 204 and actual channel receipt confirmed.\n\n"
                 "Orange dashed line: final injection started\nGreen dotted line: webhook accepted\n\n"
                 "Only bins with observed logs are plotted; gaps are not zero-filled.\n"
                 "Baseline and earlier shifted replays are also present.\n"
                 "The endpoint, schedule and compute were subsequently deleted.\n\n"
                 "Source: five saved KQL results from Azure Log Analytics.\n"
                 "This figure is a data export, not a screenshot of Azure Portal.", va="top", linespacing=1.7)
    fig.savefig("reports/dashboard-cloud-evidence.png", dpi=150)
    fig.savefig("reports/dashboard-cloud-evidence.pdf")
    plt.close(fig)
    print("Saved actual cloud dashboard export as PNG and PDF")


if __name__ == "__main__":
    main()
