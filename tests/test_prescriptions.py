"""
test_prescriptions.py - checks prescription extraction, the medication timeline and its
evaluation, using fake LLM answers (no OpenAI calls).
"""

import csv

import pytest

from medrag.evaluation import evaluate_prescriptions
from medrag.parsing import load_documents
from medrag.prescriptions import (ExtractedPrescription, PrescribedMedicine, build_timeline,
                                  extract_prescription)
from medrag.synthetic.generate import generate


# =============================================================================
# SHARED SET-UP
# =============================================================================

@pytest.fixture(scope="module")
def data(tmp_path_factory):
    folder = tmp_path_factory.mktemp("synthetic")
    generate(folder, seed=42)
    return folder


@pytest.fixture(scope="module")
def truth(data):
    """The answer key: every medication course."""
    with (data / "ground_truth" / "medications.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def prescription_docs(data):
    return [d for d in load_documents(data / "patients") if d.doc_type == "prescription"]


def perfect_answer(doc, truth) -> ExtractedPrescription:
    """What a perfect LLM would read from one prescription: every medicine active on its date."""
    active = [m for m in truth if m["patient_id"] == doc.patient_id and m["start_date"] <= doc.date
              and (m["end_date"] == "" or m["end_date"] > doc.date)]
    return ExtractedPrescription(
        issued_date=doc.date, prescriber="Dr Test", notes="",
        medicines=[PrescribedMedicine(name=m["drug"], strength=m["strength"],
                                      directions=m["instructions"]) for m in active],
    )


def rx(date, *medicines):
    """Shorthand for building a prescription in tests: rx("2024-01-01", ("Metformin", "500 mg"))."""
    return ExtractedPrescription(issued_date=date, prescriber="Dr Test", notes="",
                                 medicines=[PrescribedMedicine(name=n, strength=s, directions="daily")
                                            for n, s in medicines])


# =============================================================================
# TIMELINE (code)
# =============================================================================

def test_timeline_detects_start_dose_change_and_stop():
    history = [
        ("P1", "RX-1", rx("2024-01-01", ("Metformin", "500 mg"), ("Atorvastatin", "20 mg"))),
        ("P1", "RX-2", rx("2024-04-01", ("Metformin", "1000 mg"), ("Atorvastatin", "20 mg"))),
        ("P1", "RX-3", rx("2024-09-01", ("Metformin", "1000 mg"), ("Rosuvastatin", "10 mg"))),
    ]
    courses, changes = build_timeline(history)

    summary = [(c.date, c.drug, c.change) for c in changes]
    assert summary == [
        ("2024-01-01", "Metformin", "started"),
        ("2024-01-01", "Atorvastatin", "started"),
        ("2024-04-01", "Metformin", "dose_changed"),
        ("2024-09-01", "Atorvastatin", "stopped"),
        ("2024-09-01", "Rosuvastatin", "started"),
    ]
    # Metformin 500 mg ran from January until it was changed in April
    first = next(c for c in courses if c.strength == "500 mg")
    assert (first.start_date, first.end_date) == ("2024-01-01", "2024-04-01")


def test_timeline_works_in_any_input_order():
    """Prescriptions arrive in random order; the timeline sorts them by date."""
    history = [("P1", "RX-2", rx("2024-04-01", ("Metformin", "1000 mg"))),
               ("P1", "RX-1", rx("2024-01-01", ("Metformin", "500 mg")))]
    _, changes = build_timeline(history)
    assert [c.change for c in changes] == ["started", "dose_changed"]


def test_unchanged_repeat_prescription_records_nothing():
    history = [("P1", "RX-1", rx("2024-01-01", ("Levothyroxine", "100 microgram"))),
               ("P1", "RX-2", rx("2024-06-01", ("Levothyroxine", "100 microgram")))]
    courses, changes = build_timeline(history)
    assert len(changes) == 1 and len(courses) == 1


def test_perfect_reading_rebuilds_the_answer_key_exactly(prescription_docs, truth):
    history = [(d.patient_id, d.doc_id, perfect_answer(d, truth)) for d in prescription_docs]
    courses, _ = build_timeline(history)
    built = {(c.patient_id, c.drug, c.strength, c.start_date, c.end_date or "") for c in courses}
    expected = {(m["patient_id"], m["drug"], m["strength"], m["start_date"], m["end_date"]) for m in truth}
    assert built == expected


# =============================================================================
# EXTRACTION (fake LLM) AND EVALUATION
# =============================================================================

def test_each_prescription_is_sent_to_the_llm_only_once(prescription_docs, truth, tmp_path):
    doc = prescription_docs[0]
    calls = []

    def fake_llm(text):
        calls.append(1)
        return perfect_answer(doc, truth), {"input_tokens": 10, "output_tokens": 5}

    extract_prescription(doc, tmp_path, parser=fake_llm)
    extract_prescription(doc, tmp_path, parser=fake_llm)
    assert len(calls) == 1


def test_only_prescriptions_can_be_extracted(data, tmp_path):
    lab_report = next(d for d in load_documents(data / "patients") if d.doc_type == "lab_report")
    with pytest.raises(ValueError):
        extract_prescription(lab_report, tmp_path, parser=lambda text: None)


def evaluate(prescription_docs, truth, tamper=None):
    """Build fake LLM answers (optionally tampered with), the timeline, and the evaluation."""
    extracted = []
    for d in prescription_docs:
        answer = perfect_answer(d, truth)
        if tamper:
            tamper(d, answer)
        extracted.append((d.patient_id, d.doc_id, d.date, answer))
    courses, _ = build_timeline([(p, doc_id, a) for p, doc_id, _, a in extracted])
    return evaluate_prescriptions(truth, extracted, courses)


def test_perfect_answers_score_100_percent(prescription_docs, truth):
    report = evaluate(prescription_docs, truth)
    assert all(s.correct == s.total for s in report.scores.values())
    assert report.errors == []


def test_evaluation_catches_planted_mistakes(prescription_docs, truth):
    target = prescription_docs[2].doc_id   # P001's third prescription (2024-07-15)

    def tamper(doc, answer):
        if doc.doc_id != target:
            return
        answer.medicines[0].strength = "850 mg"                                   # wrong strength
        answer.medicines.append(PrescribedMedicine(name="Aspirin", strength="100 mg",
                                                   directions="daily"))           # made up

    report = evaluate(prescription_docs, truth, tamper)
    fields = {e["field"] for e in report.errors if e["doc_id"] == target}
    assert "strength" in fields
    assert "not_on_report" in fields
    assert report.not_on_report == 1
    # A misread strength also breaks the medication timeline, and that is caught too
    assert report.scores["course"].correct < report.scores["course"].total