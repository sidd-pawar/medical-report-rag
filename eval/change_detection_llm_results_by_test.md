# Change detection: LLM (gpt-4o-mini, results_by_test), run 1

Scored against the 15 changes built into the synthetic patients' stories (`data/synthetic/ground_truth/events.csv`).

| Measure | Result |
|---|---|
| Built-in changes caught (same report) | 40% (6/15) |
| Built-in changes caught (within one report) | 53% (8/15) |
| Alerts raised (report + test pairs) | 19 across 32 reports (0.6 per report) |
| Alerts on the same report as a built-in change, on a related test | 10 |
| Other alerts (need a human look) | 9 |

Findings by type: after_medicine 2, out_of_range 8, sudden_change 3, trend_reversal 6

## Missed

- P001 2024-04-06 HBA1C: HbA1c fell from 8.9% to about 7.1% after metformin was started and increased.
- P001 2024-07-01 K: One-off high potassium (about 5.8 mmol/L); back in range at the next test.
- P001 2025-07-07 HBA1C: HbA1c rose again from about 7.0% to 8.4% between months 15 and 24.
- P001 2025-12-29 HBA1C: HbA1c back to about 7.0% after empagliflozin was added.
- P002 2024-01-07 LDL: LDL fell from 4.6 to about 3.2 mmol/L after atorvastatin 20 mg was started.
- P002 2025-05-12 ALT: ALT back in range (about 33 U/L) after switching to rosuvastatin; LDL stayed controlled.
- P003 2024-09-15 TSH: TSH back in range (about 2.4) after dose increases to 100 microgram.

## Other alerts

Not linked to a built-in change. The story only lists the headline changes, so many of
these are real (for example a high result on the first test), and some are noise.

| Report | Test | Found by |
|---|---|---|
| P001-LAB-2024-07-01 | CHOL | out_of_range |
| P001-LAB-2024-07-01 | GLU_F | trend_reversal |
| P001-LAB-2026-04-01 | TRIG | trend_reversal |
| P002-LAB-2025-02-04 | GLU_F | after_medicine |
| P002-LAB-2026-01-08 | EGFR | trend_reversal |
| P003-LAB-2024-02-12 | CHOL | out_of_range |
| P003-LAB-2024-02-12 | LDL | out_of_range |
| P003-LAB-2025-03-11 | CHOL | trend_reversal |
| P003-LAB-2025-03-11 | LDL | trend_reversal |

## Numbers checked against the data (all runs)

| Patient | Report | Test | Kind | Problem | LLM said | Actual |
|---|---|---|---|---|---|---|
| P001 | P001-LAB-2025-12-29 | HB | worth_noting | not_a_result | 135.0 |  |
| P002 | P002-LAB-2025-02-04 | GLU_F | after_medicine | not_a_result | 5.6 |  |
| P002 | P002-LAB-2025-02-04 | GLU_F | after_medicine | not_a_result | 5.6 |  |
| P002 | P002-LAB-2025-02-04 | GLU_F | after_medicine | not_a_result | 5.4 |  |

## Consistency

16 of 20 alerts appeared in all 3 run(s).

## Worth noting (run 1, for a human to judge)

- P001 2025-12-29 HB: Haemoglobin has decreased over time.
- P001 2025-12-29 UACR: Urine albumin/creatinine ratio has decreased.
- P002 2023-10-08 CHOL: Total cholesterol was high at the first test.
- P002 2023-10-08 LDL: LDL cholesterol was high at the first test.
- P002 2023-10-08 TRIG: Triglycerides were high at the first test.

## Every finding (run 1)

| Patient | Date | Test | Kind | LLM's explanation |
|---|---|---|---|---|
| P001 | 2024-07-01 | CHOL | out_of_range | Total cholesterol is now above the normal range. |
| P001 | 2025-01-02 | CREAT | sudden_change | Creatinine has increased significantly. |
| P001 | 2025-01-02 | EGFR | out_of_range | eGFR is now below the normal range. |
| P001 | 2024-07-01 | GLU_F | trend_reversal | Fasting glucose has improved after previously worsening. |
| P001 | 2025-12-29 | HB | worth_noting | Haemoglobin has decreased over time. |
| P001 | 2025-07-07 | LDL | sudden_change | LDL cholesterol has decreased significantly. |
| P001 | 2026-04-01 | TRIG | trend_reversal | Triglycerides have improved after previously worsening. |
| P001 | 2025-12-29 | UACR | worth_noting | Urine albumin/creatinine ratio has decreased. |
| P002 | 2024-11-05 | ALT | out_of_range | ALT is newly elevated above the normal range. |
| P002 | 2025-02-04 | CK | sudden_change | CK shows a significant increase. |
| P002 | 2025-02-04 | GLU_F | after_medicine | Fasting glucose increased after stopping Atorvastatin. |
| P002 | 2026-01-08 | EGFR | trend_reversal | eGFR has decreased after previously improving. |
| P002 | 2024-11-05 | AST | out_of_range | AST is newly elevated above the normal range. |
| P002 | 2023-10-08 | CHOL | worth_noting | Total cholesterol was high at the first test. |
| P002 | 2023-10-08 | LDL | worth_noting | LDL cholesterol was high at the first test. |
| P002 | 2023-10-08 | TRIG | worth_noting | Triglycerides were high at the first test. |
| P003 | 2024-02-12 | CHOL | out_of_range | Total cholesterol is newly high at 6.1 mmol/L. |
| P003 | 2025-03-11 | CHOL | trend_reversal | Total cholesterol has reversed trend, decreasing from 6.1 to 5.0 mmol/L. |
| P003 | 2024-02-12 | TSH | out_of_range | TSH is newly high at 9.68 mIU/L. |
| P003 | 2025-06-13 | TSH | after_medicine | TSH increased to 7.72 mIU/L after the dose change of Levothyroxine. |
| P003 | 2024-02-12 | LDL | out_of_range | LDL cholesterol is newly high at 4.0 mmol/L. |
| P003 | 2025-03-11 | LDL | trend_reversal | LDL cholesterol has reversed trend, decreasing from 4.0 to 3.1 mmol/L. |
| P003 | 2024-02-12 | FT4 | out_of_range | Free T4 is newly low at 9.0 pmol/L. |
| P003 | 2025-06-13 | FT4 | trend_reversal | Free T4 has reversed trend, decreasing from 16.1 to 10.9 pmol/L. |
