# Change detection: LLM (gpt-4o-mini, notes), run 1

Scored against the 15 changes built into the synthetic patients' stories (`data/synthetic/ground_truth/events.csv`).

| Measure | Result |
|---|---|
| Built-in changes caught (same report) | 33% (5/15) |
| Built-in changes caught (within one report) | 53% (8/15) |
| Alerts raised (report + test pairs) | 16 across 32 reports (0.5 per report) |
| Alerts on the same report as a built-in change, on a related test | 8 |
| Other alerts (need a human look) | 8 |

Findings by type: after_medicine 3, out_of_range 6, sudden_change 3, trend_reversal 4

## Missed

- P001 2024-07-01 K: One-off high potassium (about 5.8 mmol/L); back in range at the next test.
- P001 2025-01-02 EGFR: Sudden eGFR drop to about 51 (below range) after gastroenteritis; partly recovered by month 21.
- P001 2025-07-07 HBA1C: HbA1c rose again from about 7.0% to 8.4% between months 15 and 24.
- P001 2025-12-29 HBA1C: HbA1c back to about 7.0% after empagliflozin was added.
- P001 2025-07-07 LDL: LDL fell from about 3.3 to 2.0 mmol/L after atorvastatin was started.
- P002 2024-01-07 LDL: LDL fell from 4.6 to about 3.2 mmol/L after atorvastatin 20 mg was started.
- P003 2024-09-15 TSH: TSH back in range (about 2.4) after dose increases to 100 microgram.

## Other alerts

Not linked to a built-in change. The story only lists the headline changes, so many of
these are real (for example a high result on the first test), and some are noise.

| Report | Test | Found by |
|---|---|---|
| P001-LAB-2023-06-30 | GLU_F | out_of_range |
| P001-LAB-2023-10-06 | HBA1C | after_medicine |
| P001-LAB-2024-01-02 | HBA1C | trend_reversal |
| P002-LAB-2023-10-08 | CHOL | out_of_range |
| P002-LAB-2024-08-09 | LDL | after_medicine |
| P002-LAB-2026-01-08 | GLU_F | out_of_range |
| P003-LAB-2024-04-10 | FT4 | sudden_change |
| P003-LAB-2025-03-11 | LDL | after_medicine |

## Numbers checked against the data (all runs)

| Patient | Report | Test | Kind | Problem | LLM said | Actual |
|---|---|---|---|---|---|---|
| P002 | P002-LAB-2025-02-04 | CK | after_medicine | wrong_previous | 121.0 | 111, 193 |

## Consistency

10 of 20 alerts appeared in all 3 run(s).

## Worth noting (run 1, for a human to judge)

- P001 2024-07-01 K: Potassium level is notably high at 5.8 mmol/L.
- P003 2025-06-13 FT4: FT4 decreased after a year of stable results.

## Every finding (run 1)

| Patient | Date | Test | Kind | LLM's explanation |
|---|---|---|---|---|
| P001 | 2023-06-30 | GLU_F | out_of_range | Fasting glucose is newly high at 10.1 mmol/L. |
| P001 | 2025-01-02 | CREAT | sudden_change | Creatinine increased significantly from 96 µmol/L to 139 µmol/L. |
| P001 | 2023-10-06 | HBA1C | after_medicine | HbA1c decreased after starting Metformin. |
| P001 | 2024-01-02 | HBA1C | trend_reversal | HbA1c improved from 8.4% to 7.6%, reversing the previous trend. |
| P001 | 2024-07-01 | K | worth_noting | Potassium level is notably high at 5.8 mmol/L. |
| P002 | 2023-10-08 | CHOL | out_of_range | Total cholesterol is newly high at 6.7 mmol/L. |
| P002 | 2025-02-04 | ALT | sudden_change | ALT increased significantly from 57 U/L to 71 U/L. |
| P002 | 2025-02-04 | CK | out_of_range | Creatine kinase is newly high at 241 U/L. |
| P002 | 2025-02-04 | AST | out_of_range | AST is newly high at 51 U/L. |
| P002 | 2024-08-09 | LDL | after_medicine | LDL cholesterol decreased after atorvastatin dose was increased. |
| P002 | 2026-01-08 | GLU_F | out_of_range | Fasting glucose is newly high at 5.6 mmol/L. |
| P002 | 2024-11-05 | ALT | trend_reversal | ALT has reversed trend, increasing from 26 U/L to 57 U/L. |
| P002 | 2025-05-12 | CK | trend_reversal | Creatine kinase has reversed trend, decreasing from 241 U/L to 121 U/L. |
| P003 | 2024-02-12 | TSH | out_of_range | TSH is newly above the normal range. |
| P003 | 2024-04-10 | FT4 | sudden_change | FT4 increased significantly since the previous result. |
| P003 | 2025-03-11 | LDL | after_medicine | LDL decreased after the dose change of Levothyroxine. |
| P003 | 2025-06-13 | TSH | trend_reversal | TSH has worsened after previously improving. |
| P003 | 2025-06-13 | FT4 | worth_noting | FT4 decreased after a year of stable results. |
