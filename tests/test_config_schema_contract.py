import unittest
from unittest import mock

from oracle import config
from oracle.db import schema


class ConfigSchemaContractTests(unittest.TestCase):
    def test_schema_uses_config_db_path(self) -> None:
        self.assertEqual(schema.DB_PATH, config.LYRA_DB_PATH)

    def test_guard_bypass_defaults_disabled(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(config.guard_bypass_allowed())

<<<<<<< HEAD
=======
    def test_validate_required_env_fails_loudly(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                config.validate_required_env(["PROWLARR_API_KEY", "REAL_DEBRID_KEY"])

    def test_validate_required_env_passes_when_set(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"PROWLARR_API_KEY": "x", "REAL_DEBRID_KEY": "y"},
            clear=True,
        ):
            config.validate_required_env(["PROWLARR_API_KEY", "REAL_DEBRID_KEY"])

>>>>>>> fc77b41 (Update workspace state and diagnostics)

if __name__ == "__main__":
    unittest.main()
