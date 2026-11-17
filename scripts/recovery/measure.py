"""Evaluate operator-recorded restore timestamps; performs no AWS operations."""

import argparse
import json
from datetime import datetime
from pathlib import Path


def measure(record):
    def stamp(key):
        result = datetime.fromisoformat(record[key].replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("Timestamps require timezone")
        return result

    incident = stamp("incident_at")
    restored = stamp("ready_and_verified_at")
    latest = stamp("latest_recovered_commit_at")
    if not latest <= incident <= restored:
        raise ValueError("Inconsistent recovery timestamps")
    if (
        record.get("database_invariants_passed") is not True
        or record.get("images_verified") is not True
    ):
        raise ValueError("Database correctness and image verification are required")
    if not record.get("evidence_paths"):
        raise ValueError("Attach source evidence paths")
    rpo = (incident - latest).total_seconds()
    rto = (restored - incident).total_seconds()
    return {
        "rpo_seconds": rpo,
        "rto_seconds": rto,
        "rpo_target_seconds": 900,
        "rto_target_seconds": 3600,
        "targets_met": rpo <= 900 and rto <= 3600,
        "evidence_paths": record["evidence_paths"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    result = measure(json.loads(args.record.read_text()))
    print(json.dumps(result, indent=2))
    if not result["targets_met"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
