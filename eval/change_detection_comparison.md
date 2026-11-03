# Change detection: rules vs LLM

Scored against the 15 changes built into the synthetic stories. LLM: gpt-4o-mini, temperature 0, 3 run(s) per variant; scores are from run 1.

| Measure | Rules (code) | LLM, by date | LLM, by date + notes | LLM, by test | LLM, by test + notes |
|---|---|---|---|---|---|
| Built-in changes caught (same report) | 15/15 | 6/15 | 5/15 | 6/15 | 6/15 |
| Caught within one report | 15/15 | 10/15 | 8/15 | 8/15 | 8/15 |
| Alerts raised | 62 (1.9 per report) | 21 (0.7 per report) | 16 (0.5 per report) | 19 (0.6 per report) | 12 (0.4 per report) |
| Other alerts (need a human look) | 34 | 12 | 8 | 9 | 5 |
| Extra 'worth noting' observations | not possible | 2 | 2 | 5 | 3 |
| Wrong or invented numbers | 0 (by construction) | 1 of 64 findings | 1 of 51 findings | 4 of 64 findings | 0 of 46 findings |
| Same alerts every run | always | 13/27 | 10/20 | 16/20 | 8/17 |
| Cost | $0 | $0.007 | $0.007 | $0.006 | $0.007 |

Details: `change_detection_rules.md` and `change_detection_llm_<variant>.md`.
