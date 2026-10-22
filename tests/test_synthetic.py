"""
test_synthetic.py - automated checks for the synthetic data generator.

Run all tests from the project folder with:
    pytest

How pytest works:
    - It finds files named test_*.py and runs every function whose name starts with test_.
    - Inside a test, `assert something` means "this must be true". If it's false, the test
      FAILS and pytest shows what went wrong. If no assert fails, the test PASSES.
    - The text after the comma in an assert (assert x, "message") is shown when it fails.

The checks are in four groups:
    1. Medical consistency  - patients only get tests and medicines that fit their conditions
    2. Completeness         - every expected file and answer-key row exists and links up
    3. Helper functions     - small calculations give known correct answers
    4. Reproducibility      - the same seed always gives identical output
"""

import csv

import pytest

from medrag.synthetic.catalog import (CONDITIONS, PLAUSIBLE_LIMITS, ROUTINE_TESTS,
                                      hba1c_pct_to_mmol_mol)
from medrag.synthetic.generate import generate, interpolate
from medrag.synthetic.patients import PATIENTS


# =============================================================================
# SHARED SET-UP
# =============================================================================

@pytest.fixture(scope="module")
def out(tmp_path_factory):
    """
    Generate a fresh copy of all the data into a temporary folder.

    A "fixture" is set-up code that tests can ask for by name: any test with a
    parameter called `out` receives this folder. scope="module" means it runs only
    ONCE for this whole file, not once per test, which keeps the tests fast.

    Using a temporary folder means tests never touch your real data/ folder.
    """
    folder = tmp_path_factory.mktemp("synthetic")
    generate(folder, seed=42)
    return folder


def read(out, name):
    """Read one answer-key CSV, e.g. read(out, "lab_results"), as a list of dictionaries."""
    with (out / "ground_truth" / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# =============================================================================
# 1. MEDICAL CONSISTENCY
# =============================================================================
# @pytest.mark.parametrize runs the same test once per patient, and reports each
# separately (e.g. "test_every_medicine_fits_a_condition[P002] FAILED"), so you can
# see exactly which patient has the problem.

@pytest.mark.parametrize("patient", PATIENTS, ids=lambda p: p.patient_id)
def test_every_medicine_fits_a_condition(patient):
    """No medicine unless it's used for one of this patient's conditions."""
    # Combine the medicine lists of all this patient's conditions into one set
    allowed = set().union(*(CONDITIONS[c].medicines for c in patient.conditions))
    for med in patient.medications:
        assert med.drug in allowed, f"{med.drug} doesn't fit {patient.conditions}"


@pytest.mark.parametrize("patient", PATIENTS, ids=lambda p: p.patient_id)
def test_every_test_fits_a_condition(patient):
    """No lab test unless it's routine or monitored for one of this patient's conditions."""
    allowed = ROUTINE_TESTS.union(*(CONDITIONS[c].tests for c in patient.conditions))
    for month, codes in patient.visits.items():
        for code in codes:
            assert code in allowed, f"{code} at month {month} doesn't fit {patient.conditions}"


def test_values_are_physically_possible(out):
    """Every generated value is within the limits a living person could have."""
    for r in read(out, "lab_results"):
        low, high = PLAUSIBLE_LIMITS[r["test_code"]]
        assert low <= float(r["value_standard"]) <= high, r


def test_flags_match_the_normal_range(out):
    """Every H/L flag on a report agrees with the normal range printed next to it."""
    for r in read(out, "lab_results"):
        value = float(r["value_printed"])
        low = float(r["ref_low"]) if r["ref_low"] else None     # "" in the CSV means no limit
        high = float(r["ref_high"]) if r["ref_high"] else None

        if high is not None and value > high:
            expected = "H"
        elif low is not None and value < low:
            expected = "L"
        else:
            expected = ""
        assert r["flag"] == expected, r


# =============================================================================
# 2. COMPLETENESS
# =============================================================================

def test_every_document_was_created(out):
    """Every document listed in the answer key exists as a real PDF file."""
    for doc in read(out, "documents"):
        assert (out / doc["file"]).is_file(), doc["file"]


def test_each_patient_has_all_document_types(out):
    """Each patient has at least one lab report, prescription and clinic note."""
    docs = read(out, "documents")
    for p in PATIENTS:
        types = {d["doc_type"] for d in docs if d["patient_id"] == p.patient_id}
        assert types == {"lab_report", "prescription", "clinic_note"}, p.patient_id


def test_built_in_surprises_point_at_real_results(out):
    """Every event in events.csv refers to a test that's really on that report."""
    results = read(out, "lab_results")
    for e in read(out, "events"):
        found = any(r["doc_id"] == e["doc_id"] and r["test_code"] == e["test_code"] for r in results)
        assert found, e


def test_clinic_notes_have_no_unfilled_placeholders(out):
    """No {CODE@month} placeholder was left behind in any clinic note."""
    for note in read(out, "clinic_notes"):
        for section in ("reason", "findings", "plan"):
            assert "{" not in note[section] and "@" not in note[section], note


def test_hba1c_units_change_when_patient_switches_lab(out):
    """Arun's HbA1c appears in both % (Kestrel) and mmol/mol (Bluegum)."""
    units = {r["unit_printed"] for r in read(out, "lab_results")
             if r["patient_id"] == "P001" and r["test_code"] == "HBA1C"}
    assert units == {"%", "mmol/mol"}


# =============================================================================
# 3. HELPER FUNCTIONS
# =============================================================================

def test_hba1c_conversion():
    """7.0% is a well-known reference point: it equals 53 mmol/mol."""
    assert round(hba1c_pct_to_mmol_mol(7.0)) == 53


def test_interpolate():
    """Halfway between two points gives the midpoint; outside the range stays flat."""
    points = [(0, 10.0), (10, 20.0)]
    assert interpolate(points, 5) == 15.0     # halfway
    assert interpolate(points, -1) == 10.0    # before the first point
    assert interpolate(points, 99) == 20.0    # after the last point


# =============================================================================
# 4. REPRODUCIBILITY
# =============================================================================

def test_same_seed_gives_identical_data(out, tmp_path):
    """Generating again with the same seed gives byte-for-byte identical answer keys."""
    generate(tmp_path, seed=42)   # tmp_path is a second, separate temporary folder
    for name in ("lab_results", "clinic_notes", "documents"):
        first = (out / "ground_truth" / f"{name}.csv").read_bytes()
        second = (tmp_path / "ground_truth" / f"{name}.csv").read_bytes()
        assert first == second, name