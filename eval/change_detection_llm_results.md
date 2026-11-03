# Change detection: LLM (gpt-4o-mini, results), run 1

Scored against the 15 changes built into the synthetic patients' stories (`data/synthetic/ground_truth/events.csv`).

| Measure | Result |
|---|---|
| Built-in changes caught (same report) | 40% (6/15) |
| Built-in changes caught (within one report) | 67% (10/15) |
| Alerts raised (report + test pairs) | 21 across 32 reports (0.7 per report) |
| Alerts on the same report as a built-in change, on a related test | 9 |
| Other alerts (need a human look) | 12 |

Findings by type: after_medicine 1, out_of_range 10, sudden_change 4, trend_reversal 6

## Missed

- P001 2024-07-01 K: One-off high potassium (about 5.8 mmol/L); back in range at the next test.
- P001 2025-07-07 HBA1C: HbA1c rose again from about 7.0% to 8.4% between months 15 and 24.
- P001 2025-12-29 HBA1C: HbA1c back to about 7.0% after empagliflozin was added.
- P001 2025-07-07 LDL: LDL fell from about 3.3 to 2.0 mmol/L after atorvastatin was started.
- P003 2024-02-12 TSH: TSH high (about 9.8 mIU/L) and Free T4 low before treatment.

## Other alerts

Not linked to a built-in change. The story only lists the headline changes, so many of
these are real (for example a high result on the first test), and some are noise.

| Report | Test | Found by |
|---|---|---|
| P001-LAB-2023-06-30 | GLU_F | out_of_range |
| P001-LAB-2023-10-06 | HBA1C | sudden_change |
| P001-LAB-2024-01-02 | HBA1C | trend_reversal |
| P001-LAB-2025-09-29 | EGFR | trend_reversal |
| P002-LAB-2023-10-08 | CHOL | out_of_range |
| P002-LAB-2024-08-09 | LDL | after_medicine |
| P002-LAB-2026-01-08 | GLU_F | out_of_range |
| P003-LAB-2024-02-12 | CHOL | out_of_range |
| P003-LAB-2024-04-10 | FT4 | sudden_change |
| P003-LAB-2024-06-14 | TSH | trend_reversal |
| P003-LAB-2025-03-11 | LDL | out_of_range |
| P003-LAB-2026-02-14 | TSH | trend_reversal |

## Numbers checked against the data (all runs)

| Patient | Report | Test | Kind | Problem | LLM said | Actual |
|---|---|---|---|---|---|---|
| P002 | P002-LAB-2025-02-04 | CK | sudden_change | wrong_previous | 121.0 | 111, 193 |

## Consistency

13 of 27 alerts appeared in all 3 run(s).

## Worth noting (run 1, for a human to judge)

- P001 2025-07-07 CHOL: Total Cholesterol decreased from 5.6 mmol/L to 4.2 mmol/L.
- P003 2025-03-11 FT4: Free T4 has remained stable around 16 pmol/L.

## Every finding (run 1)

| Patient | Date | Test | Kind | LLM's explanation |
|---|---|---|---|---|
| P001 | 2023-06-30 | GLU_F | out_of_range | Fasting Glucose is newly high at 10.1 mmol/L. |
| P001 | 2023-10-06 | HBA1C | sudden_change | HbA1c decreased from 8.9% to 8.4%. |
| P001 | 2024-01-02 | HBA1C | trend_reversal | HbA1c has improved from 8.4% to 7.6%. |
| P001 | 2025-01-02 | EGFR | out_of_range | eGFR is newly low at 51 mL/min/1.73m². |
| P001 | 2025-07-07 | CHOL | worth_noting | Total Cholesterol decreased from 5.6 mmol/L to 4.2 mmol/L. |
| P001 | 2025-09-29 | EGFR | trend_reversal | eGFR has worsened from 64 mL/min/1.73m² to 58 mL/min/1.73m². |
| P002 | 2023-10-08 | CHOL | out_of_range | Total Cholesterol is newly high at 6.7 mmol/L. |
| P002 | 2024-01-07 | LDL | sudden_change | LDL Cholesterol decreased significantly from 4.6 to 3.2 mmol/L. |
| P002 | 2024-08-09 | LDL | after_medicine | LDL Cholesterol decreased after the dose change of Atorvastatin. |
| P002 | 2025-02-04 | ALT | out_of_range | ALT is newly high at 71 U/L. |
| P002 | 2025-02-04 | AST | out_of_range | AST is newly high at 51 U/L. |
| P002 | 2025-02-04 | CK | out_of_range | Creatine Kinase is newly high at 241 U/L. |
| P002 | 2026-01-08 | GLU_F | out_of_range | Fasting Glucose is newly high at 5.6 mmol/L. |
| P002 | 2024-11-05 | ALT | trend_reversal | ALT has reversed trend, increasing from 26 to 57 U/L. |
| P002 | 2024-11-05 | AST | trend_reversal | AST has reversed trend, increasing from 24 to 43 U/L. |
| P003 | 2024-02-12 | CHOL | out_of_range | Total Cholesterol is newly high at 6.1 mmol/L. |
| P003 | 2024-02-12 | FT4 | out_of_range | Free T4 is newly low at 9.0 pmol/L. |
| P003 | 2024-04-10 | FT4 | sudden_change | Free T4 increased significantly from 9.0 pmol/L to 11.2 pmol/L. |
| P003 | 2024-06-14 | TSH | trend_reversal | TSH decreased from 6.31 mIU/L to 4.64 mIU/L after previously worsening. |
| P003 | 2025-03-11 | LDL | out_of_range | LDL Cholesterol is newly high at 3.1 mmol/L. |
| P003 | 2025-06-13 | TSH | sudden_change | TSH increased significantly from 2.10 mIU/L to 7.72 mIU/L. |
| P003 | 2026-02-14 | TSH | trend_reversal | TSH decreased from 7.72 mIU/L to 1.82 mIU/L after previously worsening. |
| P003 | 2025-03-11 | FT4 | worth_noting | Free T4 has remained stable around 16 pmol/L. |
