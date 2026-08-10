#!/usr/bin/env python3
"""Fail if webui lint problems increase above the recorded baseline.

The webui carries 211 eslint errors accumulated before any lint gate existed.
Demanding zero would mean either a huge unrelated cleanup or a permanently
ignored check — both leave the frontend unguarded. A ratchet gets the useful
property immediately: new code cannot add problems, and the baseline can only
move down.

Usage:
    python scripts/eslint_ratchet.py            # check against the baseline
    python scripts/eslint_ratchet.py --update   # lower the baseline after cleanup
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WEBUI = REPO / "webui"
BASELINE = REPO / "scripts" / "eslint_baseline.json"


def measure() -> dict[str, int]:
    if not (WEBUI / "node_modules").is_dir():
        print("webui/node_modules missing — run `npm --prefix webui ci` first")
        raise SystemExit(2)
    proc = subprocess.run(
        ["npx", "eslint", "src", "-f", "json"],
        cwd=WEBUI,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        print("eslint produced no output:\n" + proc.stderr[-2000:])
        raise SystemExit(2)
    report = json.loads(proc.stdout)
    return {
        "errors": sum(f["errorCount"] for f in report),
        "warnings": sum(f["warningCount"] for f in report),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()

    current = measure()

    if args.update or not BASELINE.exists():
        BASELINE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {current}")
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    regressed = [
        f"{k}: {current[k]} > {baseline[k]}"
        for k in ("errors", "warnings")
        if current[k] > baseline[k]
    ]
    if regressed:
        print("eslint regressed against baseline:")
        for line in regressed:
            print("  " + line)
        print("\nFix the new problems, or run with --update if you deliberately")
        print("accepted them (the number should go down over time, not up).")
        return 1

    improved = [
        f"{k}: {current[k]} < {baseline[k]}"
        for k in ("errors", "warnings")
        if current[k] < baseline[k]
    ]
    if improved:
        print("eslint improved — lower the baseline with --update:")
        for line in improved:
            print("  " + line)
    else:
        print(f"eslint at baseline: {current}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
