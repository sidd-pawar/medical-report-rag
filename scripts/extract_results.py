"""
extract_results.py - runs LLM extraction on every lab report and saves a results table.

Run from the project folder:
    python scripts/extract_results.py            # all lab reports
    python scripts/extract_results.py --limit 1  # just the first one (a cheap test run)

What it does:
    1. Reads every lab report PDF in data/synthetic/patients.
    2. For each one, gets the structured results: from the cache if this report was done
       before, otherwise by calling OpenAI (and then saving the answer to the cache).
    3. Writes every result to data/processed/extracted_results.csv.

The cache lives in data/llm_cache/extraction/ and IS committed to GitHub, so anyone can
re-run the evaluation and get your exact scores without an API key or any cost.
"""

import argparse
import csv
import json

from medrag.config import CHAT_MODEL, DATA_DIR
from medrag.extraction import extract_report, to_rows
from medrag.parsing import load_documents

PATIENTS_DIR = DATA_DIR / "synthetic" / "patients"
CACHE_DIR = DATA_DIR / "llm_cache" / "extraction"
OUTPUT_CSV = DATA_DIR / "processed" / "extracted_results.csv"

# Command-line options. argparse reads things like "--limit 1" typed after the script name.
parser = argparse.ArgumentParser(description="Extract lab results from every lab report.")
parser.add_argument("--limit", type=int, default=None,
                    help="Only process this many reports (useful for a quick, cheap test).")
args = parser.parse_args()

# Only lab reports have test results to extract (not prescriptions or clinic notes)
reports = [d for d in load_documents(PATIENTS_DIR) if d.doc_type == "lab_report"]
if args.limit:
    reports = reports[: args.limit]

print(f"Extracting {len(reports)} lab reports with {CHAT_MODEL}")
all_rows = []
for i, doc in enumerate(reports, start=1):
    was_cached = (CACHE_DIR / f"{doc.doc_id}.json").exists()
    report = extract_report(doc, CACHE_DIR)
    rows = to_rows(doc, report)
    all_rows.extend(rows)
    source = "cache" if was_cached else "OpenAI"
    print(f"  [{i:>2}/{len(reports)}] {doc.doc_id}: {len(rows)} results ({source})")

# Save the table
OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
    writer.writeheader()
    writer.writerows(all_rows)

# Add up the tokens used (read from the cache files) and estimate the cost
tokens_in = tokens_out = 0
for doc in reports:
    usage = json.loads((CACHE_DIR / f"{doc.doc_id}.json").read_text(encoding="utf-8"))["usage"]
    tokens_in += usage["input_tokens"]
    tokens_out += usage["output_tokens"]

print(f"\nSaved {len(all_rows)} results to {OUTPUT_CSV}")
print(f"Tokens used across these reports: {tokens_in:,} in, {tokens_out:,} out")
print("(Cached reports cost nothing to re-run; these totals are from when they were first extracted.)")