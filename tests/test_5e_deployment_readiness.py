"""Offline checks for the supported Streamlit container entry configuration."""
import tomllib
import unittest
from pathlib import Path


class StreamlitContainerConfigTests(unittest.TestCase):
    def test_container_binding_and_security_settings(self):
        root = Path(__file__).resolve().parents[1]
        with (root / ".streamlit" / "config.toml").open("rb") as config_file:
            config = tomllib.load(config_file)

        server = config["server"]
        self.assertTrue(server["headless"])
        self.assertEqual(server["address"], "0.0.0.0")
        self.assertEqual(server["port"], 8501)
        self.assertTrue(server["enableCORS"])
        self.assertTrue(server["enableXsrfProtection"])
        self.assertEqual(server["maxUploadSize"], 5)
        self.assertFalse(config["browser"]["gatherUsageStats"])


if __name__ == "__main__":
    unittest.main()
