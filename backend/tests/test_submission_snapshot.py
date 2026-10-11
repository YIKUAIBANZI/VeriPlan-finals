import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_submission_snapshot.py"


def _git(source: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    )


def _source_tree(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    files = {
        ".gitignore": "*.db\n.env\n",
        ".env.example": "DEEPSEEK_API_KEY=\nTAVILY_API_KEY=<set-in-shell>\n",
        "README.md": "# VeriPlan\n",
        "backend/app/main.py": "print('backend')\n",
        "backend/tests/test_main.py": "def test_ok(): assert True\n",
        "frontend/src/main.ts": "export const ready = true\n",
        "scripts/helper.py": "print('helper')\n",
        "backend/.venv/ignored.txt": "dependency",
        "frontend/node_modules/pkg/index.js": "dependency",
        "frontend/dist/app.js": "build output",
        "backend/local.db": "sqlite bytes",
        "frontend/.DS_Store": "metadata",
    }
    for relative, content in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    _git(source, "init", "-q")
    _git(source, "config", "user.email", "test@example.invalid")
    _git(source, "config", "user.name", "Snapshot Test")
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "fixture")
    return source


def _build(source: Path, output: Path, archive: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--output",
            str(output),
            "--archive",
            str(archive),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_builds_allowlisted_snapshot_manifest_and_reproducible_zip(tmp_path):
    source = _source_tree(tmp_path)
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    first_archive = tmp_path / "first.zip"
    second_archive = tmp_path / "second.zip"

    first = _build(source, first_output, first_archive)
    second = _build(source, second_output, second_archive)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    expected = {
        ".env.example",
        ".gitignore",
        "README.md",
        "backend/app/main.py",
        "backend/tests/test_main.py",
        "frontend/src/main.ts",
        "scripts/helper.py",
    }
    manifest = json.loads(
        (first_output / "SUBMISSION_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 1
    assert manifest["source_commit"] == _git(source, "rev-parse", "HEAD").stdout.strip()
    assert {item["path"] for item in manifest["files"]} == expected
    for item in manifest["files"]:
        data = (first_output / item["path"]).read_bytes()
        assert item["bytes"] == len(data)
        assert item["sha256"] == hashlib.sha256(data).hexdigest()

    assert first_archive.read_bytes() == second_archive.read_bytes()
    with ZipFile(first_archive) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert all(name.startswith("VeriPlan/") for name in names)
        assert "VeriPlan/SUBMISSION_MANIFEST.json" in names
    summary = json.loads(first.stdout)
    assert summary["file_count"] == len(expected)
    assert summary["secret_findings"] == 0
    assert summary["archive_sha256"] == hashlib.sha256(
        first_archive.read_bytes()
    ).hexdigest()


def test_rejects_secret_material_without_leaving_outputs(tmp_path):
    source = _source_tree(tmp_path)
    leak = source / "backend" / "leak.txt"
    fake_secret = "sk-" + "real-looking-secret-value"
    leak.write_text(f"DEEPSEEK_API_KEY={fake_secret}\n", encoding="utf-8")
    _git(source, "add", str(leak.relative_to(source)))
    _git(source, "commit", "-qm", "add leak")
    output = tmp_path / "snapshot"
    archive = tmp_path / "snapshot.zip"

    result = _build(source, output, archive)

    assert result.returncode != 0
    assert "secret" in result.stderr.casefold()
    assert fake_secret not in result.stderr
    assert not output.exists()
    assert not archive.exists()


def test_rejects_symlinks_in_allowlisted_tree(tmp_path):
    source = _source_tree(tmp_path)
    link = source / "backend" / "external-link"
    link.symlink_to(tmp_path / "outside")
    _git(source, "add", str(link.relative_to(source)))
    _git(source, "commit", "-qm", "add link")

    result = _build(source, tmp_path / "snapshot", tmp_path / "snapshot.zip")

    assert result.returncode != 0
    assert "symbolic link" in result.stderr.casefold()


def test_rejects_uncommitted_allowlisted_changes_but_ignores_internal_docs(tmp_path):
    source = _source_tree(tmp_path)
    (source / "README.md").write_text("changed\n", encoding="utf-8")
    (source / "AGENTS.md").write_text("private local note\n", encoding="utf-8")

    rejected = _build(source, tmp_path / "dirty", tmp_path / "dirty.zip")

    assert rejected.returncode != 0
    assert "uncommitted" in rejected.stderr.casefold()
    _git(source, "restore", "README.md")

    accepted = _build(source, tmp_path / "clean", tmp_path / "clean.zip")

    assert accepted.returncode == 0, accepted.stderr
    assert not (tmp_path / "clean" / "AGENTS.md").exists()
