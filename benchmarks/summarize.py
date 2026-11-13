"""Turn Locust's CSV output into benchmarks/results/RESULTS.md"""
import csv
import os
import platform
from datetime import datetime
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def read_csv(name):
    path = RESULTS / name
    if not path.exists():
        return []
    with path.open() as f:
        return list(csv.DictReader(f))


def ms(value):
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return "-"


def endpoint_table(prefix):
    stats = read_csv(f"{prefix}_stats.csv")
    queries = {row["Name"]: row for row in read_csv(f"{prefix}_queries.csv")}
    lines = [
        "| Method | Endpoint | Requests | Failures | p50 ms | p95 ms | p99 ms | Avg DB queries |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in stats:
        if row["Name"] == "Aggregated":
            continue
        q = queries.get(f"{row['Type']} {row['Name']}", {})
        lines.append(
            f"| {row['Type']} | `{row['Name']}` | {row['Request Count']} | {row['Failure Count']} "
            f"| {ms(row['50%'])} | {ms(row['95%'])} | {ms(row['99%'])} | {q.get('Avg Queries', '-')} |"
        )
    return "\n".join(lines)


out = [
    "# Benchmark results",
    "",
    f"Generated {datetime.now():%Y-%m-%d %H:%M}. Host: {platform.platform()}, {os.cpu_count()} CPUs.",
    "Server: Gunicorn (4 workers x 4 threads, gthread), DEBUG off, PostgreSQL 16, "
    "1M break requests. Load generator runs on the same machine.",
    "",
    "## Mixed workload (employees + managers, 50 organisations)",
    "",
    "| Concurrent users | Requests | Failures | Throughput req/s | p50 ms | p95 ms | p99 ms |",
    "|---:|---:|---:|---:|---:|---:|---:|",
]
for users in (10, 50, 100):
    agg = next((r for r in read_csv(f"u{users}_stats.csv") if r["Name"] == "Aggregated"), None)
    if agg:
        out.append(
            f"| {users} | {agg['Request Count']} | {agg['Failure Count']} "
            f"| {float(agg['Requests/s']):.1f} | {ms(agg['50%'])} | {ms(agg['95%'])} | {ms(agg['99%'])} |"
        )

out += ["", "## Per endpoint at 100 concurrent users", "", endpoint_table("u100"),
        "", "## Contention test (100 users, one organisation, same slots)", "",
        endpoint_table("contention"), ""]

(RESULTS / "RESULTS.md").write_text("\n".join(out))
print("\n".join(out))