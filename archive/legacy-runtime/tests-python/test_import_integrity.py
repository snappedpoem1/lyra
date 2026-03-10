import importlib
import pkgutil
import unittest


class ImportIntegrityTests(unittest.TestCase):
    def test_config_exports_required_paths(self) -> None:
        cfg = importlib.import_module("oracle.config")
        self.assertTrue(hasattr(cfg, "REPORTS_FOLDER"))
        self.assertTrue(hasattr(cfg, "PLAYLISTS_FOLDER"))

    def test_repair_imports_cleanly(self) -> None:
        repair = importlib.import_module("oracle.repair")
        self.assertTrue(hasattr(repair, "check_directories"))

    def test_all_oracle_modules_import_cleanly(self) -> None:
        oracle_pkg = importlib.import_module("oracle")
        failures = []
        for module in pkgutil.walk_packages(oracle_pkg.__path__, oracle_pkg.__name__ + "."):
            name = module.name
            try:
                importlib.import_module(name)
            except Exception as exc:
                failures.append(f"{name}: {exc!r}")
        self.assertEqual([], failures, "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
