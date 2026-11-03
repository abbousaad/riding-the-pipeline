"""Verify preserved evidence, reanalysis inputs, and local execution regressions."""

import hashlib
import io
import json
from pathlib import Path
import unittest

from preserve_baseline import verify

HERE = Path(__file__).resolve().parent


def main():
    verify()
    manifest = json.loads((HERE / "results/historical_reanalysis/observation_manifest.json").read_text())
    if len(manifest["observations"]) != 174:
        raise AssertionError("Expected 174 mapped observations")
    for record in manifest["observations"]:
        for stem in ("trace", "embedding"):
            path = HERE / record[f"{stem}_path"]
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != record[f"{stem}_sha256"]:
                raise AssertionError(f"Changed analysis input: {path}")
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_harness.py")
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "successful": result.wasSuccessful(), "preserved_files_verified": 425,
              "historical_observation_mappings_verified": len(manifest["observations"]),
              "kind": "offline code/evidence verification; no model measurements", "test_log": stream.getvalue()}
    (HERE / "results/verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(stream.getvalue())
    print("Historical trace/vector hashes verified; verification.json saved.")
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
