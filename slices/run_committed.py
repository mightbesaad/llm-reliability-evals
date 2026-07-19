#!/usr/bin/env python3
"""
Run a committed probe set (PROTOCOL.md) against one model — the differential driver.

A committed set is a single yaml holding per-mode probe groups
(`sets: [{mode, instances}, ...]`), authored fresh, whose SHA-256 was committed (git +
witness chain) BEFORE any API call. This driver:

  1. VERIFIES the probe file's SHA-256 against the commitment file and REFUSES to run
     on mismatch — the protocol is enforced in code, not by convention.
  2. Splits the set into per-mode instance files and runs each through that slice's own
     runner as a subprocess (`runner.py --instances ... --live`), reusing every mode's
     real call path (including sycophancy's two-turn flow) and runlib's per-record
     durability. No grader or provider logic is duplicated here.
  3. Leaves per-mode results next to the probe file (default: the same pending/
     directory, which is gitignored) so nothing publishes before the probes do.

Usage:
  source .keys.env && python3 slices/run_committed.py \\
      --probes commitments/pending/2026-07-19-k3-differential.yaml \\
      --commitment commitments/2026-07-19-k3-differential.txt \\
      --model moonshotai/kimi-k3 --samples 3

  --dry-run validates the hash, the mode map, and the per-mode split without any
  network call (used by the test suite).
"""

import argparse
import hashlib
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# mode string (as written in instances/probe files) -> slice directory
MODE_DIRS = {
    "secondary-source-over-trust": "source-overtrust",
    "stale-recall-as-current-fact": "stale-recall",
    "confidence-correctness-miscalibration": "confidence-calibration",
    "sycophancy-capitulation": "sycophancy",
    "false-precision-rigor-theater": "false-precision",
    "second-order-overcorrection": "overcorrection",
    "disconfirmation-avoidance": "disconfirmation-avoidance",
    "premature-self-certification": "premature-certification",
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def committed_hash(commitment_path: str) -> str:
    with open(commitment_path) as fh:
        text = fh.read()
    m = re.search(r"^sha256:\s*([0-9a-f]{64})\s*$", text, re.MULTILINE)
    if not m:
        raise SystemExit(f"no sha256 line found in {commitment_path}")
    return m.group(1)


def verify(probes_path: str, commitment_path: str) -> str:
    actual = sha256_file(probes_path)
    expected = committed_hash(commitment_path)
    if actual != expected:
        raise SystemExit(
            "COMMITMENT MISMATCH — refusing to run.\n"
            f"  probe file : {actual}\n"
            f"  committed  : {expected}\n"
            "The probe set is not the one that was committed. If the edit was\n"
            "legitimate, re-commit (new hash file, git push, witness event) first."
        )
    return actual


def load_sets(probes_path: str) -> list[dict]:
    doc = yaml.safe_load(open(probes_path))
    sets = doc.get("sets") or []
    if not sets:
        raise SystemExit(f"{probes_path} has no 'sets' — nothing to run")
    for s in sets:
        if s["mode"] not in MODE_DIRS:
            raise SystemExit(f"unknown mode {s['mode']!r} — not in MODE_DIRS")
        if not s.get("instances"):
            raise SystemExit(f"mode {s['mode']} has no instances")
    return sets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--probes", required=True)
    ap.add_argument("--commitment", required=True)
    ap.add_argument("--model", default=os.environ.get("EVAL_MODEL", ""))
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--out-dir", default=None,
                    help="results dir (default: the probe file's own directory)")
    ap.add_argument("--dry-run", action="store_true",
                    help="verify + split + plan, no network")
    args = ap.parse_args()

    digest = verify(args.probes, args.commitment)
    sets = load_sets(args.probes)
    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.probes))
    stamp = os.path.basename(args.probes).rsplit(".", 1)[0]
    model_label = (args.model or "MODEL").replace("/", "-")

    print(f"commitment verified: sha256 {digest[:16]}…  ({len(sets)} modes)")

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for s in sets:
            slice_dir = MODE_DIRS[s["mode"]]
            inst_path = os.path.join(tmp, f"{slice_dir}.yaml")
            with open(inst_path, "w") as fh:
                yaml.safe_dump({"mode": s["mode"], "instances": s["instances"]}, fh,
                               sort_keys=False, allow_unicode=True)
            out_path = os.path.join(out_dir, f"{stamp}-{slice_dir}-{model_label}.json")
            cmd = [sys.executable, os.path.join(HERE, slice_dir, "runner.py"),
                   "--instances", inst_path, "--out", out_path,
                   "--samples", str(args.samples)]
            if args.model:
                cmd += ["--model", args.model]
            if args.temperature is not None:
                cmd += ["--temperature", str(args.temperature)]
            if args.base_url:
                cmd += ["--base-url", args.base_url]
            if args.dry_run:
                print(f"  [dry] {slice_dir}: {len(s['instances'])} probe(s) -> {out_path}")
                continue
            cmd.append("--live")
            print(f"  [run] {slice_dir}: {len(s['instances'])} probe(s) × {args.samples} samples")
            rc = subprocess.run(cmd).returncode
            if rc != 0:
                print(f"  [FAIL] {slice_dir} runner exited {rc} — partial results kept at {out_path}")
                failures += 1

    if args.dry_run:
        print("dry-run OK — commitment verified, all modes mapped, split clean")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
