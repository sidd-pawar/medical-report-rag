# Change detection: rules in code

Scored against the 15 changes built into the synthetic patients' stories (`data/synthetic/ground_truth/events.csv`).

| Measure | Result |
|---|---|
| Built-in changes caught (same report) | 100% (15/15) |
| Built-in changes caught (within one report) | 100% (15/15) |
| Alerts raised (report + test pairs) | 62 across 32 reports (1.9 per report) |
| Alerts on the same report as a built-in change, on a related test | 28 |
| Other alerts (need a human look) | 34 |

Findings by type: after_medicine 29, out_of_range 23, sudden_change 31, trend_reversal 10

## Missed

None.

## Other alerts

Not linked to a built-in change. The story only lists the headline changes, so many of
these are real (for example a high result on the first test), and some are noise.

| Report | Test | Found by |
|---|---|---|
| P001-LAB-2023-06-30 | GLU_F | out_of_range |
| P001-LAB-2023-06-30 | HBA1C | out_of_range |
| P001-LAB-2023-06-30 | LDL | out_of_range |
| P001-LAB-2023-06-30 | TRIG | out_of_range |
| P001-LAB-2023-06-30 | UACR | out_of_range |
| P001-LAB-2024-01-02 | GLU_F | after_medicine |
| P001-LAB-2024-01-02 | HBA1C | after_medicine |
| P001-LAB-2024-07-01 | CHOL | out_of_range |
| P001-LAB-2025-04-03 | CREAT | sudden_change |
| P001-LAB-2025-04-03 | EGFR | sudden_change |
| P001-LAB-2025-04-03 | GLU_F | trend_reversal |
| P001-LAB-2025-07-07 | CREAT | out_of_range |
| P001-LAB-2025-09-29 | EGFR | out_of_range |
| P001-LAB-2025-09-29 | HBA1C | after_medicine |
| P001-LAB-2025-12-29 | UACR | sudden_change |
| P002-LAB-2023-10-08 | CHOL | out_of_range |
| P002-LAB-2023-10-08 | LDL | out_of_range |
| P002-LAB-2023-10-08 | TRIG | out_of_range |
| P002-LAB-2024-04-10 | ALT | after_medicine |
| P002-LAB-2024-11-05 | CHOL | after_medicine |
| P002-LAB-2024-11-05 | LDL | after_medicine, sudden_change |
| P002-LAB-2025-09-08 | ALT | trend_reversal |
| P002-LAB-2025-09-08 | AST | trend_reversal |
| P002-LAB-2026-01-08 | GLU_F | out_of_range |
| P003-LAB-2024-02-12 | CHOL | out_of_range |
| P003-LAB-2024-02-12 | LDL | out_of_range |
| P003-LAB-2024-04-10 | FT4 | after_medicine, sudden_change |
| P003-LAB-2024-04-10 | TSH | after_medicine, sudden_change |
| P003-LAB-2024-06-14 | FT4 | after_medicine |
| P003-LAB-2024-06-14 | TSH | after_medicine, sudden_change |
| P003-LAB-2025-03-11 | LDL | sudden_change |
| P003-LAB-2025-03-11 | TRIG | sudden_change |
| P003-LAB-2025-11-10 | FT4 | trend_reversal |
| P003-LAB-2025-11-10 | TSH | sudden_change, trend_reversal |
