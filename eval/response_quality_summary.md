# ResolveAI V1 Response Quality Summary

This summary records the completed human review of the fixed 15-case V1 Response Quality sample. Scores are copied from the reviewer and are not automated judgments.

## Overall Result

- Overall response pass: **8/15 (53.3%)**
- Failed cases: `ORD-001`, `ORD-006`, `ORD-008`, `MIS-001`, `MIS-007`, `POL-004`, `POL-005`

## Dimension Pass Rates

| Dimension | Passed | Pass rate |
|---|---:|---:|
| Helpfulness | 11/15 | 73.3% |
| Completeness | 13/15 | 86.7% |
| Clarity | 8/15 | 53.3% |
| Groundedness | 15/15 | 100.0% |
| No unnecessary friction | 15/15 | 100.0% |

## Root-cause Taxonomy

1. **Internal implementation leakage** — User-facing responses expose internal field names or machine-style values instead of presenting the result naturally.
2. **Relevant-information selection failure / omission or overload** — Responses omit useful facts already available or reproduce more policy information than the question requires.
3. **Generic missing-info template ignores known context** — The response asks for information or restatement that the user's message has already supplied.

## Qualitative Observation

Language mismatch appeared in some responses. It is recorded only as a qualitative observation and does not retroactively change any human score.
