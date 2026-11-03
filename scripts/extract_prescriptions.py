"""
extract_prescriptions.py - reads every prescription with the LLM, builds each patient's
medication timeline in code, and scores both against the answer key.

Run from the project folder:
    python scripts/extract_prescriptions.py            # all prescriptions
    python scripts/extract_prescriptions.py --limit 1  # just the first one (a cheap test run)

Writes:
    data/llm_cache/prescriptions/          one saved LLM answer per prescription (committed)
    data/processed/medication_courses.csv  each medicine, with start and end dates
    data/processed/medication_changes.csv  every change: started / stopped / dose_changed
    eval/prescription_report.md            accuracy report (only when all are processed)
"""

import argparse
import csv
import json
from dataclasses import asdict

from medrag.config import CHAT_MODEL, DATA_DIR, PROJECT_ROOT
from medrag.evaluation import evaluate_prescriptions, prescriptions_to_markdown
from medrag.parsing import load_documents
from medrag.prescriptions import build_timeline, extract_prescription

PATIENTS_DIR = DATA_DIR / "synthetic" / "patients"
TRUTH_CSV = DATA_DIR / "synthetic" / "ground_truth" / "medications.csv"
CACHE_DIR = DATA_DIR / "llm_cache" / "prescriptions"
OUT_DIR = DATA_DIR / "processed"
REPORT_MD = PROJECT_ROOT / "eval" / "prescription_report.md"

parser = argparse.ArgumentParser(description="Extract medicines from every prescription.")
parser.add_argument("--limit", type=int, default=None, help="Only process this many prescriptions.")
args = parser.parse_args()

docs = [d for d in load_documents(PATIENTS_DIR) if d.doc_type == "prescription"]
if args.limit:
    docs = docs[: args.limit]

# 1. LLM reads each prescription (or the cache does)
print(f"Extracting {len(docs)} prescriptions with {CHAT_MODEL}")
extracted = []
for i, doc in enumerate(docs, start=1):
    was_cached = (CACHE_DIR / f"{doc.doc_id}.json").exists()
    rx = extract_prescription(doc, CACHE_DIR)
    extracted.append((doc.patient_id, doc.doc_id, doc.date, rx))
    names = ", ".join(f"{m.name} {m.strength}" for m in rx.medicines)
    print(f"  [{i:>2}/{len(docs)}] {doc.doc_id}: {names} ({'cache' if was_cached else 'OpenAI'})")

# 2. Code builds the timeline
courses, changes = build_timeline([(p, d, rx) for p, d, _, rx in extracted])

OUT_DIR.mkdir(parents=True, exist_ok=True)
for name, rows in [("medication_courses", courses), ("medication_changes", changes)]:
    with (OUT_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        dict_rows = [asdict(r) for r in rows]   # dataclass -> dict
        writer = csv.DictWriter(f, fieldnames=list(dict_rows[0].keys()))
        writer.writeheader()
        writer.writerows(dict_rows)

print("\nMedication changes found:")
for c in changes:
    print(f"  {c.patient_id}  {c.date}  {c.drug:<14} {c.change:<13} {c.detail}")

# 3. Score against the answer key (only meaningful when every prescription was processed)
if args.limit:
    print("\n(Skipping evaluation: run without --limit to score all prescriptions.)")
else:
    with TRUTH_CSV.open(encoding="utf-8") as f:
        truth = list(csv.DictReader(f))
    report = evaluate_prescriptions(truth, extracted, courses)
    print("\nAccuracy against the answer key:")
    for metric in ["date", "found", "strength", "directions", "course"]:
        s = report.scores[metric]
        print(f"  {metric:<12}{s.pct:6.1f}%   ({s.correct}/{s.total})")
    print(f"  Medicines not on the prescription: {report.not_on_report}")

    model = json.loads(next(CACHE_DIR.glob("*.json")).read_text(encoding="utf-8"))["model"]
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(prescriptions_to_markdown(report, model), encoding="utf-8")
    print(f"\nFull report saved to {REPORT_MD}")