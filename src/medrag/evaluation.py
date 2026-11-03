"""
evaluation.py - scores the LLM's extracted results against the answer key.

Because we generated the data ourselves, we know the correct value of every field on
every report (data/synthetic/ground_truth/lab_results.csv). This file compares the
LLM's output with that answer key and reports how often each field is right.

How results are matched:
    For each document, an extracted row is paired with the answer-key row that has the
    same test name as printed on the report (ignoring case and extra spaces). Matching
    on the printed name, not the test code, means a wrong code shows up as a
    "code mapping" error instead of making the whole result look missing.

Metrics (each is "correct / total"):
    found           answer-key results the LLM extracted at all (recall)
    not_on_report   extracted results that aren't on the report (made-up rows)
    value, unit, range, flag    exact field matches, for results that were found
    flag_computed   the flag our code calculates from value and range (what users see)
    code            mapped to the right standard code, e.g. "Estimated GFR" -> EGFR
    standard_value  converted to the right standard value (e.g. 54 mmol/mol -> 7.1 %)
    date            collected date correct, per document
"""

from collections import defaultdict
from dataclasses import dataclass, field


def _norm(name: str) -> str:
    """Normalise a test name for matching: lower case, single spaces."""
    return " ".join(name.lower().split())


def _num(text: str) -> float | None:
    """Read a number from a CSV cell. Empty cells (or 'None') mean 'no value'."""
    return None if text in ("", "None") else float(text)


def _close(a: float | None, b: float | None, tolerance: float = 1e-6) -> bool:
    """True if both are None, or both are numbers within `tolerance` of each other."""
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tolerance


@dataclass
class Score:
    """A running tally for one metric: how many were correct out of how many."""
    correct: int = 0
    total: int = 0

    def add(self, ok: bool) -> None:
        self.total += 1
        self.correct += int(ok)   # True counts as 1, False as 0

    @property
    def pct(self) -> float:
        return 100 * self.correct / self.total if self.total else 0.0


@dataclass
class ExtractionReport:
    """
    The full result of an evaluation.

    Fields:
        scores:        {metric name: Score} for all documents together.
        by_lab:        {lab name: {metric name: Score}}, to compare the two labs.
        not_on_report: How many extracted rows didn't match anything on the report.
        errors:        One dict per mistake, describing what was expected and what came out.
    """
    scores: dict[str, Score] = field(default_factory=lambda: defaultdict(Score))
    by_lab: dict[str, dict[str, Score]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Score)))
    not_on_report: int = 0
    errors: list[dict] = field(default_factory=list)


FIELDS = ["value", "unit", "range", "flag", "flag_computed", "code", "standard_value"]


def evaluate_extraction(truth_rows: list[dict], extracted_rows: list[dict]) -> ExtractionReport:
    """
    Compare extracted results with the answer key.

    Args:
        truth_rows:     Rows of ground_truth/lab_results.csv (as dicts of strings).
        extracted_rows: Rows of processed/extracted_results.csv (as dicts of strings).

    Returns:
        An ExtractionReport with every score and a list of the mistakes.
    """
    report = ExtractionReport()

    # Group both tables by document, so each report is compared on its own
    truth_by_doc: dict[str, list[dict]] = defaultdict(list)
    for row in truth_rows:
        truth_by_doc[row["doc_id"]].append(row)
    extracted_by_doc: dict[str, list[dict]] = defaultdict(list)
    for row in extracted_rows:
        extracted_by_doc[row["doc_id"]].append(row)

    for doc_id, truths in truth_by_doc.items():
        lab = truths[0]["lab"]
        extracted = extracted_by_doc.get(doc_id, [])

        # Collected date: one check per document
        date_ok = bool(extracted) and extracted[0]["collected_date"] == truths[0]["collected_date"]
        report.scores["date"].add(date_ok)
        report.by_lab[lab]["date"].add(date_ok)
        if not date_ok:
            report.errors.append({"doc_id": doc_id, "test": "(date)", "field": "date",
                                  "expected": truths[0]["collected_date"],
                                  "got": extracted[0]["collected_date"] if extracted else "(no output)"})

        # Look up extracted rows by normalised name. If a name appears twice, keep the first.
        by_name: dict[str, dict] = {}
        for row in extracted:
            by_name.setdefault(_norm(row["test_name"]), row)

        matched_names = set()
        for t in truths:
            key = _norm(t["test_name_printed"])
            e = by_name.get(key)
            report.scores["found"].add(e is not None)
            report.by_lab[lab]["found"].add(e is not None)
            if e is None:
                report.errors.append({"doc_id": doc_id, "test": t["test_name_printed"], "field": "found",
                                      "expected": "present", "got": "missing"})
                continue
            matched_names.add(key)

            # Check each field of a found result
            checks = {
                "value": _close(_num(e["value"]), _num(t["value_printed"])),
                "unit": e["unit"] == t["unit_printed"],
                "range": _close(_num(e["ref_low"]), _num(t["ref_low"]))
                         and _close(_num(e["ref_high"]), _num(t["ref_high"])),
                "flag": e["flag"] == t["flag"],
                "flag_computed": e["flag_computed"] == t["flag"],
                "code": e["test_code"] == t["test_code"],
                # 0.1 tolerance: converting a rounded mmol/mol back to % can differ in the last digit
                "standard_value": _close(_num(e["value_standard"]), _num(t["value_standard"]), 0.1),
            }
            expected = {"value": t["value_printed"], "unit": t["unit_printed"],
                        "range": f'{t["ref_low"]}..{t["ref_high"]}', "flag": t["flag"] or "(none)",
                        "flag_computed": t["flag"] or "(none)", "code": t["test_code"], "standard_value": t["value_standard"]}
            got = {"value": e["value"], "unit": e["unit"], "range": f'{e["ref_low"]}..{e["ref_high"]}',
                   "flag": e["flag"] or "(none)", "flag_computed": e["flag_computed"] or "(none)",
                   "code": e["test_code"], "standard_value": e["value_standard"]}

            for name, ok in checks.items():
                report.scores[name].add(ok)
                report.by_lab[lab][name].add(ok)
                if not ok:
                    report.errors.append({"doc_id": doc_id, "test": t["test_name_printed"], "field": name,
                                          "expected": expected[name], "got": got[name]})

        # Anything extracted that didn't match a real result was made up (or mis-named)
        for key, row in by_name.items():
            if key not in matched_names:
                report.not_on_report += 1
                report.errors.append({"doc_id": doc_id, "test": row["test_name"], "field": "not_on_report",
                                      "expected": "(not on report)", "got": row["value"]})

    return report


def to_markdown(report: ExtractionReport, model: str) -> str:
    """Write the evaluation as a Markdown page (for eval/extraction_report.md and the README)."""
    order = ["found", "date"] + FIELDS
    labels = {"found": "Results found", "date": "Collected date", "value": "Value",
              "unit": "Unit", "range": "Reference range", "flag": "High/low flag (read by LLM)",
              "flag_computed": "High/low flag (calculated in code)",
              "code": "Mapped to standard test code", "standard_value": "Converted to standard unit"}
    labs = sorted(report.by_lab)

    lines = [f"# Extraction evaluation ({model})", "",
             "Every value extracted by the LLM compared with the synthetic data's answer key.", "",
             "| Check | Overall | " + " | ".join(labs) + " |",
             "|---|---|" + "---|" * len(labs)]
    for metric in order:
        s = report.scores[metric]
        cells = [f"{s.pct:.1f}% ({s.correct}/{s.total})"]
        cells += [f"{report.by_lab[lab][metric].pct:.1f}%" for lab in labs]
        lines.append(f"| {labels[metric]} | " + " | ".join(cells) + " |")
    lines += ["", f"Results extracted that are not on the report: **{report.not_on_report}**", ""]

    lines += ["## Mistakes", ""]
    if report.errors:
        lines += ["| Document | Test | Check | Expected | Got |", "|---|---|---|---|---|"]
        lines += [f"| {e['doc_id']} | {e['test']} | {e['field']} | {e['expected']} | {e['got']} |"
                  for e in report.errors]
    else:
        lines.append("None. Every checked field matched the answer key.")
    return "\n".join(lines) + "\n"




# =============================================================================
# PRESCRIPTIONS
# =============================================================================

def evaluate_prescriptions(medication_truth: list[dict], prescriptions: list[tuple],
                           courses: list) -> ExtractionReport:
    """
    Score prescription extraction and the medication timeline against the answer key.

    Args:
        medication_truth: Rows of ground_truth/medications.csv (one per medicine course).
        prescriptions:    (patient_id, doc_id, doc_date, ExtractedPrescription) per prescription.
        courses:          The MedicationCourses built by prescriptions.build_timeline().

    Checks:
        date        issue date read correctly (per prescription)
        found       each medicine the patient was taking appears on the extracted list
        strength, directions   copied exactly, for medicines that were found
        course      each medication course in the answer key was rebuilt exactly
                    (same medicine, strength, start date and end date)
    Extracted medicines that aren't on the prescription count as not_on_report.
    """
    report = ExtractionReport()

    for patient_id, doc_id, doc_date, rx in prescriptions:
        # The medicines this patient was taking on this date, according to the answer key:
        # started on or before the date, and not yet ended
        active = [m for m in medication_truth if m["patient_id"] == patient_id
                  and m["start_date"] <= doc_date and (m["end_date"] == "" or m["end_date"] > doc_date)]

        date_ok = rx.issued_date == doc_date
        report.scores["date"].add(date_ok)
        if not date_ok:
            report.errors.append({"doc_id": doc_id, "test": "(date)", "field": "date",
                                  "expected": doc_date, "got": rx.issued_date})

        extracted = {_norm(m.name): m for m in rx.medicines}
        for m in active:
            e = extracted.pop(_norm(m["drug"]), None)   # pop: remove it, so leftovers are extras
            report.scores["found"].add(e is not None)
            if e is None:
                report.errors.append({"doc_id": doc_id, "test": m["drug"], "field": "found",
                                      "expected": "present", "got": "missing"})
                continue
            for name, expected, got in [("strength", m["strength"], e.strength),
                                        ("directions", m["instructions"], e.directions)]:
                report.scores[name].add(expected == got)
                if expected != got:
                    report.errors.append({"doc_id": doc_id, "test": m["drug"], "field": name,
                                          "expected": expected, "got": got})

        for e in extracted.values():   # anything left over wasn't on the prescription
            report.not_on_report += 1
            report.errors.append({"doc_id": doc_id, "test": e.name, "field": "not_on_report",
                                  "expected": "(not on prescription)", "got": e.strength})

    # Medication timeline: every course in the answer key rebuilt exactly?
    built = {(c.patient_id, _norm(c.drug), c.strength, c.start_date, c.end_date or "") for c in courses}
    for m in medication_truth:
        key = (m["patient_id"], _norm(m["drug"]), m["strength"], m["start_date"], m["end_date"])
        report.scores["course"].add(key in built)
        if key not in built:
            report.errors.append({"doc_id": m["start_doc_id"], "test": f'{m["drug"]} {m["strength"]}',
                                  "field": "course", "expected": f'{m["start_date"]} to {m["end_date"] or "now"}',
                                  "got": "not rebuilt"})
    return report


def prescriptions_to_markdown(report: ExtractionReport, model: str) -> str:
    """Write the prescription evaluation as a Markdown page (for eval/prescription_report.md)."""
    labels = {"date": "Issue date", "found": "Medicines found", "strength": "Strength",
              "directions": "Directions", "course": "Medication courses rebuilt (start and end dates)"}
    lines = [f"# Prescription evaluation ({model})", "",
             "Medicines read from each prescription by the LLM, and the medication timeline built from",
             "them in code, compared with the synthetic data's answer key.", "",
             "| Check | Accuracy |", "|---|---|"]
    for metric, label in labels.items():
        s = report.scores[metric]
        lines.append(f"| {label} | {s.pct:.1f}% ({s.correct}/{s.total}) |")
    lines += ["", f"Medicines extracted that are not on the prescription: **{report.not_on_report}**", "",
              "## Mistakes", ""]
    if report.errors:
        lines += ["| Document | Medicine | Check | Expected | Got |", "|---|---|---|---|---|"]
        lines += [f"| {e['doc_id']} | {e['test']} | {e['field']} | {e['expected']} | {e['got']} |"
                  for e in report.errors]
    else:
        lines.append("None. Every checked field matched the answer key.")
    return "\n".join(lines) + "\n"