# Prescription evaluation (gpt-4o-mini)

Medicines read from each prescription by the LLM, and the medication timeline built from
them in code, compared with the synthetic data's answer key.

| Check | Accuracy |
|---|---|
| Issue date | 100.0% (11/11) |
| Medicines found | 100.0% (21/21) |
| Strength | 100.0% (21/21) |
| Directions | 100.0% (21/21) |
| Medication courses rebuilt (start and end dates) | 100.0% (12/12) |

Medicines extracted that are not on the prescription: **0**

## Mistakes

None. Every checked field matched the answer key.
