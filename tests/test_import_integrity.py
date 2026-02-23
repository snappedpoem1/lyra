import importlib
import unittest


class ImportIntegrityTests(unittest.TestCase):
    def test_config_exports_required_paths(self) -> None:
        cfg = importlib.import_module("oracle.config")
        self.assertTrue(hasattr(cfg, "REPORTS_FOLDER"))
        self.assertTrue(hasattr(cfg, "PLAYLISTS_FOLDER"))

    def test_repair_imports_cleanly(self) -> None:
        repair = importlib.import_module("oracle.repair")
        self.assertTrue(hasattr(repair, "check_directories"))


if __name__ == "__main__":
    unittest.main()
