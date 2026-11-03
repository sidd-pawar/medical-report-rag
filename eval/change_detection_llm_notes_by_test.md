# Change detection: LLM (gpt-4o-mini, notes_by_test), run 1

Scored against the 15 changes built into the synthetic patients' stories (`data/synthetic/ground_truth/events.csv`).

| Measure | Result |
|---|---|
| Built-in changes caught (same report) | 40% (6/15) |
| Built-in changes caught (within one report) | 53% (8/15) |
| Alerts raised (report + test pairs) | 12 across 32 reports (0.4 per report) |
| Alerts on the same report as a built-in change, on a related test | 7 |
| Other alerts (need a human look) | 5 |

Findings by type: after_medicine 3, out_of_range 3, sudden_change 3, trend_reversal 3

## Missed

- P001 2024-04-06 HBA1C: HbA1c fell from 8.9% to about 7.1% after metformin was started and increased.
- P001 2025-01-02 EGFR: Sudden eGFR drop to about 51 (below range) after gastroenteritis; partly recovered by month 21.
- P001 2025-07-07 HBA1C: HbA1c rose again from about 7.0% to 8.4% between months 15 and 24.
- P001 2025-07-07 LDL: LDL fell from about 3.3 to 2.0 mmol/L after atorvastatin was started.
- P002 2024-01-07 LDL: LDL fell from 4.6 to about 3.2 mmol/L after atorvastatin 20 mg was started.
- P003 2024-02-12 TSH: TSH high (about 9.8 mIU/L) and Free T4 low before treatment.
- P003 2024-09-15 TSH: TSH back in range (about 2.4) after dose increases to 100 microgram.

## Other alerts

Not linked to a built-in change. The story only lists the headline changes, so many of
these are real (for example a high result on the first test), and some are noise.

| Report | Test | Found by |
|---|---|---|
| P001-LAB-2024-07-01 | CHOL | out_of_range |
| P001-LAB-2026-04-01 | HBA1C | trend_reversal |
| P002-LAB-2026-01-08 | EGFR | trend_reversal |
| P003-LAB-2024-02-12 | CHOL | out_of_range |
| P003-LAB-2025-03-11 | TSH | sudden_change |

## Numbers checked against the data (all runs)

Every value the LLM quoted matches the data.

## Consistency

8 of 17 alerts appeared in all 3 run(s).

## Worth noting (run 1, for a human to judge)

- P001 2025-12-29 UACR: Urine albumin/creatinine ratio has decreased significantly.
- P002 2025-05-12 LDL: LDL cholesterol level is now at 2.1 mmol/L, which is below the previous level of 2.2 mmol/L.
- P003 2024-02-12 LDL: LDL cholesterol is above the normal range and should be monitored.

## Every finding (run 1)

| Patient | Date | Test | Kind | LLM's explanation |
|---|---|---|---|---|
| P001 | 2024-07-01 | CHOL | out_of_range | Total cholesterol is now above the normal range. |
| P001 | 2025-01-02 | CREAT | sudden_change | Creatinine has increased significantly. |
| P001 | 2024-07-01 | K | after_medicine | Potassium increased after starting perindopril. |
| P001 | 2026-04-01 | HBA1C | trend_reversal | HbA1c has improved after previously worsening. |
| P001 | 2025-12-29 | UACR | worth_noting | Urine albumin/creatinine ratio has decreased significantly. |
| P002 | 2024-11-05 | ALT | out_of_range | ALT level increased to 57 U/L, which is above the normal range. |
| P002 | 2025-02-04 | CK | sudden_change | CK level increased significantly from 193 U/L to 241 U/L. |
| P002 | 2025-02-04 | ALT | after_medicine | ALT level increased after atorvastatin was stopped. |
| P002 | 2026-01-08 | EGFR | trend_reversal | eGFR level decreased from 82 mL/min/1.73m² to 79 mL/min/1.73m² after previously improving. |
| P002 | 2025-05-12 | LDL | worth_noting | LDL cholesterol level is now at 2.1 mmol/L, which is below the previous level of 2.2 mmol/L. |
| P003 | 2024-02-12 | CHOL | out_of_range | Total cholesterol is newly above the normal range. |
| P003 | 2025-03-11 | TSH | sudden_change | TSH decreased significantly from the previous result. |
| P003 | 2025-06-13 | TSH | after_medicine | TSH increased after the dose change of levothyroxine. |
| P003 | 2025-09-09 | TSH | trend_reversal | TSH has improved and returned to within the normal range after previously being high. |
| P003 | 2024-02-12 | LDL | worth_noting | LDL cholesterol is above the normal range and should be monitored. |
