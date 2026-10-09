import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "mobile_setup", Path(__file__).resolve().parents[2] / "scripts/setup-local-mobile.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_independent_secrets_and_no_overwrite(tmp_path):
    first, second = tmp_path / "first.env", tmp_path / "second.env"
    assert setup.create_settings(first)
    assert setup.create_settings(second)
    a, b = first.read_text(), second.read_text()
    assert a != b
    assert "COOKIE_DOMAIN=\n" in a
    assert "DATABASE_URL=sqlite://storage/local_mobile.sqlite3" in a
    assert "DEMO_ARTIFACT_INFERENCE_ENABLED=true" in a
    assert not setup.create_settings(first)
    assert first.read_text() == a
