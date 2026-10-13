"""Guard regressions without network attempts or nested test execution."""
import ast
import os
import unittest
from pathlib import Path
from pkgutil import resolve_name
from unittest.mock import patch

from tests.offline_support import BLOCKED_TARGETS, offline_environment, offline_guard


class TestTestingFoundation(unittest.TestCase):
    def test_each_guard_rejects_and_remembers_swallowed_attempts(self):
        for target in BLOCKED_TARGETS:
            with self.subTest(target=target):
                with self.assertRaisesRegex(AssertionError, "Forbidden offline operations"):
                    with offline_guard():
                        # Resolve only after patching: this calls the guard, never an SDK/socket.
                        with self.assertRaisesRegex(AssertionError, "Offline operation forbidden"):
                            resolve_name(target)()

    def test_guard_restores_targets_on_exception(self):
        import socket
        original = socket.create_connection
        with self.assertRaisesRegex(RuntimeError, "test interruption"):
            with offline_guard():
                self.assertIsNot(socket.create_connection, original)
                raise RuntimeError("test interruption")
        self.assertIs(socket.create_connection, original)

    def test_environment_is_isolated_and_restored(self):
        with patch.dict(os.environ, {"AWS_PROFILE": "wrong", "AWS_ACCESS_KEY_ID": "fake",
                                     "BEDROCK_MODEL_ID": "wrong", "BEDROCK_SYSTEM_PROMPT": "wrong"}):
            before = dict(os.environ)
            with offline_environment():
                self.assertEqual(os.environ["AWS_PROFILE"], "novamind")
                self.assertEqual(os.environ["AWS_REGION"], "us-east-1")
                self.assertNotIn("AWS_ACCESS_KEY_ID", os.environ)
                self.assertNotIn("BEDROCK_SYSTEM_PROMPT", os.environ)
                self.assertEqual(os.environ["AWS_EC2_METADATA_DISABLED"], "true")
            self.assertEqual(dict(os.environ), before)

    def test_regression_modules_do_not_run_nested_suites(self):
        forbidden = {"TextTestRunner", "TestLoader", "discover", "loadTestsFromModule",
                     "loadTestsFromName", "loadTestsFromNames", "loadTestsFromTestCase"}
        for path in Path(__file__).parent.glob("test_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                    self.assertNotIn(name, forbidden, str(path))
