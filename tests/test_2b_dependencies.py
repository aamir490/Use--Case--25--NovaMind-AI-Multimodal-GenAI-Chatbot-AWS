"""Offline dependency contract checks; no installation, subprocesses or AWS."""
import ast
import importlib.metadata as metadata
import struct
import sys
import unittest
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def declarations(filename):
    """Read only this file; includes are validated separately."""
    return [line.strip() for line in (ROOT / filename).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def pins(filename):
    result = {}
    for line in declarations(filename):
        requirement = Requirement(line)
        specs = list(requirement.specifier)
        if (len(specs) != 1 or specs[0].operator != "==" or "*" in specs[0].version
                or requirement.url or requirement.marker or requirement.extras):
            raise AssertionError("Expected unconditional exact pin: " + line)
        name = canonicalize_name(requirement.name)
        if name in result:
            raise AssertionError("Duplicate dependency: " + name)
        result[name] = specs[0].version
    return result


class TestDependencyBaseline(unittest.TestCase):
    def test_supported_interpreter(self):
        expected = (ROOT / ".python-version").read_text().strip()
        self.assertEqual(expected, "3.14.6")
        self.assertEqual(sys.implementation.name, "cpython")
        self.assertEqual(".".join(map(str, sys.version_info[:3])), expected)
        self.assertEqual(sys.platform, "win32", "Validate a separate lock for other platforms")
        self.assertEqual(struct.calcsize("P"), 8)
        import sysconfig
        self.assertFalse(sysconfig.get_config_var("Py_GIL_DISABLED"))

    def test_compatibility_entrypoint_and_direct_pins(self):
        self.assertEqual(declarations("requirements_new.txt"), ["-r requirements.txt"])
        direct = pins("requirements.in")
        self.assertEqual(set(direct), {"boto3", "botocore", "streamlit", "pillow", "pypdf"})
        locked = pins("requirements.txt")
        for name, version in direct.items():
            self.assertEqual(locked[name], version)

    def test_installed_versions_and_python_requirements_match_lock(self):
        for name, version in pins("requirements.txt").items():
            with self.subTest(package=name):
                dist = metadata.distribution(name)
                self.assertEqual(dist.version, version, "Recreate the locked environment")
                python_range = dist.metadata.get("Requires-Python")
                if python_range:
                    self.assertIn(".".join(map(str, sys.version_info[:3])), SpecifierSet(python_range))

    def test_lock_is_complete_compatible_and_contains_no_unused_packages(self):
        locked = pins("requirements.txt")
        pending = list(pins("requirements.in"))
        visited = set()
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            for value in metadata.distribution(name).requires or []:
                dependency = Requirement(value)
                if dependency.marker and not dependency.marker.evaluate({"extra": ""}):
                    continue
                child = canonicalize_name(dependency.name)
                with self.subTest(parent=name, dependency=child):
                    self.assertFalse(dependency.extras, "Expand extra dependencies before locking")
                    self.assertIn(child, locked)
                    self.assertIn(locked[child], dependency.specifier)
                pending.append(child)
        self.assertEqual(visited, set(locked))

    def test_runtime_imports_have_direct_or_optional_declarations(self):
        mapping = {"PIL": "pillow", "boto3": "boto3", "botocore": "botocore",
                   "streamlit": "streamlit", "pypdf": "pypdf", "olefile": "olefile"}
        declared = set(pins("requirements.in")) | {"olefile"}
        local = {"novamind", "services", "utils"}
        paths = [ROOT / "mod_chatbot_frontend.py"]
        for folder in ("novamind", "services", "utils", "scripts"):
            paths.extend((ROOT / folder).rglob("*.py"))
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    names = [node.module]
                for name in names:
                    name = name.split(".")[0]
                    if name in sys.stdlib_module_names or name in local:
                        continue
                    with self.subTest(file=str(path.relative_to(ROOT)), module=name):
                        self.assertIn(name, mapping)
                        self.assertIn(mapping[name], declared)

    def test_required_parser_apis_exist(self):
        from PIL import Image, ImageOps
        from pypdf import PdfReader, PdfWriter, filters
        from pypdf.generic import IndirectObject, StreamObject
        for attribute in ("ZLIB_MAX_OUTPUT_LENGTH", "LZW_MAX_OUTPUT_LENGTH",
                          "RUN_LENGTH_MAX_OUTPUT_LENGTH", "MAX_DECLARED_STREAM_LENGTH"):
            self.assertTrue(hasattr(filters, attribute), attribute)
        self.assertTrue(callable(filters.JBIG2Decode.decode))
        self.assertTrue(callable(ImageOps.exif_transpose))
        self.assertTrue(hasattr(Image.Resampling, "LANCZOS"))
        for cls, attributes in ((Image.Image, ("verify", "load")),
                                (PdfReader, ("__enter__", "__exit__")),
                                (PdfWriter, ("close",)),
                                (IndirectObject, ("get_object",)),
                                (StreamObject, ("get_data",))):
            for attribute in attributes:
                self.assertTrue(callable(getattr(cls, attribute, None)), attribute)

    def test_legacy_dependency_is_explicit_and_optional(self):
        self.assertEqual(declarations("requirements-legacy.txt"),
                         ["-r requirements.txt", "olefile==0.47"])
        self.assertNotIn("olefile", pins("requirements.txt"))
        try:
            version = metadata.version("olefile")
        except metadata.PackageNotFoundError:
            return  # Baseline intentionally preserves fail-closed legacy handling.
        self.assertEqual(version, "0.47")
