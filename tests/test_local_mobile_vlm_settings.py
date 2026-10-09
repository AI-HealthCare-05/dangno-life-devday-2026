import os

import pytest

from scripts.local_mobile_settings import load_local_mobile_settings


@pytest.fixture
def settings_root(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_API_KEY_FILE", "OPENAI_VLM_FALLBACK_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-only")
    return tmp_path


def test_file_backed_key_is_injected_without_copying_it(settings_root):
    key_file = settings_root / "key.txt"
    key_file.write_text("OPENAI_API_KEY=sk-test-local-only\n", encoding="utf-8-sig")
    env_file = settings_root / ".env.local-mobile"
    contents = f"SECRET_KEY=test-only\nOPENAI_VLM_FALLBACK_ENABLED=true\nOPENAI_API_KEY_FILE={key_file.as_posix()}\n"
    env_file.write_text(contents, encoding="utf-8")
    load_local_mobile_settings(settings_root)
    assert os.environ["OPENAI_API_KEY"] == "sk-test-local-only"
    assert env_file.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize("content", ["", "not-a-key", "sk-first\nsk-second"])
def test_ambiguous_key_file_fails_without_disclosing_content(settings_root, content):
    key_file = settings_root / "key.txt"
    key_file.write_text(content, encoding="utf-8")
    (settings_root / ".env.local-mobile").write_text(
        f"SECRET_KEY=test-only\nOPENAI_VLM_FALLBACK_ENABLED=true\nOPENAI_API_KEY_FILE={key_file.as_posix()}\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="exactly one API key") as exc:
        load_local_mobile_settings(settings_root)
    assert "sk-first" not in str(exc.value)
    assert "OPENAI_API_KEY" not in os.environ


def test_existing_environment_key_has_priority_over_key_file(settings_root, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-existing-test-only")
    (settings_root / ".env.local-mobile").write_text(
        "SECRET_KEY=test-only\nOPENAI_VLM_FALLBACK_ENABLED=true\nOPENAI_API_KEY_FILE=missing.txt\n", encoding="utf-8"
    )
    load_local_mobile_settings(settings_root)
    assert os.environ["OPENAI_API_KEY"] == "sk-existing-test-only"


def test_enabled_vlm_requires_key(settings_root):
    (settings_root / ".env.local-mobile").write_text("SECRET_KEY=test-only\nOPENAI_VLM_FALLBACK_ENABLED=true\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="key is missing"):
        load_local_mobile_settings(settings_root)


def test_disabled_vlm_does_not_read_key_file(settings_root):
    (settings_root / ".env.local-mobile").write_text(
        "SECRET_KEY=test-only\nOPENAI_VLM_FALLBACK_ENABLED=false\nOPENAI_API_KEY_FILE=missing.txt\n", encoding="utf-8"
    )
    load_local_mobile_settings(settings_root)
    assert "OPENAI_API_KEY" not in os.environ
