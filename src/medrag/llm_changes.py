"""
llm_changes.py - asks an LLM to find important changes in a patient's results, so we can
compare it with the rules in trends.py.

This is the "LLM only" side of the experiment. The LLM gets the SAME information the
rules get (every result in standard units with its H/L flag, plus the medicine changes)
and is asked to find the same four kinds of change. It is NOT given the thresholds
(20%, 10%, ...): the question is whether its own judgement can replace hand-tuned rules.

It may also report a fifth kind, "worth_noting": anything else a doctor would want
highlighted. The rules can't produce that, so it's kept out of the four-kind comparison
and listed separately for a human to judge (useful insight, or noise?).

Optionally it also gets the doctor's clinic notes. That's kept as a separate variant,
because the notes often describe the changes ("eGFR has dropped"), so the LLM can partly
copy the doctor's conclusions instead of detecting them from the numbers.

How it works:
    1. build_patient_input()   Turns one patient's data into a text table for the prompt.
    2. detect_changes_llm()    One LLM call per patient (cached), answer in a fixed schema.
                               The answer becomes trends.Finding objects, so the SAME
                               evaluate_changes() scores both approaches.
    3. check_numbers()         Python checks every number the LLM quoted against the
                               real data. Invented or wrong numbers are the biggest risk
                               of using an LLM in healthcare, so we measure them.
    4. consistency()           Each variant runs several times; how often does the LLM
                               report the same findings? (Rules: always 100%.)
"""

from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .config import CHAT_MODEL
from .extraction import TestCode
from .llm import Parser, cached_parse, make_openai_parser
from .parsing import ParsedDocument
from .synthetic.catalog import TESTS
from .trends import Finding, build_histories

# =============================================================================
# 1. SCHEMA AND PROMPT
# =============================================================================
# As before, these docstrings and descriptions are sent to the LLM as part of the schema.

# The same four kinds of change as the rules, so the two can be compared directly, plus
# "worth_noting" for anything else a doctor would want highlighted. The rules can't produce
# that fifth kind, so it's scored separately (listed for a human to review), never mixed
# into the four-kind comparison.
ChangeKind = Literal["out_of_range", "sudden_change", "after_medicine", "trend_reversal",
                     "worth_noting"]
MAIN_KINDS = {"out_of_range", "sudden_change", "after_medicine", "trend_reversal"}


class LLMFinding(BaseModel):
    """One important change in the patient's results."""
    doc_id: str = Field(description="The lab report ID (from the table) where the change shows up.")
    test_code: TestCode = Field(description="The test's code, exactly as in the table.")
    kind: ChangeKind = Field(description="Which kind of change this is.")
    value: float = Field(description="The result on that report, copied exactly from the table.")
    previous: float | None = Field(
        description="The earlier result it is compared with, copied exactly from the table. "
                    "null for out_of_range on a first result.")
    detail: str = Field(description="One short, factual sentence a patient can understand.")


class LLMFindings(BaseModel):
    """All the important changes found for one patient."""
    findings: list[LLMFinding] = Field(description="Every important change, oldest first.")


# The task, in plain words. Notice: no percentages or thresholds anywhere.
INSTRUCTIONS = """You review a patient's pathology results over time and point out the changes
a careful doctor would want to see. You do not diagnose and you do not give advice.

You get a table of results (one row per test on each lab report, values in standard units,
with H or L if outside the normal range) and the dates the patient's medicines changed.

Report these four kinds of change:
- out_of_range: a result is newly outside the normal range (the previous result for that
  test was not, or it is the first result available).
- sudden_change: a large change in a test since its previous result.
- after_medicine: after a medicine was started, stopped or had its dose changed, a test that
  medicine is known to affect moved clearly. Say that they happened together; never say the
  medicine caused it.
- trend_reversal: a test that had been clearly improving or worsening has turned and moved
  clearly the other way over the last results.

Also report anything else worth highlighting that doesn't fit the four kinds above, as
worth_noting. For example: related tests moving together, a result close to a limit and
getting closer, or a long gap since a test was last checked. Only include things a doctor
would genuinely want to see.

Rules:
- Use only the numbers in the table. Copy values exactly; never calculate new ones.
- doc_id must be a lab report ID from the table, and test_code a code from the table.
- One finding per kind of change, on the report where it first shows up.
- Small ups and downs are normal; don't report them.
"""


# =============================================================================
# 2. BUILDING THE PROMPT INPUT
# =============================================================================

def build_patient_input(patient_id: str, result_rows: list[dict], medication_changes: list,
                        notes: list[ParsedDocument] | None = None,
                        layout: Literal["by_date", "by_test"] = "by_date") -> str:
    """
    Turn one patient's data into the text the LLM reads.

    Args:
        patient_id:         e.g. "P001".
        result_rows:        Rows of extracted_results.csv (any patients; filtered here).
        medication_changes: MedicationChange objects (any patients; filtered here).
        notes:              Parsed clinic notes to include, or None for the
                            results-only variant.
        layout:             How the results are arranged (the data is identical):
                            "by_date"  one table sorted by date, all tests mixed together
                                       (like reading the reports one after another)
                            "by_test"  one block per test, oldest to newest (the same
                                       view the rules get: one time series per test)

    Returns:
        Text with three sections: results, medicine changes, and (optionally) clinic notes.

        by_date example line:
            2025-01-02 | P001-LAB-2025-01-02 | EGFR | eGFR | 51 mL/min/1.73m² | L
        by_test example block:
            EGFR - eGFR (mL/min/1.73m²)
              2024-10-03 | P001-LAB-2024-10-03 | 67 | -
              2025-01-02 | P001-LAB-2025-01-02 | 51 | L
    """
    # build_histories gives the same standardised values the rules use, already
    # grouped into one time series per (patient, test) and sorted oldest first
    histories = build_histories(result_rows)
    mine = {code: points for (pid, code), points in histories.items() if pid == patient_id}

    def value(code, p):
        """A value printed with the test's usual number of decimals, e.g. 51 or 7.4."""
        return f"{p.value:.{TESTS[code].decimals}f}"

    if layout == "by_test":
        lines = ["RESULTS BY TEST (each test oldest to newest: date | report | value | flag)"]
        for code in sorted(mine):
            t = TESTS[code]
            lines += ["", f"{code} - {t.name} ({t.unit})"]
            lines += [f"  {p.date} | {p.doc_id} | {value(code, p)} | {p.flag or '-'}" for p in mine[code]]
    else:
        lines = ["RESULTS (date | report | test code | test | value | flag)"]
        # Keep (date, report, code) alongside the text so we can sort by them
        rows = [(p.date, p.doc_id, code,
                 f"{p.date} | {p.doc_id} | {code} | {TESTS[code].name} | "
                 f"{value(code, p)} {TESTS[code].unit} | {p.flag or '-'}")
                for code, points in mine.items() for p in points]
        # sorted() orders by date, then report, then test; "*_, text" keeps only the text
        lines += [text for *_, text in sorted(rows)]

    lines += ["", "MEDICINE CHANGES (date | medicine | change | detail)"]
    lines += [f"{m.date} | {m.drug} | {m.change} | {m.detail}"
              for m in sorted(medication_changes, key=lambda m: m.date) if m.patient_id == patient_id]

    if notes:
        lines += ["", "CLINIC NOTES"]
        for n in sorted(notes, key=lambda n: n.date):
            if n.patient_id == patient_id:
                lines += [f"--- {n.doc_id} ---", n.text.strip()]
    return "\n".join(lines)


# =============================================================================
# 3. THE LLM CALL (cached, one per patient per run)
# =============================================================================

def detect_changes_llm(patient_id: str, text: str, cache_dir: Path, run: int = 1,
                       parser: Parser | None = None, model: str = CHAT_MODEL) -> list[Finding]:
    """
    Ask the LLM for one patient's important changes.

    Args:
        patient_id: e.g. "P001".
        text:       The output of build_patient_input().
        cache_dir:  Folder for this variant's answers, e.g. llm_cache/changes/gpt-4o-mini_results.
        run:        Run number (1, 2, 3...). Each run is cached separately, so we can
                    measure consistency, and re-running the script costs nothing.
        parser:     The function that calls the LLM. None = OpenAI (only created if needed).
        model:      Model name, stored in the cache file.

    Returns:
        trends.Finding objects (rule = the LLM's "kind"), ready for evaluate_changes().
        Includes worth_noting findings; split them off with MAIN_KINDS before scoring.
    """
    # Cache file name e.g. "P001-run2.json" (cached_parse treats it like a document ID)
    answer = cached_parse(
        f"{patient_id}-run{run}", text, cache_dir, LLMFindings,
        make_parser=lambda: parser or make_openai_parser(LLMFindings, INSTRUCTIONS, model),
        model=model,
    )
    # Convert to the same Finding class the rules produce
    return [Finding(patient_id, f.test_code, f.doc_id, _date_of(f.doc_id), f.kind,
                    f.value, f.previous, f.detail)
            for f in answer.findings]


def _date_of(doc_id: str) -> str:
    """The date at the end of a document ID: "P001-LAB-2025-01-02" -> "2025-01-02"."""
    return doc_id[-10:]


# =============================================================================
# 4. CHECKING THE LLM'S NUMBERS (in code)
# =============================================================================

def check_numbers(findings: list[Finding], result_rows: list[dict]) -> list[dict]:
    """
    Check every number the LLM quoted against the real results.

    A finding has a problem if:
        not_a_result     its report + test combination doesn't exist (e.g. it cited a
                         clinic note, or a test that report didn't include)
        wrong_value      "value" isn't the actual result on that report
        wrong_previous   "previous" isn't any earlier result for that test

    Args:
        findings:    Findings from detect_changes_llm().
        result_rows: Rows of extracted_results.csv (the real data).

    Returns:
        One dict per problem: patient_id, doc_id, test_code, kind, problem, quoted, actual.
    """
    histories = build_histories(result_rows)
    problems = []
    for f in findings:
        points = histories.get((f.patient_id, f.test_code), [])
        here = [p for p in points if p.doc_id == f.doc_id]     # the real result it refers to

        def problem(name, quoted, actual):
            """Record one problem with this finding."""
            problems.append({"patient_id": f.patient_id, "doc_id": f.doc_id, "test_code": f.test_code,
                             "kind": f.rule, "problem": name, "quoted": quoted, "actual": actual})

        if not here:
            problem("not_a_result", f.value, "")
            continue
        if not _same(f.value, here[0].value):
            problem("wrong_value", f.value, here[0].value)
        earlier = [p.value for p in points if p.date < here[0].date]
        if f.previous is not None and not any(_same(f.previous, v) for v in earlier):
            # Show the last 3 real earlier values, to help when reading the report
            problem("wrong_previous", f.previous, ", ".join(f"{v:g}" for v in earlier[-3:]))
    return problems


def _same(a: float, b: float) -> bool:
    """Equal allowing for rounding in the last printed digit (e.g. 7.0 vs 7)."""
    return abs(a - b) <= 0.051 + 0.001 * abs(b)


# =============================================================================
# 5. CONSISTENCY ACROSS RUNS
# =============================================================================

def consistency(runs: list[list[Finding]]) -> tuple[int, int]:
    """
    How many alerts appear in EVERY run, out of all alerts seen in any run.

    An alert is a (report, test) pair, the same unit evaluate_changes() counts.
    The kind is ignored: if run 1 calls a jump "sudden_change" and run 2 calls it
    "out_of_range", the patient still sees an alert on that result.

    Args:
        runs: The findings from each run, e.g. [run1_findings, run2_findings, run3_findings].

    Returns:
        (alerts in every run, alerts in any run). The rules always give (n, n).
    """
    seen: dict[tuple[str, str], int] = defaultdict(int)   # alert -> number of runs it appeared in
    for findings in runs:
        for key in {(f.doc_id, f.test_code) for f in findings}:   # a set: count once per run
            seen[key] += 1
    return sum(1 for n in seen.values() if n == len(runs)), len(seen)