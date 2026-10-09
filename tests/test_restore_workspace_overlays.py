"""Historical archive restores must preserve clean Git overlays, never dirty edits."""

import hashlib
import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

GIT = shutil.which("git")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def overlay_repo(tmp_path):
    if not GIT:
        pytest.skip("Git is required for the workspace restoration contract")
    shutil.copyfile(ROOT / "restore_workspace.py", tmp_path / "restore_workspace.py")
    old = b"historical archive\n"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo("src/example.txt")
        member.size = len(old)
        archive.addfile(member, io.BytesIO(old))
    archive_bytes = buffer.getvalue()
    (tmp_path / "workspace.part").write_bytes(archive_bytes)
    manifest = {
        "parts": [{"name": "workspace.part", "bytes": len(archive_bytes),
                   "sha256": hashlib.sha256(archive_bytes).hexdigest()}],
        "files": [{"path": "src/example.txt", "sha256": hashlib.sha256(old).hexdigest()}],
    }
    (tmp_path / "WORKSPACE.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "src").mkdir()
    source = tmp_path / "src/example.txt"
    source.write_bytes(b"current PR source\n")
    subprocess.run([GIT, "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run([GIT, "-c", "core.autocrlf=false", "add", "src/example.txt"], cwd=tmp_path, check=True)
    return tmp_path, source


def test_restore_preserves_clean_tracked_overlay_and_crlf_checkout(overlay_repo):
    import sys

    repo, source = overlay_repo
    source.write_bytes(b"current PR source\r\n")
    result = subprocess.run([sys.executable, "restore_workspace.py"], cwd=repo, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert source.read_bytes() == b"current PR source\r\n"


def test_restore_refuses_dirty_overlay_without_overwriting(overlay_repo):
    import sys

    repo, source = overlay_repo
    source.write_bytes(b"uncommitted edit\n")
    result = subprocess.run([sys.executable, "restore_workspace.py"], cwd=repo, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Existing local changes" in result.stderr
    assert source.read_bytes() == b"uncommitted edit\n"
