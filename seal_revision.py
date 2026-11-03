"""Hash the reviewed v2 source and derived results, separately from the v1 archive."""

import argparse
import hashlib
import json
from pathlib import Path
import platform

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "revision_manifest.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(verify_only):
    if verify_only:
        report = json.loads(MANIFEST.read_text())
        for entry in report["files"]:
            if digest(HERE / entry["path"]) != entry["sha256"]:
                raise SystemExit(f"Revision file changed: {entry['path']}")
        print(f"Verified {len(report['files'])} revision source/result files.")
        return
    sources = [p for p in HERE.iterdir() if p.is_file() and p.suffix in {".py", ".md", ".txt"}]
    outputs = [p for p in (HERE / "results").rglob("*") if p.is_file()]
    paths = sorted(sources + outputs + [HERE / "baseline_manifest.json"])
    report = {
        "revision": "2.0-local-simulator-and-historical-reanalysis",
        "python": platform.python_version(), "fresh_model_runs": 0, "external_deployments": 0,
        "final_local_validation": "results/local_validation_02/summary.json",
        "files": [{"path": p.relative_to(HERE).as_posix(), "bytes": p.stat().st_size, "sha256": digest(p)} for p in paths],
        "notes": "Hashes freeze the current outputs. Rescoring regenerates derived files; reseal after intentional changes.",
    }
    MANIFEST.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Sealed {len(paths)} revision source/result files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    main(parser.parse_args().verify)
