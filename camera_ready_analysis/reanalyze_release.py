"""Run reanalyze.py in the public release.

reanalyze.py first verifies the baseline snapshot AND the pre-revision original
directory, which is not distributed. This wrapper verifies only the snapshot hashes
in baseline_manifest.json (skipping the three withheld peer-review files) and then
runs the unchanged reanalysis. Afterwards, `seal_revision.py --verify` confirms the
regenerated results are byte-identical to the published ones.
"""
import hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
WITHHELD = {"reviews.md", "SUBMISSION_PREP.md", "review_2026-09-24/DEEP_REVIEW.md"}

import reanalyze  # noqa: E402


def verify_snapshot():
    manifest = json.loads((ROOT / "baseline_manifest.json").read_text())
    bad = [i["path"] for i in manifest["files"] if i["path"] not in WITHHELD and
           hashlib.sha256((ROOT / "baseline" / i["path"]).read_bytes()).hexdigest() != i["sha256"]]
    if bad:
        raise SystemExit("Snapshot changed: " + ", ".join(bad))
    print(f"Verified {len(manifest['files']) - len(WITHHELD)} snapshot files ({len(WITHHELD)} withheld).")


reanalyze.verify = verify_snapshot
reanalyze.main()
