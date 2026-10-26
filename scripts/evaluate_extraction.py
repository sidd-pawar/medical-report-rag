"""
evaluate_extraction.py - scores the LLM extraction against the answer key.

Run from the project folder, after scripts/extract_results.py:
    python scripts/evaluate_extraction.py

It prints a summary and saves the full report (including every mistake) to
eval/extraction_report.md, which is committed to GitHub and linked from the README.
"""

import csv
import json

from medrag.config import DATA_DIR, PROJECT_ROOT
from medrag.evaluation import evaluate_extraction, to_markdown

TRUTH_CSV = DATA_DIR / "synthetic" / "ground_truth" / "lab_results.csv"
EXTRACTED_CSV = DATA_DIR / "processed" / "extracted_results.csv"
CACHE_DIR = DATA_DIR / "llm_cache" / "extraction"
REPORT_MD = PROJECT_ROOT / "eval" / "extraction_report.md"


def read_csv(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


if not EXTRACTED_CSV.exists():
    raise SystemExit("No extracted results yet. Run: python scripts/extract_results.py")

truth = read_csv(TRUTH_CSV)
extracted = read_csv(EXTRACTED_CSV)

# Which model produced the cached answers (read from any cache file)
model = json.loads(next(CACHE_DIR.glob("*.json")).read_text(encoding="utf-8"))["model"]

report = evaluate_extraction(truth, extracted)

# Print a short summary
print(f"Extraction accuracy ({model}, {len(truth)} results in the answer key)\n")
for metric in ["found", "date", "value", "unit", "range", "flag", "code", "standard_value"]:
    s = report.scores[metric]
    print(f"  {metric:<16}{s.pct:6.1f}%   ({s.correct}/{s.total})")
print(f"\n  Results not on the report: {report.not_on_report}")
print(f"  Total mistakes: {len(report.errors)}")

REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
REPORT_MD.write_text(to_markdown(report, model), encoding="utf-8")
print(f"\nFull report saved to {REPORT_MD}")