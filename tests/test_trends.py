"""
test_trends.py - checks each change-detection rule on small hand-made histories, then
checks the rules find every change built into the synthetic patients' stories.

No OpenAI calls: the full-dataset tests use the answer key as a "perfect extraction".
"""

import csv

import pytest

from medrag.evaluation import evaluate_changes
from medrag.extraction import range_flag, to_standard
from medrag.parsing import load_documents
from medrag.prescriptions import (ExtractedPrescription, MedicationChange, PrescribedMedicine,
                                  build_timeline)
from medrag.synthetic.generate import generate
from medrag.trends import build_histories, detect_changes


# =============================================================================
# HELPERS
# =============================================================================

def rows(test_code, values, flags=None, patient="P1"):
    """
    Build result rows for one test, one report a month apart, starting January 2024.

    Example:
        rows("EGFR", [70, 68, 51]) -> three eGFR results with doc_ids
        P1-LAB-0, P1-LAB-1, P1-LAB-2, no H/L flags.
    """
    flags = flags or [""] * len(values)
    return [{"patient_id": patient, "test_code": test_code, "doc_id": f"{patient}-LAB-{i}",
             "collected_date": f"2024-{i + 1:02d}-01", "value_standard": v, "flag_computed": f}
            for i, (v, f) in enumerate(zip(values, flags))]


def rules_found(findings, doc_index, patient="P1"):
    """The set of rule names that fired on one report, e.g. {"sudden_change"}."""
    return {f.rule for f in findings if f.doc_id == f"{patient}-LAB-{doc_index}"}


# =============================================================================
# EACH RULE ON ITS OWN
# =============================================================================

def test_out_of_range_only_when_newly_out():
    # Potassium: normal, high, still high, normal
    findings = detect_changes(rows("K", [4.4, 5.8, 5.9, 4.5], ["", "H", "H", ""]), [])
    assert "out_of_range" in rules_found(findings, 1)        # crossed the limit -> alert
    assert "out_of_range" not in rules_found(findings, 2)    # still high: not new -> no repeat


def test_first_result_out_of_range_is_reported():
    findings = detect_changes(rows("TSH", [9.8, 6.4], ["H", "H"]), [])
    assert "out_of_range" in rules_found(findings, 0)


def test_sudden_change_threshold():
    findings = detect_changes(rows("EGFR", [67, 51, 55]), [])
    assert "sudden_change" in rules_found(findings, 1)       # -24%: over the 20% limit
    assert "sudden_change" not in rules_found(findings, 2)   # +8%: under it


def test_change_after_medicine_links_only_related_tests():
    # Atorvastatin (a statin) started between report 1 and report 2.
    # Both LDL and TSH drop afterwards, but statins affect LDL, not thyroid tests.
    change = MedicationChange("P1", "2024-02-15", "P1-RX-1", "Atorvastatin", "started", "20 mg")
    history = rows("LDL", [4.6, 4.5, 3.2]) + rows("TSH", [2.0, 2.0, 1.4])
    findings = detect_changes(history, [change])
    after = [f for f in findings if f.rule == "after_medicine"]
    assert [(f.test_code, f.doc_id) for f in after] == [("LDL", "P1-LAB-2")]   # LDL yes, TSH no
    assert "Atorvastatin was started" in after[0].detail


def test_trend_reversal_needs_an_earlier_opposite_move():
    # HbA1c improves (8.9 -> 7.0), then worsens twice (7.4, 8.2): a reversal
    improving_then_worse = detect_changes(rows("HBA1C", [8.9, 7.6, 7.0, 7.4, 8.2]), [])
    assert "trend_reversal" in rules_found(improving_then_worse, 4)
    # A steady rise with no earlier fall is a trend, but not a REVERSAL
    steady_rise = detect_changes(rows("HBA1C", [6.0, 6.2, 6.6, 7.0]), [])
    assert not any(f.rule == "trend_reversal" for f in steady_rise)


def test_small_wobbles_are_not_reversals():
    # Tiny ups and downs (under 10%) after a fall shouldn't trigger alerts
    findings = detect_changes(rows("EGFR", [80, 70, 69, 68.5, 68.8, 69.1]), [])
    assert not any(f.rule == "trend_reversal" for f in findings)


# =============================================================================
# ON THE FULL SYNTHETIC DATASET
# =============================================================================

@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    """
    Results and medication changes as a PERFECT extraction would produce them,
    built from the answer key. Returns (results, medication_changes, events).
    """
    folder = tmp_path_factory.mktemp("synthetic")
    generate(folder, seed=42)

    def read(name):
        with (folder / "ground_truth" / f"{name}.csv").open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def num(text):
        return None if text == "" else float(text)

    # Lab results: add the standard value and computed flag, just like extraction.to_rows()
    results = []
    for t in read("lab_results"):
        value = float(t["value_printed"])
        standard, _ = to_standard(t["test_code"], value, t["unit_printed"])
        results.append({**t, "value_standard": standard,
                        "flag_computed": range_flag(value, num(t["ref_low"]), num(t["ref_high"]))})

    # Prescriptions: each lists every medicine active on its date
    meds = read("medications")
    prescriptions = []
    for d in [d for d in load_documents(folder / "patients") if d.doc_type == "prescription"]:
        active = [m for m in meds if m["patient_id"] == d.patient_id and m["start_date"] <= d.date
                  and (m["end_date"] == "" or m["end_date"] > d.date)]
        prescriptions.append((d.patient_id, d.doc_id, ExtractedPrescription(
            issued_date=d.date, prescriber="Dr Test", notes="",
            medicines=[PrescribedMedicine(name=m["drug"], strength=m["strength"], directions="")
                       for m in active])))
    _, changes = build_timeline(prescriptions)
    return results, changes, read("events")


def test_rules_catch_every_built_in_change(dataset):
    results, changes, events = dataset
    report = evaluate_changes(events, detect_changes(results, changes), build_histories(results))
    assert report.caught_exact.correct == report.caught_exact.total == 15
    assert report.missed == []


def test_lab_switch_is_not_a_sudden_change(dataset):
    """Arun's HbA1c changes from % to mmol/mol at the new lab; in standard units it barely moves."""
    results, changes, _ = dataset
    hba1c_jumps = [f for f in detect_changes(results, changes)
                   if f.patient_id == "P001" and f.test_code == "HBA1C" and f.rule == "sudden_change"]
    assert hba1c_jumps == []