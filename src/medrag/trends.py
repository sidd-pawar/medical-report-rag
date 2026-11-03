"""
trends.py - finds important changes in a patient's results, using simple rules in code.

Input:   the results table from extraction (one row per test result) and the medication
         changes from prescriptions.
Output:  a list of Findings, e.g. "eGFR fell from 67 to 51 (-24%) since the last test".

Why rules and not an LLM? Spotting a change is arithmetic: comparing numbers and dates.
Rules give the same answer every time, never skip a result, and can say exactly why
something was flagged ("dropped more than 20%"). In healthcare that explainability
matters. The LLM's job comes later: explaining these findings in plain language.

The four rules (thresholds are constants below, so they're easy to see and tune):

    1. out_of_range      Outside the normal range, when the previous result wasn't
                         (or it's the first result we have for that test).
    2. sudden_change     Changed by SUDDEN_CHANGE_PCT or more since the previous result.
    3. after_medicine    Within MEDICINE_WINDOW_DAYS after a medicine started, stopped or
                         changed dose, a test that medicine affects moved by
                         MEDICINE_CHANGE_PCT or more from its last result before the change.
                         This says WHEN things happened together, never WHY.
    4. trend_reversal    Two moves in a row in the same direction, adding up to
                         TREND_MOVE_PCT or more, after an earlier move of at least that
                         size the opposite way (e.g. HbA1c improving for a year, then
                         rising twice).

All comparisons use values in standard units (value_standard), so a lab changing
HbA1c from % to mmol/mol doesn't look like a sudden change.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .synthetic.catalog import TESTS

# =============================================================================
# SETTINGS
# =============================================================================

SUDDEN_CHANGE_PCT = 20        # rule 2: % change vs the previous result
MEDICINE_CHANGE_PCT = 10      # rule 3: % change vs the result before a medicine change
MEDICINE_WINDOW_DAYS = 366    # rule 3: how long after a medicine change to look
TREND_MOVE_PCT = 10           # rule 4: minimum size of both the new and the earlier move

# Which tests each medicine is known to affect, either as its purpose or as something
# doctors monitor for side effects. Rule 3 only links a medicine to these tests.
MEDICINE_AFFECTS: dict[str, set[str]] = {
    "metformin": {"HBA1C", "GLU_F"},
    "empagliflozin": {"HBA1C", "GLU_F", "EGFR", "CREAT"},
    "perindopril": {"K", "CREAT", "EGFR"},
    "atorvastatin": {"LDL", "CHOL", "ALT", "AST", "CK"},
    "rosuvastatin": {"LDL", "CHOL", "ALT", "AST", "CK"},
    "levothyroxine": {"TSH", "FT4"},
    "amlodipine": set(),           # blood pressure; none of our lab tests
}


# =============================================================================
# DATA SHAPES
# =============================================================================

@dataclass(frozen=True)
class Point:
    """One result in a test's history."""
    date: str
    value: float          # in standard units
    flag: str             # "H", "L" or "" (calculated in code, not read by the LLM)
    doc_id: str


@dataclass
class Finding:
    """
    One change worth showing the patient.

    Fields:
        patient_id, test_code: Whose result and which test.
        doc_id, date:  The report where the change shows up (for citing it).
        rule:          Which rule found it: out_of_range, sudden_change, after_medicine,
                       trend_reversal.
        value:         The result on that report, in standard units.
        previous:      The value it's compared with (None for a first result).
        detail:        A short, factual sentence explaining the finding.
    """
    patient_id: str
    test_code: str
    doc_id: str
    date: str
    rule: str
    value: float
    previous: float | None
    detail: str


def _pct(new: float, old: float) -> float:
    """Percentage change from old to new, e.g. 67 -> 51 gives -23.9."""
    return 100 * (new - old) / old


def _fmt(code: str, value: float) -> str:
    """Format a value with its unit, e.g. ("EGFR", 51) -> "51 mL/min/1.73m²"."""
    t = TESTS[code]
    spacer = "" if t.unit == "%" else " "
    return f"{value:.{t.decimals}f}{spacer}{t.unit}"


def _days(a: str, b: str) -> int:
    """Days from date a to date b (both YYYY-MM-DD)."""
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


# =============================================================================
# BUILDING EACH TEST'S HISTORY
# =============================================================================

def build_histories(result_rows: list[dict]) -> dict[tuple[str, str], list[Point]]:
    """
    Group results into one time series per patient and test, oldest first.

    Args:
        result_rows: Rows of extracted_results.csv (strings), or dicts with the same keys.

    Returns:
        {(patient_id, test_code): [Point, Point, ...]}
        Results with no standard value (unknown test or unit) are skipped.
    """
    histories: dict[tuple[str, str], list[Point]] = defaultdict(list)
    for r in result_rows:
        if r["test_code"] == "UNKNOWN" or r["value_standard"] in ("", None, "None"):
            continue
        histories[(r["patient_id"], r["test_code"])].append(
            Point(r["collected_date"], float(r["value_standard"]), r["flag_computed"], r["doc_id"]))
    for points in histories.values():
        points.sort(key=lambda p: p.date)
    return dict(histories)


# =============================================================================
# THE RULES
# =============================================================================

def _out_of_range(pid, code, points) -> list[Finding]:
    """Rule 1: newly outside the normal range."""
    findings = []
    for i, p in enumerate(points):
        if not p.flag:
            continue
        before = points[i - 1] if i > 0 else None
        if before is None or before.flag != p.flag:     # first result, or it just crossed the limit
            word = "above" if p.flag == "H" else "below"
            when = "on the first test available" if before is None else \
                   f"after being {'in range' if not before.flag else 'on the other side'} last time"
            findings.append(Finding(pid, code, p.doc_id, p.date, "out_of_range", p.value,
                                    before.value if before else None,
                                    f"{TESTS[code].name} {_fmt(code, p.value)} is {word} the normal range {when}."))
    return findings


def _sudden_change(pid, code, points) -> list[Finding]:
    """Rule 2: a big jump since the previous result."""
    findings = []
    for before, p in zip(points, points[1:]):
        change = _pct(p.value, before.value)
        if abs(change) >= SUDDEN_CHANGE_PCT:
            word = "rose" if change > 0 else "fell"
            findings.append(Finding(pid, code, p.doc_id, p.date, "sudden_change", p.value, before.value,
                                    f"{TESTS[code].name} {word} from {_fmt(code, before.value)} to "
                                    f"{_fmt(code, p.value)} ({change:+.0f}%) since the previous test."))
    return findings


def _after_medicine(pid, code, points, medication_changes) -> list[Finding]:
    """Rule 3: a clear move in a related test after a medicine change."""
    findings = []
    for m in medication_changes:
        if m.patient_id != pid or code not in MEDICINE_AFFECTS.get(m.drug.lower(), set()):
            continue
        before = [p for p in points if p.date < m.date]
        after = [p for p in points if p.date >= m.date and _days(m.date, p.date) <= MEDICINE_WINDOW_DAYS]
        if not before:
            continue
        baseline = before[-1]
        for p in after:                                   # report the FIRST clear move only
            change = _pct(p.value, baseline.value)
            if abs(change) >= MEDICINE_CHANGE_PCT:
                word = "rose" if change > 0 else "fell"
                what = {"started": f"{m.drug} was started", "stopped": f"{m.drug} was stopped",
                        "dose_changed": f"the {m.drug} dose changed ({m.detail})"}[m.change]
                findings.append(Finding(pid, code, p.doc_id, p.date, "after_medicine", p.value, baseline.value,
                                        f"{TESTS[code].name} {word} from {_fmt(code, baseline.value)} to "
                                        f"{_fmt(code, p.value)} ({change:+.0f}%) after {what} on {m.date}."))
                break
    return findings


def _trend_reversal(pid, code, points) -> list[Finding]:
    """Rule 4: two moves in a row one way, after an earlier clear move the other way."""
    findings = []
    for i in range(2, len(points)):
        a, b, c = points[i - 2].value, points[i - 1].value, points[i].value
        if not ((c > b > a) or (c < b < a)):
            continue
        if abs(_pct(c, a)) < TREND_MOVE_PCT:              # ignore small wobbles
            continue
        rising = c > b
        earlier = [p.value for p in points[: i - 1]]      # everything up to and including point a
        # Was there an earlier clear move in the opposite direction, ending at a?
        if rising:
            peak = max(earlier)
            opposite = _pct(a, peak) <= -TREND_MOVE_PCT
        else:
            low = min(earlier)
            opposite = _pct(a, low) >= TREND_MOVE_PCT
        # Only report the start of a reversal, not every later step of it
        already = findings and findings[-1].doc_id == points[i - 1].doc_id
        if opposite and not already:
            word = "rising" if rising else "falling"
            findings.append(Finding(pid, code, points[i].doc_id, points[i].date, "trend_reversal", c, a,
                                    f"{TESTS[code].name} is {word} again: {_fmt(code, a)} -> {_fmt(code, b)} -> "
                                    f"{_fmt(code, c)}, after an earlier move the other way."))
    return findings


def detect_changes(result_rows: list[dict], medication_changes: list) -> list[Finding]:
    """
    Run all four rules over every patient's results.

    Args:
        result_rows:        Rows of extracted_results.csv.
        medication_changes: MedicationChange objects from prescriptions.build_timeline().

    Returns:
        Every Finding, sorted by patient, date and test.
    """
    findings: list[Finding] = []
    for (pid, code), points in build_histories(result_rows).items():
        findings += _out_of_range(pid, code, points)
        findings += _sudden_change(pid, code, points)
        findings += _after_medicine(pid, code, points, medication_changes)
        findings += _trend_reversal(pid, code, points)
    return sorted(findings, key=lambda f: (f.patient_id, f.date, f.test_code, f.rule))