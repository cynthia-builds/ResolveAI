# ResolveAI Data Analysis

This folder contains a small, reproducible analysis of ResolveAI's saved Eval results, human response-quality reviews, and local SQLite prototype data. It does not modify the Agent, Golden Dataset, Eval results, or database.

## Data boundaries

- **24 mock orders** in `resolveai.db`, evenly seeded across six statuses.
- **4 local prototype interactions** in `resolveai.db`. These are not production customer events and are not the isolated temporary databases used by the Eval Runner.
- **50-case frozen Decision Eval benchmark** used for both the V1 baseline and V2 regression.
- **15-case human-reviewed Response Quality sample** used for the paired V1/V2 review.
- API token counts come from the real saved API responses. No missing usage is estimated.
- Results are descriptive for this fixed prototype dataset; they are not production-scale or statistically representative customer metrics.

## Python analysis

### 1. Decision Regression

Files:

- `decision_regression_prep.py`
- `decision_regression_analysis.py`

Product question:

> Did the V2 response-layer change preserve the existing decision and safety behavior on the same frozen benchmark?

Skills used:

- Reading nested JSON with Python
- Flattening nested case records into pandas DataFrames
- Nullable Boolean and integer data types
- Validating benchmark hashes, case IDs, order, and metadata
- `concat`, `groupby`, aggregation, and paired case comparison
- Summarizing real API token usage

Observed results:

- V1 overall Decision pass: **50/50 (100%)**
- V2 overall Decision pass: **50/50 (100%)**
- No case changed its decision-level pass status from V1 to V2.
- Every category, difficulty level, and language group was 100% in both saved runs.
- V1 token usage: **18,770 input / 2,638 output / 21,408 total**
- V2 token usage: **18,770 input / 2,619 output / 21,389 total**
- The 19-token difference is one observed run difference and is not evidence of a systematic cost reduction.

### 2. Response Quality Improvement

Files:

- `response_quality_prep.py`
- `response_quality_bad_cases.py`
- `response_quality_paired_comparison.py`

Product question:

> Did the response-only V2 changes improve the human-reviewed answers for the fixed V1 bad cases?

Skills used:

- Aligning V1 and V2 records by `case_id`
- Validating binary human-review scores
- Filtering DataFrames with Boolean conditions
- Pivoting paired V1/V2 records
- Joining exact response telemetry to human-review data
- Calculating pass-count changes without altering review labels

Observed results:

- V1 overall response pass: **8/15 (53.3%)**
- V2 overall response pass: **15/15 (100%)**
- All seven V1 bad cases changed from fail to pass in the V2 human review.
- Within those seven cases, dimension pass counts changed as follows:
  - Helpfulness: **3 → 7**
  - Completeness: **5 → 7**
  - Clarity: **0 → 7**
  - Groundedness: **7 → 7**
  - No unnecessary friction: **7 → 7**

This is a fixed 15-case, human-reviewed sample, not a large-scale user study.

## SQL analysis

File: `queries.sql`

Product questions:

1. How is the mock order inventory distributed by status and amount?
2. Which order facts are connected to recorded refund attempts?
3. Which distinct refund outcomes have occurred locally?
4. Do successful simulated-refund interactions agree with the current `orders.refunded` state?

Skills used:

- `GROUP BY`, `COUNT`, `SUM`, and `AVG`
- `ROUND` for readable amount summaries
- Inner `JOIN` between `orders` and `interactions`
- `DISTINCT` outcome inspection
- Conditional consistency checks with `CASE`
- Filtering with `WHERE` and deterministic ordering with `ORDER BY`

### Actual SQL results

#### Orders by status

| Status | Order count |
|---|---:|
| CANCELLED | 4 |
| DELIVERED | 4 |
| IN_TRANSIT | 4 |
| LOST | 4 |
| PROCESSING | 4 |
| SHIPPED | 4 |

#### Count and amount by status

| Status | Count | Total amount | Average amount |
|---|---:|---:|---:|
| CANCELLED | 4 | 289.50 | 72.38 |
| DELIVERED | 4 | 209.40 | 52.35 |
| IN_TRANSIT | 4 | 362.40 | 90.60 |
| LOST | 4 | 300.05 | 75.01 |
| PROCESSING | 4 | 213.40 | 53.35 |
| SHIPPED | 4 | 211.30 | 52.83 |

#### Orders joined to interactions

| Interaction | Order | Status | Amount | Shipped | Refunded | Action | Result |
|---:|---|---|---:|---:|---:|---|---|
| 1 | ORD-1009 | IN_TRANSIT | 59.00 | 1 | 0 | PROCESS_REFUND | IN_TRANSIT_EXCEPTION_ONLY |
| 2 | ORD-1017 | LOST | 59.00 | 1 | 1 | PROCESS_REFUND | SIMULATED_REFUND_COMPLETED |
| 3 | ORD-1017 | LOST | 59.00 | 1 | 1 | PROCESS_REFUND | ALREADY_REFUNDED |
| 4 | ORD-1018 | LOST | 130.00 | 1 | 1 | PROCESS_REFUND | SIMULATED_REFUND_COMPLETED |

The joined `refunded` value is the order's **current state**, not a historical snapshot at the moment of each interaction.

#### Distinct PROCESS_REFUND results

- `ALREADY_REFUNDED`
- `IN_TRANSIT_EXCEPTION_ONLY`
- `SIMULATED_REFUND_COMPLETED`

The equality filter is `action = 'PROCESS_REFUND'`; underscores do not need escaping with `=`.

#### Successful-refund consistency audit

| Order | Status | Refunded | Interaction result | Audit status |
|---|---|---:|---|---|
| ORD-1017 | LOST | 1 | SIMULATED_REFUND_COMPLETED | CONSISTENT |
| ORD-1018 | LOST | 1 | SIMULATED_REFUND_COMPLETED | CONSISTENT |

No inconsistency was found in this scoped audit: every order with a recorded `SIMULATED_REFUND_COMPLETED` interaction currently has `refunded = 1`.

## Reproducing the analysis

Install the public project dependencies, then run the analysis files with Python when the saved raw Eval artifacts are available locally:

```bash
python3 -m pip install -r requirements.txt
python3 analysis/decision_regression_analysis.py
python3 analysis/response_quality_bad_cases.py
python3 analysis/response_quality_paired_comparison.py
```

The SQL statements in `analysis/queries.sql` are read-only and can be run against `resolveai.db` with any SQLite client. Raw API run JSON is excluded from the public repository because the original artifacts contain local machine paths; the verified aggregate findings are preserved above and in the public Eval summaries.
