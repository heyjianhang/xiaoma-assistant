"""Package a clean, checked Git revision without credentials or build artifacts."""

import hashlib
import json
import os
import stat
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import check_repository

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return (
        subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )


def main():
    if git("status", "--porcelain", "--untracked-files=all"):
        print(
            "Refusing to package uncommitted changes; commit the reviewed revision first.",
            file=sys.stderr,
        )
        return 1
    if check_repository.main():
        return 1
    revision = git("rev-parse", "HEAD")
    timestamp = int(git("show", "-s", "--format=%ct", "HEAD"))
    paths = check_repository.candidates()
    files = []
    for relative in paths:
        path = ROOT / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("Refusing non-regular source file: " + relative.as_posix())
        content = path.read_bytes()
        files.append(
            {
                "path": relative.as_posix(),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    manifest = {"format_version": 1, "git_revision": revision, "files": files}
    directory = ROOT / "var/deliverables"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "xiaoma-assistant-source.zip"
    temporary = output.with_suffix(".zip.tmp")
    prefix = "xiaoma-assistant/"
    date = time.gmtime(max(timestamp, 315532800))[:6]
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry in files:
                path = ROOT / entry["path"]
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    raise ValueError("Source changed during packaging: " + entry["path"])
                info = zipfile.ZipInfo(prefix + entry["path"], date)
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o755 if path.stat().st_mode & stat.S_IXUSR else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                archive.writestr(info, data)
            info = zipfile.ZipInfo(prefix + "SUBMISSION_MANIFEST.json", date)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        # A submission must identify the exact clean revision, even if an editor
        # saved a file while the archive was being written.
        if git("rev-parse", "HEAD") != revision or git(
            "status", "--porcelain", "--untracked-files=all"
        ):
            raise ValueError("Source changed during packaging; review and commit again")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(digest + "  " + output.name + "\n")
    print(f"Packaged {len(files)} source files at {revision[:12]}: {output.relative_to(ROOT)}")
    print("SHA-256: " + digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
