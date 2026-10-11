#!/usr/bin/env python3
"""Build a scanned, deterministic VeriPlan submission snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ALLOWED_PATHS = (
    ".gitignore",
    ".env.example",
    "README.md",
    "backend",
    "frontend",
    "scripts",
)
EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
}
EXCLUDED_FILES = {".DS_Store", ".env"}
EXCLUDED_SUFFIXES = {".db", ".pyc", ".pyo", ".tsbuildinfo"}
TOKEN_PATTERNS = (
    ("private key", re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("provider token", re.compile(rb"\b(?:sk|tvly)-[A-Za-z0-9_-]{16,}\b")),
    ("GitHub token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(rb"\bAKIA[A-Z0-9]{16}\b")),
)
SENSITIVE_ASSIGNMENT = re.compile(
    rb"(?m)^[ \t]*(?:DEEPSEEK_API_KEY|TAVILY_API_KEY|OPENAI_API_KEY|"
    rb"GITHUB_TOKEN|AWS_SECRET_ACCESS_KEY)[ \t]*=[ \t]*([^ \t\r\n#]*)"
)
PLACEHOLDERS = {b"", b"changeme", b"placeholder", b"<set-in-shell>", b"<your-key>"}


class BuildError(RuntimeError):
    """A safe, user-facing snapshot build failure."""


def _is_excluded(path: Path) -> bool:
    return path.name in EXCLUDED_FILES or path.suffix in EXCLUDED_SUFFIXES


def _collect_files(source: Path) -> list[Path]:
    collected: list[Path] = []
    for allowed in ALLOWED_PATHS:
        root = source / allowed
        if not root.exists():
            raise BuildError(f"required allowlisted path is missing: {allowed}")
        if root.is_symlink():
            raise BuildError(f"symbolic link is not allowed: {allowed}")
        if root.is_file():
            collected.append(root)
            continue
        for current, directories, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            kept_directories: list[str] = []
            for name in directories:
                candidate = current_path / name
                if candidate.is_symlink():
                    raise BuildError(
                        "symbolic link is not allowed: "
                        + candidate.relative_to(source).as_posix()
                    )
                if name not in EXCLUDED_DIRS:
                    kept_directories.append(name)
            directories[:] = kept_directories
            for name in files:
                candidate = current_path / name
                if candidate.is_symlink():
                    raise BuildError(
                        "symbolic link is not allowed: "
                        + candidate.relative_to(source).as_posix()
                    )
                if not _is_excluded(candidate):
                    collected.append(candidate)
    return sorted(collected, key=lambda item: item.relative_to(source).as_posix())


def _git_output(source: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _source_revision(source: Path) -> str:
    revision = _git_output(source, "rev-parse", "HEAD")
    return revision or "unversioned"


def _require_clean_allowlist(source: Path) -> None:
    if _git_output(source, "rev-parse", "--is-inside-work-tree") != "true":
        return
    status = _git_output(source, "status", "--porcelain", "--", *ALLOWED_PATHS)
    if status:
        changed = [line[3:] for line in status.splitlines()[:8]]
        raise BuildError(
            "allowlisted files contain uncommitted changes: " + ", ".join(changed)
        )


def _secret_findings(source: Path, files: list[Path]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    for path in files:
        data = path.read_bytes()
        if b"\0" in data:
            continue
        relative = path.relative_to(source).as_posix()
        for label, pattern in TOKEN_PATTERNS:
            if pattern.search(data):
                findings.append((relative, label))
        for match in SENSITIVE_ASSIGNMENT.finditer(data):
            value = match.group(1).strip().lower()
            if value not in PLACEHOLDERS:
                findings.append((relative, "non-empty sensitive assignment"))
    return findings


def _write_manifest(source: Path, destination: Path, files: list[Path]) -> dict:
    entries = []
    for path in files:
        data = path.read_bytes()
        relative = path.relative_to(source).as_posix()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entries.append(
            {
                "path": relative,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    manifest = {
        "schema_version": 1,
        "source_commit": _source_revision(source),
        "files": entries,
    }
    (destination / "SUBMISSION_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _write_archive(snapshot: Path, archive: Path) -> None:
    with ZipFile(archive, "w") as bundle:
        for path in sorted(item for item in snapshot.rglob("*") if item.is_file()):
            relative = path.relative_to(snapshot).as_posix()
            info = ZipInfo(f"VeriPlan/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes(), compresslevel=9)


def _safe_targets(source: Path, output: Path, archive: Path) -> None:
    if output == source or output in source.parents:
        raise BuildError("output cannot be the source repository or one of its parents")
    if archive == source or archive in source.parents:
        raise BuildError("archive cannot be the source repository or one of its parents")
    if archive == output or archive.is_relative_to(output):
        raise BuildError("archive must be outside the snapshot directory")


def build(source: Path, output: Path, archive: Path, *, force: bool = False) -> dict:
    source = source.resolve()
    output = output.resolve()
    archive = archive.resolve()
    _safe_targets(source, output, archive)
    if not source.is_dir():
        raise BuildError(f"source repository does not exist: {source}")
    if not force and (output.exists() or archive.exists()):
        raise BuildError("output already exists; choose a new path or pass --force")

    _require_clean_allowlist(source)
    files = _collect_files(source)
    findings = _secret_findings(source, files)
    if findings:
        descriptions = ", ".join(f"{path} ({label})" for path, label in findings)
        raise BuildError(f"secret scan found unsafe material: {descriptions}")

    output.parent.mkdir(parents=True, exist_ok=True)
    archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".veriplan-snapshot-", dir=output.parent))
    archive_handle, archive_name = tempfile.mkstemp(
        prefix=".veriplan-archive-", suffix=".zip", dir=archive.parent
    )
    os.close(archive_handle)
    temporary_archive = Path(archive_name)
    try:
        manifest = _write_manifest(source, temporary, files)
        _write_archive(temporary, temporary_archive)
        if force:
            if output.is_dir():
                shutil.rmtree(output)
            elif output.exists():
                output.unlink()
            if archive.exists():
                archive.unlink()
        temporary.replace(output)
        temporary_archive.replace(archive)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        temporary_archive.unlink(missing_ok=True)
        if output.exists() and not archive.exists():
            shutil.rmtree(output, ignore_errors=True)
        raise

    archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    return {
        "source_commit": manifest["source_commit"],
        "file_count": len(manifest["files"]),
        "secret_findings": 0,
        "output": str(output),
        "archive": str(archive),
        "archive_sha256": archive_sha256,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="source repository (defaults to this script's repository)",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    archive = args.archive or args.output.with_suffix(".zip")
    try:
        summary = build(args.source, args.output, archive, force=args.force)
    except BuildError as error:
        print(f"snapshot build failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
