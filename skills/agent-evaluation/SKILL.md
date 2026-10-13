---
name: agent-evaluation
description: Run or extend repeatable agent evaluations against a frozen Golden Dataset, with isolated state, auditable failures, safety-first scoring, and version-comparable metrics. Use for ResolveAI benchmark runs, pilot evaluations, failure analysis, and V1/V2 comparisons; do not use to change business behavior or relabel the benchmark to improve scores.
---

# Agent Evaluation

Treat the Golden Dataset as a frozen specification and actual outputs as run
artifacts. Never edit expected values in response to model behavior. Change a
Golden label only when an objective annotation error is independently shown,
and report that benchmark change explicitly.

## Evaluation invariants

- Keep expected data in the Golden Dataset and actual data under a separate,
  timestamped results path. Never overwrite the benchmark.
- Score `model_decision` separately from the deterministic executor result.
  Model intent, route, and order extraction are proposal metrics; final route,
  actual tool trace, action, reason, eligibility, and escalation are executor
  metrics.
- Start every case from an isolated, freshly seeded database. Never let a refund
  mutation affect a later case.
- Compare routing, exact ordered tool trace, missing-information handling,
  escalation, and unsafe execution. Treat `UNSAFE_ACTION` as the highest-severity
  failure and primary failure type whenever it occurs.
- Preserve bad cases with expected values, actual values, provider error,
  failure categories, and attempt count. Do not silently discard API, refusal,
  schema, parse, or timeout failures.
- Do not silently retry a failed provider call. Any explicitly authorized retry
  must remain a separate auditable attempt.
- Use the same frozen benchmark, identified by its content hash, for V1/V2
  comparisons. A changed hash means the results are not directly comparable.
- Report only metrics calculated from completed recorded runs. Never invent,
  estimate, extrapolate, or backfill metrics for cases that were not run.

## Safety and execution

Real-provider evaluation requires explicit selection and authorization for that
run. Default commands must not call a paid API. Executable cases may perform only
the prototype's simulated action inside their isolated database.

Store a primary `failure_type` and all applicable `failure_types`. Supported
types are `INTENT_ERROR`, `ROUTING_ERROR`, `TOOL_ERROR`,
`MISSING_INFO_ERROR`, `ESCALATION_ERROR`, `UNSAFE_ACTION`, and `OTHER`.

When comparing versions, include the benchmark hash, selected case IDs,
provider/mode, timestamp, per-case records, aggregate metrics, and breakdowns by
difficulty, category, and language.
