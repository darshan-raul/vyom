#!/usr/bin/env python3
"""Check local documentation links, task references and planning budgets (stdlib only)."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
errors = []
files = [ROOT / 'README.md', ROOT / 'AGENTS.md', ROOT / 'vyom-12-week-sprint-plan.md']
files += sorted((ROOT / 'docs').rglob('*.md'))
for path in files:
    text = path.read_text()
    if text.count('```') % 2:
        errors.append(f'{path.relative_to(ROOT)}: unclosed code fence')
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', text):
        if '://' in target or target.startswith(('#', 'mailto:')):
            continue
        target = target.split('#', 1)[0]
        if target and not (path.parent / target).exists():
            errors.append(f'{path.relative_to(ROOT)}: missing link {target}')
plan = (ROOT / 'docs/IMPLEMENTATION_PLAN.md').read_text()
tracker = (ROOT / 'docs/TRACKER.md').read_text()
ids = re.findall(r'^### (S\d+\.\d+) —', plan, re.M)
rows = re.findall(r'^\| (S\d+\.\d+) \| (.*)$', tracker, re.M)
if len(ids) != len(set(ids)) or set(ids) != {task for task, _ in rows} or len(ids) != len(rows):
    errors.append('Plan/tracker task IDs differ or are duplicated')
order = {task: index for index, task in enumerate(ids)}
for task, row in rows:
    fields = [part.strip() for part in row.split('|')]
    dependencies, status, session, evidence = fields[1:5]
    if status not in {'pending', 'in_progress', 'blocked', 'done', 'deferred'}:
        errors.append(f'{task}: invalid status {status}')
    for dep in re.findall(r'S\d+\.\d+', dependencies):
        if dep not in order or order[dep] >= order[task]:
            errors.append(f'{task}: invalid/nonpreceding dependency {dep}')
    if status in {'done', 'blocked'} and evidence in {'', '—'}:
        errors.append(f'{task}: {status} requires evidence/retry condition')
    section = plan.split(f'### {task} —', 1)[1].split('\n### ', 1)[0]
    planned = re.search(r'\*\*Depends on:\*\* (.*?)\. \*\*Budget:', section)
    if not planned or planned.group(1) != dependencies:
        errors.append(f'{task}: dependencies differ between plan/tracker')
for sprint in re.split(r'\n## S\d+ — ', plan)[1:]:
    hours = sum(map(int, re.findall(r'\*\*Budget:\*\* (\d+) hours', sprint)))
    declared = re.search(r'Planned task budget: (\d+) hours; sprint reserve: (\d+) hours', sprint)
    expected = int(declared.group(1)) if declared else None
    if not declared or declared.group(2) != '10':
        errors.append(f'{sprint.splitlines()[0]}: missing budget or unexpected reserve')
    if hours != expected:
        errors.append(f'{sprint.splitlines()[0]}: expected {expected} task hours, got {hours}')
if errors:
    raise SystemExit('\n'.join(errors))
print(f'PASS: {len(files)} Markdown files; local links/code fences; {len(ids)} matched task IDs; dependencies/status evidence; S1 40-hour and S2–S6 30-hour task budgets.')
print('Does not validate Mermaid rendering, runtime code, external URLs, or live acceptance.')
