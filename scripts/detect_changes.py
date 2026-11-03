"""
detect_changes.py - finds important changes in every patient's results using the rules
in trends.py, and scores them against the changes built into the synthetic stories.

This is approach 1 of the experiment (rules in code). Approach 2 (LLM only) comes in
step 5c and is scored with exactly the same evaluate_changes() function.

Run from the project folder, after extract_results.py and extract_prescriptions.py:
    python scripts/detect_changes.py

Uses only cached LLM answers (no API calls, no cost). Writes:
    data/processed/findings.csv       every finding, with a plain-English explanation
    eval/change_detection_rules.md    the evaluation report (committed to GitHub)
"""

import csv
from collections import Counter          # counts things, e.g. how many findings per rule
from dataclasses import asdict           # turns a Finding into a dict, for writing to CSV

from medrag.config import DATA_DIR, PROJECT_ROOT
from medrag.evaluation import changes_to_markdown, evaluate_changes
from medrag.parsing import load_documents
from medrag.prescriptions import build_timeline, extract_prescription
from medrag.trends import build_histories, detect_changes

# Where everything is read from and written to
RESULTS_CSV = DATA_DIR / "processed" / "extracted_results.csv"           # from extract_results.py
EVENTS_CSV = DATA_DIR / "synthetic" / "ground_truth" / "events.csv"      # the answer key
RX_CACHE = DATA_DIR / "llm_cache" / "prescriptions"                      # saved LLM answers
FINDINGS_CSV = DATA_DIR / "processed" / "findings.csv"
REPORT_MD = PROJECT_ROOT / "eval" / "change_detection_rules.md"


def read_csv(path):
    """Read a CSV file into a list of dicts, one per row (all values are strings)."""
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---- 1. Load the inputs ------------------------------------------------------

if not RESULTS_CSV.exists():
    raise SystemExit("No extracted results yet. Run: python scripts/extract_results.py")

results = read_csv(RESULTS_CSV)

# Medication changes, rebuilt from the cached prescription answers.
# extract_prescription() finds each answer in the cache, so OpenAI is never called.
# build_timeline() returns (courses, changes); we only need the changes here, so the
# courses go into "_", Python's name for "a value we don't need".
prescriptions = [d for d in load_documents(DATA_DIR / "synthetic" / "patients")
                 if d.doc_type == "prescription"]
_, medication_changes = build_timeline(
    [(d.patient_id, d.doc_id, extract_prescription(d, RX_CACHE)) for d in prescriptions])

# ---- 2. Run the rules --------------------------------------------------------

findings = detect_changes(results, medication_changes)

# Save every finding (asdict turns each Finding into a dict whose keys become the columns)
FINDINGS_CSV.parent.mkdir(parents=True, exist_ok=True)
with FINDINGS_CSV.open("w", newline="", encoding="utf-8") as f:
    rows = [asdict(x) for x in findings]
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

# Show one patient's findings as an example of what the app will display
print("Example findings for P001:\n")
for x in findings:
    if x.patient_id == "P001":
        print(f"  {x.date}  {x.test_code:<6} {x.rule:<15} {x.detail}")

# ---- 3. Score against the built-in events ------------------------------------

report = evaluate_changes(read_csv(EVENTS_CSV), findings, build_histories(results))
print(f"\nBuilt-in changes caught: {report.caught_exact.correct}/{report.caught_exact.total} on the same report, "
      f"{report.caught_near.correct}/{report.caught_near.total} within one report")
print(f"Alerts raised: {report.alerts} across {report.reports} reports "
      f"({report.alerts / report.reports:.1f} per report)")
print(f"  on the same report as a built-in change, related test: {report.alerts_related}")
print(f"  other (need a human look): {len(report.other_alerts)}")

# Counter(...) counts findings per rule, e.g. {"sudden_change": 31, "out_of_range": 23, ...}
REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
REPORT_MD.write_text(changes_to_markdown(report, "Change detection: rules in code",
                                         Counter(x.rule for x in findings)), encoding="utf-8")
print(f"\nSaved {len(findings)} findings to {FINDINGS_CSV}")
print(f"Full report saved to {REPORT_MD}")