"""Regression cases for roadmap validation; run with unittest discovery."""
import importlib.util
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

spec = importlib.util.spec_from_file_location("check_docs", Path(__file__).with_name("check-docs.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PLAN = """### R1 — First
**Depends on:** —
**Acceptance:** verified
### R2 — Second
**Depends on:** R1
**Acceptance:** verified
"""
TRACKER = """## Active implementation
| R1 | First | — | done | [2026-10-29-05](sessions/example.md) | passed |
| R2 | Second | R1 | in_progress | 2026-10-29-05 | verifying |
## Historical
| S1.1 | ignored |
"""


class RoadmapTests(unittest.TestCase):
    def test_local_markdown_and_html_images_must_exist(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs/IMPLEMENTATION_PLAN.md").write_text(PLAN)
            (root / "docs/TRACKER.md").write_text(TRACKER.replace(
                "sessions/example.md", "../README.md"))
            for name in ("AGENTS.md", "CONSTITUTION.md"):
                (root / name).write_text("")
            (root / "README.md").write_text(
                '<img src="logo.png" />\n![Architecture](architecture.png)\n'
                '<img src="https://example.com/remote.png" />')
            errors, _ = module.check(root)
            self.assertEqual(len(errors), 2)
            for name in ("logo.png", "architecture.png"):
                (root / name).touch()
            self.assertEqual(module.check(root)[0], [])

    def test_valid_active_roadmap_ignores_history(self):
        self.assertEqual(module.check_roadmap(PLAN, TRACKER), [])

    def test_rejects_broken_dependency_and_missing_task(self):
        self.assertTrue(module.check_roadmap(PLAN.replace('**Depends on:** R1', '**Depends on:** R9'), TRACKER))
        self.assertTrue(module.check_roadmap(PLAN, TRACKER.replace('| R2 |', '| R3 |')))

    def test_cannot_start_before_prerequisite_or_run_two_tasks(self):
        self.assertTrue(module.check_roadmap(PLAN, TRACKER.replace('| done |', '| in_progress |')))

    def test_done_requires_linked_evidence(self):
        self.assertTrue(module.check_roadmap(PLAN, TRACKER.replace('[2026-10-29-05](sessions/example.md)', '2026-10-29-05')))

    def test_partial_is_valid_but_needs_session_and_reason(self):
        tracker = TRACKER.replace('| in_progress |', '| partial |')
        self.assertEqual(module.check_roadmap(PLAN, tracker), [])
        self.assertTrue(module.check_roadmap(PLAN, tracker.replace('| 2026-10-29-05 | verifying |', '| — | — |')))

    def test_no_empty_or_duplicate_roadmap(self):
        self.assertTrue(module.check_roadmap('', ''))
        self.assertTrue(module.check_roadmap(PLAN + PLAN, TRACKER))
