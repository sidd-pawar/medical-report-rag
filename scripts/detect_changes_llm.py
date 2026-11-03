"""
detect_changes_llm.py - asks the LLM to find important changes for every patient, scores
it exactly like the rules, and writes a side-by-side comparison.

Variants (each run --runs times, to measure consistency):
    results           the same data as the rules: results + medicine changes,
                      in one table sorted by date (all tests mixed together)
    notes             the same, plus the doctor's clinic notes
    results_by_test   identical data, but grouped into one block per test
    notes_by_test     the same, plus the clinic notes

Run from the project folder, after detect_changes.py:
    python scripts/detect_changes_llm.py --runs 1      # try it: 3 calls per variant, under 1 cent each
    python scripts/detect_changes_llm.py               # full: 3 runs (runs 1 come from the cache)

Every answer is cached in data/llm_cache/changes/, so re-running costs nothing. Writes:
    eval/change_detection_llm_<variant>.md  full report for each variant
    eval/change_detection_comparison.md    rules vs LLM, one table
"""

import argparse
import csv
import json
import time
from collections import Counter

from medrag.config import CHAT_MODEL, DATA_DIR, PROJECT_ROOT
from medrag.evaluation import changes_to_markdown, evaluate_changes
from medrag.llm_changes import (MAIN_KINDS, build_patient_input, check_numbers, consistency,
                                detect_changes_llm)
from medrag.parsing import load_documents
from medrag.prescriptions import build_timeline, extract_prescription
from medrag.trends import build_histories, detect_changes

RESULTS_CSV = DATA_DIR / "processed" / "extracted_results.csv"
EVENTS_CSV = DATA_DIR / "synthetic" / "ground_truth" / "events.csv"
RX_CACHE = DATA_DIR / "llm_cache" / "prescriptions"
CHANGES_CACHE = DATA_DIR / "llm_cache" / "changes"
EVAL_DIR = PROJECT_ROOT / "eval"

# gpt-4o-mini prices in US dollars per million tokens (check openai.com/api/pricing
# if you change model). Only used to report cost.
PRICE_IN, PRICE_OUT = 0.15, 0.60


def read_csv(path):
    """Read a CSV file into a list of dicts, one per row."""
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# argparse reads options from the command line, e.g. --runs 1
parser = argparse.ArgumentParser(description="LLM change detection experiment")
parser.add_argument("--runs", type=int, default=3, help="how many times to run each variant")
args = parser.parse_args()

# ---- 1. Load the same inputs the rules used ----------------------------------

if not RESULTS_CSV.exists():
    raise SystemExit("No extracted results yet. Run: python scripts/extract_results.py")
results = read_csv(RESULTS_CSV)
events = read_csv(EVENTS_CSV)
histories = build_histories(results)

documents = load_documents(DATA_DIR / "synthetic" / "patients")
prescriptions = [d for d in documents if d.doc_type == "prescription"]
notes = [d for d in documents if d.doc_type == "clinic_note"]
_, medication_changes = build_timeline(
    [(d.patient_id, d.doc_id, extract_prescription(d, RX_CACHE)) for d in prescriptions])
patients = sorted({r["patient_id"] for r in results})

# The rules, for the comparison table (instant, no API)
rule_findings = detect_changes(results, medication_changes)
rule_report = evaluate_changes(events, rule_findings, histories)

# ---- 2. Run each LLM variant ----------------------------------------------------

# name -> (column heading for the comparison table, clinic notes to include, layout)
# The name is also the cache folder, so the first two reuse the answers you already paid for.
variants = {
    "results": ("LLM, by date", None, "by_date"),
    "notes": ("LLM, by date + notes", notes, "by_date"),
    "results_by_test": ("LLM, by test", None, "by_test"),
    "notes_by_test": ("LLM, by test + notes", notes, "by_test"),
}
summary = {}                                      # name -> numbers for the comparison table

for name, (heading, variant_notes, layout) in variants.items():
    cache_dir = CHANGES_CACHE / f"{CHAT_MODEL}_{name}"
    print(f"\n=== LLM, {name} ({CHAT_MODEL}, {args.runs} run(s)) ===")

    runs = []                                     # one list of findings per run
    seconds = 0.0
    for run in range(1, args.runs + 1):
        findings = []
        for pid in patients:
            text = build_patient_input(pid, results, medication_changes, variant_notes, layout)
            start = time.perf_counter()
            findings += detect_changes_llm(pid, text, cache_dir, run=run)
            seconds += time.perf_counter() - start      # near 0 when the answer is cached
        runs.append(findings)
        main = [f for f in findings if f.rule in MAIN_KINDS]
        r = evaluate_changes(events, main, histories)
        print(f"  run {run}: caught {r.caught_exact.correct}/{r.caught_exact.total}, "
              f"{r.alerts} alerts, {len(findings) - len(main)} worth_noting")

    # Score run 1 in full (the others are summarised by the consistency measure)
    first = runs[0]
    main = [f for f in first if f.rule in MAIN_KINDS]
    worth_noting = [f for f in first if f.rule not in MAIN_KINDS]
    report = evaluate_changes(events, main, histories)

    # Check every number the LLM quoted, in every run
    all_findings = [f for findings in runs for f in findings]
    problems = check_numbers(all_findings, results)
    same, total = consistency([[f for f in findings if f.rule in MAIN_KINDS] for findings in runs])

    # Cost: add up the token usage saved in this variant's cache files
    tokens_in = tokens_out = 0
    for path in cache_dir.glob("*-run*.json"):
        if int(path.stem.rsplit("run", 1)[1]) <= args.runs:     # "P001-run2" -> 2
            usage = json.loads(path.read_text(encoding="utf-8"))["usage"]
            tokens_in += usage["input_tokens"]
            tokens_out += usage["output_tokens"]
    cost = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1_000_000

    print(f"  numbers wrong or invented: {len(problems)} of {len(all_findings)} findings (all runs)")
    print(f"  consistency: {same}/{total} alerts in every run")
    print(f"  tokens: {tokens_in:,} in, {tokens_out:,} out (about ${cost:.3f})")

    # Full report for this variant
    md = changes_to_markdown(report, f"Change detection: LLM ({CHAT_MODEL}, {name}), run 1",
                             Counter(f.rule for f in main))
    md += "\n## Numbers checked against the data (all runs)\n\n"
    if problems:
        md += "| Patient | Report | Test | Kind | Problem | LLM said | Actual |\n|---|---|---|---|---|---|---|\n"
        md += "".join(f"| {p['patient_id']} | {p['doc_id']} | {p['test_code']} | {p['kind']} | "
                      f"{p['problem']} | {p['quoted']} | {p['actual']} |\n" for p in problems)
    else:
        md += "Every value the LLM quoted matches the data.\n"
    md += f"\n## Consistency\n\n{same} of {total} alerts appeared in all {args.runs} run(s).\n"
    md += "\n## Worth noting (run 1, for a human to judge)\n\n"
    md += "".join(f"- {f.patient_id} {f.date} {f.test_code}: {f.detail}\n" for f in worth_noting) or "None.\n"
    md += "\n## Every finding (run 1)\n\n| Patient | Date | Test | Kind | LLM's explanation |\n|---|---|---|---|---|\n"
    md += "".join(f"| {f.patient_id} | {f.date} | {f.test_code} | {f.rule} | {f.detail} |\n" for f in first)
    (EVAL_DIR / f"change_detection_llm_{name}.md").write_text(md, encoding="utf-8")

    summary[name] = {"report": report, "problems": len(problems), "checked": len(all_findings),
                     "consistency": f"{same}/{total}", "worth_noting": len(worth_noting),
                     "cost": f"${cost:.3f}", "seconds": seconds}

# ---- 3. The comparison table ----------------------------------------------------

def row(label, rules, *llm):
    """One Markdown table row: measure | rules | each LLM variant."""
    return f"| {label} | {rules} | " + " | ".join(str(x) for x in llm) + " |"


# Small helpers that format a ChangeReport's numbers for the table
s = [summary[n] for n in variants]
caught = lambda r: f"{r.caught_exact.correct}/{r.caught_exact.total}"
near = lambda r: f"{r.caught_near.correct}/{r.caught_near.total}"
per_report = lambda r: f"{r.alerts} ({r.alerts / r.reports:.1f} per report)"

lines = [
    "# Change detection: rules vs LLM", "",
    f"Scored against the {rule_report.caught_exact.total} changes built into the synthetic stories. "
    f"LLM: {CHAT_MODEL}, temperature 0, {args.runs} run(s) per variant; scores are from run 1.", "",
    # Header row built from the variant headings, so adding a variant adds a column
    "| Measure | Rules (code) | " + " | ".join(h for h, _, _ in variants.values()) + " |",
    "|---|---|" + "---|" * len(variants),
    row("Built-in changes caught (same report)", caught(rule_report), *(caught(x["report"]) for x in s)),
    row("Caught within one report", near(rule_report), *(near(x["report"]) for x in s)),
    row("Alerts raised", per_report(rule_report), *(per_report(x["report"]) for x in s)),
    row("Other alerts (need a human look)", len(rule_report.other_alerts),
        *(len(x["report"].other_alerts) for x in s)),
    row("Extra 'worth noting' observations", "not possible", *(x["worth_noting"] for x in s)),
    row("Wrong or invented numbers", "0 (by construction)",
        *(f"{x['problems']} of {x['checked']} findings" for x in s)),
    row("Same alerts every run", "always", *(x["consistency"] for x in s)),
    row("Cost", "$0", *(x["cost"] for x in s)),
    "",
    "Details: `change_detection_rules.md` and `change_detection_llm_<variant>.md`.",
]
(EVAL_DIR / "change_detection_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n" + "\n".join(lines[4:14]))      # print just the table
print(f"\nReports saved in {EVAL_DIR}")