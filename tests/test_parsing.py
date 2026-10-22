"""
test_parsing.py - checks that every PDF can be read back into text correctly.

The most important check: every value printed on every report can be found in the
extracted text. If the text is missing or garbled, the LLM could never extract it
correctly, so this protects the whole pipeline that comes after.
"""

import csv

import pytest

from medrag.parsing import load_documents, parse_pdf
from medrag.synthetic.generate import generate


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    """Generate the synthetic data once, into a temporary folder."""
    folder = tmp_path_factory.mktemp("synthetic")
    generate(folder, seed=42)
    return folder


@pytest.fixture(scope="module")
def docs(data):
    """Parse every PDF once, as {doc_id: ParsedDocument}, for quick lookups."""
    return {d.doc_id: d for d in load_documents(data / "patients")}


def read(data, name):
    """Read one answer-key CSV as a list of dictionaries."""
    with (data / "ground_truth" / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_every_document_is_parsed_with_the_right_id(docs, data):
    """The IDs we build from file names match the IDs in the answer key exactly."""
    assert set(docs) == {d["doc_id"] for d in read(data, "documents")}


def test_every_printed_result_can_be_found_in_the_text(docs, data):
    """Every test name, value and unit on every lab report is in the extracted text."""
    for r in read(data, "lab_results"):
        text = docs[r["doc_id"]].text
        assert r["test_name_printed"] in text, r
        assert r["value_printed"] in text, r
        assert r["unit_printed"] in text, r


def test_every_medicine_can_be_found_in_its_prescription(docs, data):
    for m in read(data, "medications"):
        text = docs[m["start_doc_id"]].text
        assert m["drug"] in text and m["strength"] in text, m


def test_clinic_note_text_can_be_found(docs, data):
    """A distinctive phrase from each note's findings appears in the extracted text."""
    for n in read(data, "clinic_notes"):
        # Compare the first 40 characters, ignoring line breaks added by the PDF layout
        text = " ".join(docs[n["doc_id"]].text.split())
        assert n["findings"][:40] in text, n["doc_id"]


def test_every_page_says_synthetic(docs):
    """The disclaimer footer is present, so no document can be mistaken for real."""
    for d in docs.values():
        assert "SYNTHETIC DATA" in d.text, d.doc_id


def test_page_numbers_start_at_one(docs):
    for d in docs.values():
        assert d.pages[0].page_number == 1


def test_load_one_patient_in_date_order(data):
    docs = load_documents(data / "patients", "P003")
    assert docs and all(d.patient_id == "P003" for d in docs)
    assert [d.date for d in docs] == sorted(d.date for d in docs)


def test_rejects_badly_named_files(tmp_path):
    """A file that doesn't follow the naming convention gives a clear error."""
    bad = tmp_path / "P001" / "scan.pdf"
    bad.parent.mkdir()
    bad.write_bytes(b"%PDF-1.4")
    with pytest.raises(ValueError):   # the test passes only if ValueError is raised
        parse_pdf(bad)