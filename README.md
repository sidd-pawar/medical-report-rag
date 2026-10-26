# Medical Report RAG

**An LLM + RAG assistant that helps people with chronic conditions understand years of pathology reports, prescriptions and doctor's notes.**

Patients managing conditions like diabetes or thyroid disease collect dozens of reports from different labs. This project turns that pile of PDFs into something searchable, trackable and easy to discuss with a doctor, and measures how accurately the AI does it.

> **Not a diagnostic tool.** It explains what reports contain and highlights changes; it never diagnoses or gives medical advice.
> **All data is synthetic.** Every patient, doctor, lab and value is fictional.

---

## Results so far

### LLM extraction: PDF lab report → structured results

`gpt-4o-mini` read all 32 synthetic lab reports from two labs with different layouts, test names and units, and was scored field by field against a known answer key.

| Check | Accuracy |
|---|---|
| Results found | **100%** (217 / 217) |
| Value, unit and reference range | **100%** |
| Mapped to a standard test code (e.g. "Estimated GFR" → eGFR) | **100%** |
| Converted to standard units (e.g. HbA1c 54 mmol/mol → 7.1%) | **100%** |
| High/low flag, as read by the LLM | 99.5% (216 / 217) |
| High/low flag, calculated in code (what users see) | **100%** |
| Results invented that aren't on the report | **0** |

Cost for all 32 reports: about **1 US cent**. Full report, including every mistake: [`eval/extraction_report.md`](eval/extraction_report.md).

These scores are on clean, computer-generated PDFs. Scanned or photographed reports would be harder, and testing on those is planned.

### What the one mistake taught us

The LLM marked a fasting glucose of **5.4** (normal range 3.0 – 5.4) as **low**. The value sits exactly on the limit, and on that lab's layout an empty flag cell disappears from the extracted text, so the model guessed. Deciding high/low is a calculation, so it moved into code ([`range_flag()`](src/medrag/extraction.py)), and the exact case is now a regression test.

That became the project's main design principle:

> **The LLM reads, maps and explains. Python calculates.**

---

## How it works

```
PDF reports ──► text (pypdf) ──► LLM structured extraction ──► results table ──► trends & flags
                                   (schema-validated JSON)       (standard units)     (rules in code)
                     │
                     └──────────► chunks + embeddings ──► RAG: answers with citations   (planned)
```

| Design decision | Why |
|---|---|
| **Structured outputs** with a Pydantic schema | The model must return JSON of a fixed shape; test codes are restricted to a fixed list, so it can't invent one |
| **Unit conversion and flags in code** | LLMs are unreliable at arithmetic and boundary judgements; code is exact and testable |
| **Every LLM answer cached** in [`data/llm_cache/`](data/llm_cache/) | Each report is sent to the API once. Anyone can reproduce the scores **without an API key** |
| **Fake LLMs in tests** | The test suite runs free and offline, including the real failure case |
| **Synthetic data with an answer key** | Real medical records can't be shared, and an answer key makes the AI measurable |

---

## Synthetic dataset

Three fictional patients, each with a scripted multi-year story built on standard clinical practice, so the data is **clinically plausible** (it is not clinically validated):

| Patient | Conditions | Built-in story |
|---|---|---|
| P001 | Type 2 diabetes, early kidney disease | HbA1c improves, rises again, improves after a second medicine. Sudden kidney result drop after gastroenteritis. Changes labs, so HbA1c switches from % to mmol/mol |
| P002 | High blood pressure, high cholesterol | Statin dose increase raises liver and muscle enzymes; switching statin brings them back to normal |
| P003 | Underactive thyroid | TSH normalises over dose increases, then jumps a year later when a calcium supplement interferes with absorption |

**55 documents**: 32 lab reports, 11 prescriptions and 12 clinic notes. Two fictional labs print the same tests with different layouts, names and units, as real labs do.

The answer key in [`data/synthetic/ground_truth/`](data/synthetic/ground_truth/) lists every printed value, every medicine change, and 15 deliberately built-in changes for anomaly detection to find.

Automated tests enforce **medical consistency**: every medicine and lab test must belong to one of the patient's conditions, and every value must be physically possible.

---

## Run it yourself

Requires Python 3.10+.

```bash
git clone https://github.com/sidd-pawar/medical-report-rag.git
cd medical-report-rag
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

python scripts/generate_data.py        # rebuild the synthetic PDFs and answer key
python scripts/extract_results.py      # uses the committed cache: no API key needed
python scripts/evaluate_extraction.py  # prints the accuracy table
pytest                                 # 40 tests
```

To extract with your own OpenAI key instead of the cache, copy `.env.example` to `.env`, add your key, and delete `data/llm_cache/extraction/`.

---

## Project structure

```
src/medrag/
  config.py           settings; reads the API key from .env
  parsing.py          PDF → text, keeping page numbers for citations
  extraction.py       LLM structured extraction, caching, unit conversion, flags
  evaluation.py       scores extraction against the answer key
  synthetic/          the synthetic data generator (patients, labs, PDF layouts)
scripts/              runnable steps: generate, extract, evaluate
tests/                pytest suite (no API calls)
data/synthetic/       generated PDFs and answer key
data/llm_cache/       saved LLM answers (makes results reproducible)
eval/                 evaluation reports
```

---

## Roadmap

- [x] Synthetic patients, reports, prescriptions and clinic notes with an answer key
- [x] PDF parsing with page tracking
- [x] LLM extraction with evaluation
- [ ] Trends and change detection, evaluated against the built-in events
- [ ] RAG over reports and clinic notes, with cited answers and retrieval evaluation
- [ ] Plain-language explanations and a one-page summary for doctor visits
- [ ] Web app (FastAPI + HTML/CSS/JS), mobile-friendly
- [ ] Robustness testing on scanned / noisy PDFs

---

## Author

**Siddhesh Pawar** · Master of Data Science, Monash University
[GitHub](https://github.com/sidd-pawar) · siddhesh.pawar.1397@gmail.com

## License

MIT