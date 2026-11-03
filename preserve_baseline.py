"""Snapshot the pre-revision evidence without copying credentials or environments."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASELINE = HERE / "baseline"
MANIFEST = HERE / "baseline_manifest.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected_files():
    files = []
    for folder in ("IEEE_Conference", "poc", "review_2026-09-24"):
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(ROOT)
            if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                continue
            if path.suffix in {".py", ".md", ".yaml", ".json", ".tex", ".bib",
                               ".pdf", ".cls", ".bst", ".bbl", ".log", ".aux", ".blg"}:
                files.append(path)
    files.extend(ROOT / name for name in ("reviews.md", "SUBMISSION_PREP.md"))
    return sorted(files)


def verify():
    manifest = json.loads(MANIFEST.read_text())
    failures = []
    for item in manifest["files"]:
        for label, root in (("snapshot", BASELINE), ("original", ROOT)):
            path = root / item["path"]
            if not path.is_file() or digest(path) != item["sha256"]:
                failures.append(f"{label}: {item['path']}")
    if failures:
        raise RuntimeError("Evidence changed:\n" + "\n".join(failures))
    print(f"Verified {len(manifest['files'])} snapshot files and unchanged originals.")


def create():
    if MANIFEST.exists():
        raise SystemExit("Baseline already exists; use --verify. It will not be overwritten.")
    entries = []
    for path in selected_files():
        rel = path.relative_to(ROOT)
        before = digest(path)
        dest = BASELINE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(path, dest)
        if digest(dest) != before or digest(path) != before:
            raise RuntimeError(f"File changed while snapshotting: {rel}")
        entries.append({"path": rel.as_posix(), "bytes": path.stat().st_size, "sha256": before})
    manifest = {
        "schema": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "label": "Pre-v2 revision baseline, 2026-09-24; includes earlier editorial changes, not certified as-submitted",
        "excludes": ["credentials and all dotfiles", "virtual environments", "bytecode", "symlinks"],
        "files": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    verify()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    verify() if args.verify else create()
