"""
test_extraction.py - checks the extraction and evaluation code WITHOUT calling OpenAI.

Instead of the real LLM, these tests use fake "extractors": small functions that
return answers we choose. That makes the tests free, fast, and repeatable, and lets
us check exactly how our code handles both perfect and flawed LLM answers.
"""

import csv
import io
import json
from typing import get_args

import pytest

from medrag.evaluation import evaluate_extraction
from medrag.extraction import (ExtractedReport, ExtractedResult, TestCode, extract_report,
                               range_flag, to_rows, to_standard)
from medrag.parsing import load_documents
from medrag.synthetic.catalog import TESTS
from medrag.synthetic.generate import generate


# =============================================================================
# SHARED SET-UP
# =============================================================================

@pytest.fixture(scope="module")
def data(tmp_path_factory):
    """Generate the synthetic data once, into a temporary folder."""
    folder = tmp_path_factory.mktemp("synthetic")
    generate(folder, seed=42)
    return folder


@pytest.fixture(scope="module")
def truth(data):
    """The answer key: every printed lab result."""
    with (data / "ground_truth" / "lab_results.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def lab_reports(data):
    """Every lab report, parsed, as {doc_id: ParsedDocument}."""
    return {d.doc_id: d for d in load_documents(data / "patients") if d.doc_type == "lab_report"}


def perfect_answer(doc_id: str, truth: list[dict]) -> ExtractedReport:
    """Build the ExtractedReport a perfect LLM would return for one document."""
    rows = [t for t in truth if t["doc_id"] == doc_id]

    def num(text):
        return None if text == "" else float(text)

    return ExtractedReport(
        lab_name=rows[0]["lab"],
        collected_date=rows[0]["collected_date"],
        results=[ExtractedResult(test_name=t["test_name_printed"], test_code=t["test_code"],
                                 value=float(t["value_printed"]), unit=t["unit_printed"],
                                 ref_low=num(t["ref_low"]), ref_high=num(t["ref_high"]),
                                 flag=t["flag"]) for t in rows],
    )


def as_csv_rows(rows: list[dict]) -> list[dict]:
    """
    Write rows to an in-memory CSV and read them back, exactly like the real scripts
    do via extracted_results.csv. This makes sure the evaluation copes with CSV quirks
    (everything becomes text, None becomes an empty string).
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return list(csv.DictReader(buffer))


# =============================================================================
# 1. SCHEMA
# =============================================================================

def test_test_codes_match_the_catalog():
    """The hand-written TestCode list must match catalog.TESTS (plus UNKNOWN) exactly."""
    assert set(get_args(TestCode)) == set(TESTS) | {"UNKNOWN"}


def test_schema_rejects_an_invented_test_code():
    """Pydantic refuses any code that isn't in the list, so a made-up code can't slip through."""
    with pytest.raises(ValueError):
        ExtractedResult(test_name="Vitamin D", test_code="VITD", value=50, unit="nmol/L",
                        ref_low=50, ref_high=None, flag="")


# =============================================================================
# 2. CALCULATIONS DONE IN CODE (never by the LLM)
# =============================================================================

@pytest.mark.parametrize("value, low, high, expected", [
    (5.5, 3.0, 5.4, "H"),     # above the range
    (2.9, 3.0, 5.4, "L"),     # below the range
    (4.0, 3.0, 5.4, ""),      # inside the range
    (5.4, 3.0, 5.4, ""),      # exactly on the upper limit counts as normal (the real LLM mistake)
    (3.0, 3.0, 5.4, ""),      # exactly on the lower limit counts as normal
    (51, 60, None, "L"),      # only a lower limit, e.g. eGFR "> 60"
    (3.1, None, 2.5, "H"),    # only an upper limit, e.g. "< 2.5"
])
def test_range_flag(value, low, high, expected):
    assert range_flag(value, low, high) == expected


def test_to_standard_converts_hba1c_from_mmol_mol():
    assert to_standard("HBA1C", 53, "mmol/mol") == (7.0, "%")


def test_to_standard_keeps_values_already_in_standard_units():
    assert to_standard("K", 4.6, "mmol/L") == (4.6, "mmol/L")
    assert to_standard("CREAT", 139, "umol/L") == (139, "µmol/L")   # "u" accepted for "µ"


def test_to_standard_gives_up_on_unknowns():
    assert to_standard("UNKNOWN", 1.0, "mmol/L") == (None, None)
    assert to_standard("K", 4.6, "mg/dL") == (None, None)            # unit we can't convert


# =============================================================================
# 3. CACHING
# =============================================================================

def test_each_report_is_sent_to_the_llm_only_once(lab_reports, truth, tmp_path):
    doc = next(iter(lab_reports.values()))
    calls = []

    def fake_llm(text):
        calls.append(text)
        return perfect_answer(doc.doc_id, truth), {"input_tokens": 100, "output_tokens": 50}

    first = extract_report(doc, tmp_path, extractor=fake_llm)
    second = extract_report(doc, tmp_path, extractor=fake_llm)

    assert len(calls) == 1          # second time came from the cache
    assert first == second          # and gave the same answer
    saved = json.loads((tmp_path / f"{doc.doc_id}.json").read_text(encoding="utf-8"))
    assert saved["usage"] == {"input_tokens": 100, "output_tokens": 50}


def test_only_lab_reports_can_be_extracted(data, tmp_path):
    prescription = next(d for d in load_documents(data / "patients") if d.doc_type == "prescription")
    with pytest.raises(ValueError):
        extract_report(prescription, tmp_path, extractor=lambda text: None)


# =============================================================================
# 4. EVALUATION
# =============================================================================

def all_rows(lab_reports, truth, tamper=None):
    """Run every report through a fake LLM (optionally tampering with its answers) and return CSV rows."""
    rows = []
    for doc_id, doc in lab_reports.items():
        answer = perfect_answer(doc_id, truth)
        if tamper:
            tamper(doc_id, answer)
        rows += to_rows(doc, answer)
    return as_csv_rows(rows)


def test_perfect_answers_score_100_percent(lab_reports, truth):
    report = evaluate_extraction(truth, all_rows(lab_reports, truth))
    for name, score in report.scores.items():
        assert score.correct == score.total, name
    assert report.errors == []


def test_evaluation_catches_each_kind_of_mistake(lab_reports, truth):
    """Plant one of each mistake and check every one is detected and reported."""
    target = "P002-LAB-2024-11-05"

    def tamper(doc_id, answer):
        if doc_id != target:
            return
        results = answer.results
        results[0].flag = "L"                    # wrong flag read from the page
        results[1].test_code = "HDL"             # wrong code mapping
        results[2].value += 1                    # wrong value
        del results[3]                           # a missing result
        results.append(ExtractedResult(test_name="Vitamin D", test_code="UNKNOWN", value=80,
                                       unit="nmol/L", ref_low=50, ref_high=None, flag=""))  # made up

    report = evaluate_extraction(truth, all_rows(lab_reports, truth, tamper))
    found = {(e["doc_id"], e["field"]) for e in report.errors}

    assert (target, "flag") in found
    assert (target, "code") in found
    assert (target, "value") in found
    assert (target, "found") in found
    assert (target, "not_on_report") in found
    assert report.not_on_report == 1
    # The LLM's flag on Fasting Glucose was wrong, but the flag calculated in code is still right
    computed_flag_errors = [e["test"] for e in report.errors if e["field"] == "flag_computed"]
    assert "Fasting Glucose" not in computed_flag_errors