#!/usr/bin/env python3
"""Generate Mermaid dependency diagrams from docs/tickets/tickets.csv."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "tickets.csv"
MOVE_PLAN_PATH = ROOT / "move-plan.csv"
GRAPH_PATH = ROOT / "GRAPH.md"
REPO_ROOT = ROOT.parent.parent

# These targets intentionally pin the current migration graph. Update them
# only when adding or removing tickets deliberately.
TARGET_ROW_COUNT = 66
TARGET_EPIC_COUNT = 7
TARGET_TASK_COUNT = 59
REMOVED_AGGREGATE_KEYS = (
    "NBB-108",
    "NBB-202",
    "NBB-207",
    "NBB-209",
    "NBB-501",
    "NBB-704",
    "NBB-705",
)
REMOVED_ACTIVE_KEYS = REMOVED_AGGREGATE_KEYS + ("NBB-404",)
MOVE_PLAN_HEADER = (
    "ticket",
    "language",
    "old_path",
    "new_path",
    "old_symbol",
    "new_symbol",
    "mode",
    "tool",
)
MOVE_PLAN_MODES = frozenset({
    "json_asset_move",
    "python_module_move",
    "python_module_remove",
    "python_symbol_extract",
    "python_symbol_move",
    "python_symbol_remove",
    "python_symbol_rename",
    "text_reference_check",
    "typescript_module_move",
})


def required_move_plan_fields(mode):
    if mode in {"json_asset_move", "python_module_move", "typescript_module_move"}:
        return ("old_path", "new_path")
    if mode in {"python_symbol_move", "python_symbol_rename", "python_symbol_extract"}:
        return ("old_path", "new_path", "old_symbol", "new_symbol")
    if mode in {"python_module_remove", "text_reference_check"}:
        return ("old_path",)
    if mode == "python_symbol_remove":
        return ("old_path", "old_symbol")
    return ()


def load_rows():
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def dependencies(row):
    raw = row.get("depends_on") or ""
    return [part.strip() for part in raw.replace(",", ";").split(";") if part.strip()]


def task_rows(rows):
    return [row for row in rows if row["type"] == "Task"]


def compute_waves(tasks):
    task_keys = {row["key"] for row in tasks}
    deps = {
        row["key"]: [dep for dep in dependencies(row) if dep in task_keys]
        for row in tasks
    }

    waves = {}
    while len(waves) < len(tasks):
        progressed = False
        for row in tasks:
            key = row["key"]
            if key in waves:
                continue
            if all(dep in waves for dep in deps[key]):
                waves[key] = 0 if not deps[key] else max(waves[dep] + 1 for dep in deps[key])
                progressed = True
        if not progressed:
            unresolved = sorted(set(task_keys) - set(waves))
            raise SystemExit(f"cycle or unresolved dependency among: {', '.join(unresolved)}")
    return waves


def node_id(key):
    return key.replace("-", "")


def mermaid_dag(tasks):
    lines = [
        "```mermaid",
        "flowchart LR",
        "  classDef p0 fill:#fee2e2,stroke:#b91c1c,color:#111",
        "  classDef p1 fill:#e0f2fe,stroke:#0369a1,color:#111",
    ]
    task_keys = {row["key"] for row in tasks}
    emitted_nodes = set()

    for row in tasks:
        key = row["key"]
        priority_class = "p0" if row["priority"] == "P0" else "p1"
        if not dependencies(row):
            lines.append(f'  {node_id(key)}["{key}"]:::{priority_class}')
            emitted_nodes.add(key)
        for dep in dependencies(row):
            if dep not in task_keys:
                continue
            if dep not in emitted_nodes:
                dep_row = next(item for item in tasks if item["key"] == dep)
                dep_class = "p0" if dep_row["priority"] == "P0" else "p1"
                lines.append(f'  {node_id(dep)}["{dep}"]:::{dep_class}')
                emitted_nodes.add(dep)
            if key not in emitted_nodes:
                lines.append(f'  {node_id(key)}["{key}"]:::{priority_class}')
                emitted_nodes.add(key)
            lines.append(f"  {node_id(dep)} --> {node_id(key)}")

    lines.append("```")
    return "\n".join(lines)


def wave_table(tasks, waves):
    by_wave = defaultdict(list)
    for row in tasks:
        by_wave[waves[row["key"]]].append(row["key"])

    lines = ["## Execution Waves", "", "| Wave | Tickets |", "|---|---|"]
    for wave in sorted(by_wave):
        tickets = ", ".join(f"`{key}`" for key in sorted(by_wave[wave]))
        lines.append(f"| {wave} | {tickets} |")
    return "\n".join(lines)


def milestone_gantt(tasks, waves):
    by_epic = defaultdict(list)
    for row in tasks:
        by_epic[row["epic_key"]].append(row)

    lines = [
        "```mermaid",
        "gantt",
        "  title Agentic Migration Milestones by Dependency Wave",
        "  dateFormat  YYYY-MM-DD",
        "  axisFormat  Wave %j",
    ]

    for epic in sorted(by_epic):
        lines.append(f"  section {epic}")
        for row in sorted(by_epic[epic], key=lambda item: (waves[item["key"]], item["key"])):
            wave = waves[row["key"]]
            day = wave + 1
            start = f"2026-01-{day:02d}"
            label = f'{row["key"]} {row["size"]}'
            lines.append(f"  {label} :{start}, 1d")

    lines.append("```")
    return "\n".join(lines)


def validate(rows):
    keys = {row["key"] for row in rows}
    tasks = [row for row in rows if row["type"] == "Task"]
    epics = [row for row in rows if row["type"] == "Epic"]

    lines = [
        f"Rows: {len(rows)} (target {TARGET_ROW_COUNT})",
        f"Epics: {len(epics)} (target {TARGET_EPIC_COUNT})",
        f"Tasks: {len(tasks)} (target {TARGET_TASK_COUNT})",
    ]
    issues = 0
    if len(rows) != TARGET_ROW_COUNT:
        issues += 1
    if len(epics) != TARGET_EPIC_COUNT:
        issues += 1
    if len(tasks) != TARGET_TASK_COUNT:
        issues += 1

    dangling = []
    for row in rows:
        for dep in dependencies(row):
            if dep not in keys:
                dangling.append(f"{row['key']}->{dep}")
    if dangling:
        issues += 1
        lines.append(f"Dangling deps: {dangling}")
    else:
        lines.append("Dangling deps: none")

    for row in rows:
        doc_path = REPO_ROOT / row["doc_path"]
        if not doc_path.exists():
            issues += 1
            lines.append(f"MISSING DOC: {row['key']} -> {row['doc_path']}")
            continue
        anchor = row["anchor"].lstrip("#")
        content = doc_path.read_text(encoding="utf-8")
        if f'<a id="{anchor}"></a>' not in content:
            issues += 1
            lines.append(
                f"MISSING ANCHOR: {row['key']} expects {row['anchor']} in {row['doc_path']}"
            )

    lines.append("CSV integrity check done.")

    for row in rows:
        for dep in dependencies(row):
            if dep in REMOVED_AGGREGATE_KEYS:
                issues += 1
                lines.append(f"STALE AGGREGATE REF: {row['key']} -> {dep}")

    for row in rows:
        if row["key"] in REMOVED_ACTIVE_KEYS:
            issues += 1
            lines.append(f"STALE ROW STILL PRESENT: {row['key']}")

    lines.append("Aggregate check done.")

    return lines, issues == 0


def validate_move_plan():
    lines = []
    issues = 0
    with MOVE_PLAN_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != MOVE_PLAN_HEADER:
            issues += 1
            lines.append(
                "MOVE-PLAN HEADER: expected "
                f"{list(MOVE_PLAN_HEADER)}, got {reader.fieldnames}"
            )
        rows = list(reader)

    for index, row in enumerate(rows, start=2):
        if None in row:
            issues += 1
            lines.append(f"MOVE-PLAN ROW {index}: malformed extra columns {row[None]}")
        for field in ("ticket", "language", "mode", "tool"):
            if not (row.get(field) or "").strip():
                issues += 1
                lines.append(f"MOVE-PLAN ROW {index}: missing {field}")
        mode = (row.get("mode") or "").strip()
        if mode and mode not in MOVE_PLAN_MODES:
            issues += 1
            lines.append(f"MOVE-PLAN ROW {index}: unknown mode {mode!r}")
            continue
        for field in required_move_plan_fields(mode):
            if not (row.get(field) or "").strip():
                issues += 1
                lines.append(f"MOVE-PLAN ROW {index}: {mode} missing {field}")

    lines.append(f"Move-plan rows: {len(rows)}")
    lines.append("Move-plan check done.")
    return lines, issues == 0


def render():
    rows = load_rows()
    tasks = task_rows(rows)
    waves = compute_waves(tasks)

    return "\n\n".join(
        [
            "# Ticket Dependency Graph",
            "Generated from `docs/tickets/tickets.csv` by `python3 docs/tickets/dag.py --write`.",
            wave_table(tasks, waves),
            "## Mermaid Task Dependency DAG",
            mermaid_dag(tasks),
            "## Mermaid Milestone Bar Chart",
            milestone_gantt(tasks, waves),
        ]
    ) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write docs/tickets/GRAPH.md")
    parser.add_argument(
        "--check",
        action="store_true",
        help="run CSV integrity and aggregate checks; exit 1 on any issue",
    )
    args = parser.parse_args()

    exit_code = 0
    if args.check:
        rows = load_rows()
        lines, ok = validate(rows)
        for line in lines:
            print(line)
        if not ok:
            exit_code = 1
        move_plan_lines, move_plan_ok = validate_move_plan()
        for line in move_plan_lines:
            print(line)
        if not move_plan_ok:
            exit_code = 1

    if args.write or not args.check:
        output = render()
        if args.write:
            GRAPH_PATH.write_text(output, encoding="utf-8")
        else:
            print(output, end="")

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
