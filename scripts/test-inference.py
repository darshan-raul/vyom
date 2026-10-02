"""Run offline inference tests, optionally polling selectors in a restricted sandbox."""

import argparse
import selectors
import sys
import unittest
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--sandbox-selector-poll", action="store_true",
    help="Bound selector waits to avoid lost asyncio self-pipe wakeups in the managed sandbox",
)
args = parser.parse_args()

if args.sandbox_selector_poll:
    original_select = selectors.EpollSelector.select

    def bounded_select(self, timeout=None):
        return original_select(self, 0.05 if timeout is None else min(timeout, 0.05))

    selectors.EpollSelector.select = bounded_select

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / "rag-service"))
suite = unittest.defaultTestLoader.discover(str(repo / "rag-service" / "tests"))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
