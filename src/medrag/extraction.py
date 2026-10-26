"""
extraction.py - uses an LLM to turn a lab report's text into clean, structured results.

The problem: after parsing, a lab report is messy text with one table cell per line,
and two labs use different layouts, test names and units. We want tidy rows like:
    test_code=EGFR, test_name="Estimated GFR", value=51, unit="mL/min/1.73m²",
    ref_low=60, ref_high=None, flag="L"

How it works:
    1. SCHEMA     Pydantic classes (ExtractedResult, ExtractedReport) define the exact
                  shape of the answer we want.
    2. PROMPT     Instructions telling the LLM how to read a report, plus our list of
                  standard test codes so it can map "Estimated GFR" -> EGFR.
    3. LLM CALL   OpenAI "structured outputs": the model MUST reply with JSON that fits
                  the schema, and the SDK turns it straight into Python objects.
    4. CACHE      Every answer is saved to a JSON file. A report is only ever sent to
                  OpenAI once; re-runs read the file (free, fast, identical results).
    5. STANDARD   Python, not the LLM, converts units (e.g. HbA1c mmol/mol -> %),
                  because LLMs are unreliable at arithmetic.

Design choice worth knowing: the LLM only READS and MAPS. Every calculation happens
in plain, tested Python code.
"""

import json
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from .config import CHAT_MODEL, get_api_key
from .parsing import ParsedDocument
from .synthetic.catalog import TESTS

# =============================================================================
# 1. SCHEMA: the exact shape of the answer we want from the LLM
# =============================================================================

# The allowed test codes: our 17 standard codes, plus "UNKNOWN" for anything else.
# `Literal[...]` means "only one of these exact values". OpenAI's structured outputs
# enforce it, so the LLM physically can't invent a new code.
#
# They're written out by hand (not built from TESTS) so VS Code's type checker can
# read them. A test in tests/test_extraction.py checks this list always matches
# catalog.TESTS, so the two can't silently drift apart.
TestCode = Literal[
    "HBA1C", "GLU_F", "CREAT", "EGFR", "UACR", "NA", "K",
    "CHOL", "LDL", "HDL", "TRIG", "ALT", "AST", "CK",
    "TSH", "FT4", "HB",
    "UNKNOWN",
]


# Note: class docstrings and Field(description=...) texts are sent to the LLM as part of
# the schema, so they're written as instructions for the model, not notes for developers.

class ExtractedResult(BaseModel):
    """One test result from a pathology report."""
    test_name: str = Field(description="The test name exactly as printed on the report.")
    test_code: TestCode = Field(description="The matching standard code from the list, or UNKNOWN.")
    value: float = Field(description="The numeric result exactly as printed. Do not convert units.")
    unit: str = Field(description="The unit exactly as printed, e.g. 'mmol/L'.")
    ref_low: float | None = Field(description="Lower limit of the reference range, or null if none.")
    ref_high: float | None = Field(description="Upper limit of the reference range, or null if none.")
    flag: Literal["H", "L", ""] = Field(description="'H' if marked high, 'L' if marked low, '' if not marked.")


class ExtractedReport(BaseModel):
    """The lab details and all test results from one pathology report."""
    lab_name: str = Field(description="Name of the laboratory that issued the report.")
    collected_date: str = Field(description="Date the specimen was collected, as YYYY-MM-DD.")
    results: list[ExtractedResult] = Field(description="Every test result on the report, in order.")


# =============================================================================
# 2. PROMPT: instructions for the LLM
# =============================================================================

# One line per standard code, e.g. "- EGFR: eGFR (Kidney Function, mL/min/1.73m²)"
_CODE_LIST = "\n".join(f"- {t.code}: {t.name} ({t.panel}, {t.unit})" for t in TESTS.values())

INSTRUCTIONS = f"""You extract test results from the text of a pathology lab report.

The text comes from a PDF, so table cells may appear one per line. Rebuild each result row.

Rules:
- Include every test result on the report, and nothing that isn't on it.
- Copy test names and units exactly as printed. Copy values exactly; never convert units.
- Reference ranges: "3.5 - 5.2" means ref_low=3.5, ref_high=5.2. "< 3.0" means ref_low=null,
  ref_high=3.0. "> 60" means ref_low=60, ref_high=null.
- Flag: "H" or "L" only if the report marks the result that way (e.g. a Flag column, or
  "7.4 H"). Otherwise use "".
- Dates on the report are written DD/MM/YYYY. Return collected_date as YYYY-MM-DD.
- test_code: choose the standard code below that means the same test, even if the report
  uses a different name (e.g. "Estimated GFR" is EGFR, "LDL-C" is LDL). Use UNKNOWN if
  none matches.

Standard test codes:
{_CODE_LIST}
"""


# =============================================================================
# 3. LLM CALL
# =============================================================================

# Type of an "extractor": any function that takes report text and returns
# (ExtractedReport, token usage). Tests swap in a fake one, so they never call OpenAI.
Extractor = Callable[[str], tuple[ExtractedReport, dict]]


def openai_extractor(model: str = CHAT_MODEL) -> Extractor:
    """
    Create an extractor that calls OpenAI.

    Args:
        model: Which OpenAI model to use (default from .env, e.g. "gpt-4o-mini").

    Returns:
        A function: report text -> (ExtractedReport, {"input_tokens": .., "output_tokens": ..})
    """
    from openai import OpenAI   # imported here so tests don't need the OpenAI package set up

    client = OpenAI(api_key=get_api_key())

    def extract(text: str) -> tuple[ExtractedReport, dict]:
        # responses.parse sends our schema to OpenAI and turns the JSON reply
        # back into an ExtractedReport object for us.
        response = client.responses.parse(
            model=model,
            instructions=INSTRUCTIONS,     # the "system" instructions
            input=text,                    # the report text
            text_format=ExtractedReport,   # the schema the reply must follow
            temperature=0,                 # least random: same input -> (nearly) same output
            # (If you switch to a "reasoning" model such as o-series, remove temperature:
            #  those models don't accept it.)
        )
        usage = {"input_tokens": response.usage.input_tokens,
                 "output_tokens": response.usage.output_tokens}
        return response.output_parsed, usage

    return extract


# =============================================================================
# 4. CACHE: save every LLM answer so each report is only sent once
# =============================================================================

def extract_report(doc: ParsedDocument, cache_dir: Path,
                   extractor: Extractor | None = None, model: str = CHAT_MODEL) -> ExtractedReport:
    """
    Get the structured results for one lab report, using the cache if possible.

    Args:
        doc:       A parsed lab report (from parsing.py).
        cache_dir: Folder of saved answers, one JSON file per document.
        extractor: The function that calls the LLM. Leave as None to use OpenAI;
                   it's only created if the answer isn't already cached.
        model:     Model name, stored in the cache file for reference.

    Returns:
        The ExtractedReport.
    """
    if doc.doc_type != "lab_report":
        raise ValueError(f"{doc.doc_id} is a {doc.doc_type}, not a lab report")

    cache_file = cache_dir / f"{doc.doc_id}.json"
    if cache_file.exists():
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        # model_validate checks the saved JSON still fits the schema
        return ExtractedReport.model_validate(saved["report"])

    if extractor is None:
        extractor = openai_extractor(model)
    report, usage = extractor(doc.text)

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({
        "doc_id": doc.doc_id,
        "model": model,
        "usage": usage,
        "report": report.model_dump(),   # model_dump turns the object into a plain dict
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


# =============================================================================
# 5. STANDARDISE: convert to standard units in Python (never by the LLM)
# =============================================================================

def _same_unit(a: str, b: str) -> bool:
    """Compare units loosely: ignore case and spaces, and treat 'u' and 'µ' as the same."""
    def norm(s: str) -> str:
        return s.replace(" ", "").replace("µ", "u").replace("μ", "u").lower()
    return norm(a) == norm(b)


def to_standard(test_code: str, value: float, unit: str) -> tuple[float | None, str | None]:
    """
    Convert a result into the standard unit for its test (from catalog.TESTS).

    Args:
        test_code: e.g. "HBA1C". If UNKNOWN, no conversion is possible.
        value:     The value as printed.
        unit:      The unit as printed.

    Returns:
        (standard value, standard unit), or (None, None) if we don't know how to convert.

    Examples:
        to_standard("HBA1C", 54, "mmol/mol")  ->  (7.1, "%")
        to_standard("K", 4.6, "mmol/L")       ->  (4.6, "mmol/L")
    """
    test = TESTS.get(test_code)
    if test is None:
        return None, None
    if _same_unit(unit, test.unit):
        return value, test.unit
    if test_code == "HBA1C" and _same_unit(unit, "mmol/mol"):
        # Reverse of the formula in catalog.py: % = mmol/mol / 10.929 + 2.15
        return round(value / 10.929 + 2.15, 1), "%"
    return None, None


def to_rows(doc: ParsedDocument, report: ExtractedReport) -> list[dict]:
    """
    Turn one ExtractedReport into flat table rows (one per result), adding the
    document details and the standardised value.
    """
    rows = []
    for r in report.results:
        value_std, unit_std = to_standard(r.test_code, r.value, r.unit)
        rows.append({
            "doc_id": doc.doc_id, "patient_id": doc.patient_id,
            "collected_date": report.collected_date, "lab": report.lab_name,
            "test_code": r.test_code, "test_name": r.test_name,
            "value": r.value, "unit": r.unit, "ref_low": r.ref_low, "ref_high": r.ref_high,
            "flag": r.flag, "value_standard": value_std, "unit_standard": unit_std,
        })
    return rows