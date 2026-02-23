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


if __name__ == "__main__":
    unittest.main()
