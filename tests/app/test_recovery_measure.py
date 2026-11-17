"""Recovery evidence evaluation is offline and never creates cloud resources."""

import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "recovery_measure",
    Path(__file__).resolve().parents[2] / "scripts/recovery/measure.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BASE = {
    "incident_at": "2026-11-17T01:00:00Z",
    "ready_and_verified_at": "2026-11-17T01:45:00Z",
    "latest_recovered_commit_at": "2026-11-17T00:50:00Z",
    "database_invariants_passed": True,
    "images_verified": True,
    "evidence_paths": ["fixture-only"],
}


def test_measured_objectives():
    result = module.measure(BASE)
    assert (
        result["rpo_seconds"] == 600
        and result["rto_seconds"] == 2700
        and result["targets_met"]
    )


def test_over_budget_is_reported():
    assert not module.measure(BASE | {"ready_and_verified_at": "2026-11-17T02:45:00Z"})[
        "targets_met"
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"images_verified": False},
        {"evidence_paths": []},
        {"latest_recovered_commit_at": "2026-11-17T01:01:00Z"},
    ],
)
def test_missing_or_inconsistent_evidence_refused(change):
    with pytest.raises(ValueError):
        module.measure(BASE | change)
