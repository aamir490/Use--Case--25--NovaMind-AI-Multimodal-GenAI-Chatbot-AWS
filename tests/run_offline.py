"""Canonical offline entry point. Importing this module does not run tests."""
import sys
import unittest
from pathlib import Path

from tests.offline_support import offline_environment, offline_guard


def test_ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from test_ids(item)
        else:
            yield item.id()


def main():
    root = Path(__file__).resolve().parents[1]
    with offline_environment(), offline_guard():
        # Preserve existing top-level fixture imports without discovering twice.
        suite = unittest.TestLoader().discover(str(root / "tests"), pattern="test_*.py")
        ids = list(test_ids(suite))
        if len(ids) != len(set(ids)):
            raise AssertionError("Duplicate test IDs in discovery")
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
