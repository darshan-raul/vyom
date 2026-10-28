#!/usr/bin/env python3
"""Validate Markdown links and the active roadmap (stdlib only)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check_roadmap(plan: str, tracker: str) -> list[str]:
    errors = []
    sections = re.split(r"^### (R\d+[a-z]?) — [^\n]+\n", plan, flags=re.M)
    ids = sections[1::2]
    bodies = sections[2::2]
    # Historical tables never count as active tasks.
    active = tracker.split("## Active implementation", 1)[-1].split("\n## ", 1)[0]
    rows = []
    for line in active.splitlines():
        if re.match(r"^\| R\d+[a-z]? \|", line):
            fields = [part.strip() for part in line.strip("|").split("|")]
            if len(fields) != 6:
                errors.append("Active task row must have six fields")
            else:
                rows.append(fields)
    row_ids = [row[0] for row in rows]
    if not ids or len(ids) != len(set(ids)) or len(row_ids) != len(set(row_ids)) or set(ids) != set(row_ids):
        errors.append("Active plan/tracker task IDs missing, duplicated or different")
    order = {task: index for index, task in enumerate(ids)}
    planned = {}
    for task, body in zip(ids, bodies):
        match = re.search(r"^\*\*Depends on:\*\* (.+)$", body, re.M)
        planned[task] = match.group(1) if match else None
        if "**Acceptance:**" not in body:
            errors.append(f"{task}: missing acceptance")
    statuses = {row[0]: row[3] for row in rows}
    if sum(row[3] == "in_progress" for row in rows) > 1:
        errors.append("More than one active implementation task")
    for task, _, deps, status, session, evidence in rows:
        if status not in {"pending", "in_progress", "partial", "blocked", "done", "deferred"}:
            errors.append(f"{task}: invalid status {status}")
        if planned.get(task) != deps:
            errors.append(f"{task}: dependencies differ")
        dependencies = [] if deps == "—" else deps.split(", ")
        for dep in dependencies:
            if dep not in order or order.get(dep, 0) >= order.get(task, -1):
                errors.append(f"{task}: invalid/nonpreceding dependency {dep}")
            if status in {"in_progress", "done"} and statuses.get(dep) != "done":
                errors.append(f"{task}: prerequisite {dep} is unfinished")
        if status in {"in_progress", "partial", "blocked", "done"}:
            if not re.search(r"\d{4}-\d{2}-\d{2}-\d{2}", session) or evidence in {"", "—"}:
                errors.append(f"{task}: status requires session and evidence/retry condition")
        if status == "done" and not re.search(r"\[[^]]+\]\([^)]+\)", session + evidence):
            errors.append(f"{task}: done requires linked evidence")
    return errors


def check(root: Path) -> tuple[list[str], int]:
    errors = []
    files = [root / name for name in ("README.md", "AGENTS.md", "vyom-12-week-sprint-plan.md")]
    files += sorted((root / "docs").rglob("*.md"))
    for path in files:
        text = path.read_text()
        if text.count("```") % 2:
            errors.append(f"{path.relative_to(root)}: unclosed code fence")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            target = target.split("#", 1)[0]
            if target and not (path.parent / target).exists():
                errors.append(f"{path.relative_to(root)}: missing link {target}")
    errors += check_roadmap((root / "docs/IMPLEMENTATION_PLAN.md").read_text(),
                            (root / "docs/TRACKER.md").read_text())
    return errors, len(files)


if __name__ == "__main__":
    errors, count = check(ROOT)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"PASS: {count} Markdown files; local links/fences; active roadmap IDs, dependencies, status and evidence")
    print("Does not validate anchors, rendering, external URLs or runtime/live acceptance.")
