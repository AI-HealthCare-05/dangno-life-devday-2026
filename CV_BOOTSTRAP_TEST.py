import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("cv_bootstrap", Path(__file__).with_name("CV_BOOTSTRAP.py"))
cv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cv)


class DeliveryTests(unittest.TestCase):
    def test_last_bad_download_preserves_all_installed_models(self):
        with tempfile.TemporaryDirectory() as root:
            dst = Path(root) / "models"
            dst.mkdir()
            for name, _, _ in cv.FILES:
                (dst / name).write_bytes(b"existing")
            def fake_download(file_id, target):
                target.write_bytes(b"bad" if target.name == "1.tflite" else b"verified")
            def fake_digest(path):
                return next(sha for name, _, sha in cv.FILES if name == path.name) if path.read_bytes() == b"verified" else "invalid"
            with patch.object(cv, "download", fake_download), patch.object(cv, "digest", fake_digest):
                with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                    cv.provision(dst)
            self.assertTrue(all((dst / n).read_bytes() == b"existing" for n, _, _ in cv.FILES))

    def test_verified_cache_does_not_use_network(self):
        with tempfile.TemporaryDirectory() as root:
            dst = Path(root)
            for name, _, _ in cv.FILES:
                (dst / name).write_bytes(b"verified")
            with patch.object(cv, "digest", lambda p: next(sha for n, _, sha in cv.FILES if n == p.name)), patch.object(cv, "download") as download:
                cv.provision(dst)
                download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
