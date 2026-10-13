# ResolveAI Response Quality: V1 → V2

Both versions use the same frozen 15-case sample and the unchanged rubric in `eval/response_quality_rubric.md`. Scores are human review results, not automated estimates.

| Metric | V1 | V2 | Change |
|---|---:|---:|---:|
| Overall response pass | 8/15 (53.3%) | 15/15 (100.0%) | +46.7 pp |
| Helpfulness | 11/15 (73.3%) | 15/15 (100.0%) | +26.7 pp |
| Completeness | 13/15 (86.7%) | 15/15 (100.0%) | +13.3 pp |
| Clarity | 8/15 (53.3%) | 15/15 (100.0%) | +46.7 pp |
| Groundedness | 15/15 (100.0%) | 15/15 (100.0%) | 0.0 pp |
| No unnecessary friction | 15/15 (100.0%) | 15/15 (100.0%) | 0.0 pp |

V1 failed cases were `ORD-001`, `ORD-006`, `ORD-008`, `MIS-001`, `MIS-007`, `POL-004`, and `POL-005`. All 15 cases passed the V2 human response-quality review.
