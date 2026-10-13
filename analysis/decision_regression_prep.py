"""Prepare paired V1/V2 Decision Eval data without changing source files."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_RESULT = PROJECT_ROOT / "eval/results/eval_20261010T082058_754842Z.json"
V2_RESULT = PROJECT_ROOT / "eval/results/eval_20261010T120509_651584Z.json"
FROZEN_BENCHMARK_SHA256 = (
    "c38ccd8c1c6dd700efd2678dae67693db9b72bfe007c8f2a1a6ec291280b0dd3"
)

COLUMNS = [
    "version",
    "case_id",
    "category",
    "difficulty",
    "language",
    "routing_pass",
    "tool_selection_pass",
    "missing_info_applicable",
    "missing_info_pass",
    "escalation_pass",
    "final_fields_pass",
    "overall_pass",
    "unsafe_action",
    "api_attempts",
    "api_success",
    "provider_error_type",
    "provider_error_code",
    "input_tokens",
    "output_tokens",
    "total_tokens",
]


def read_result(path: Path) -> dict:
    """Read one saved Eval result as JSON; never modify the source file."""
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_cases(result: dict, version: str) -> pd.DataFrame:
    """Turn nested per-case Eval records into one analysis-ready table."""
    rows = []
    for case in result["cases"]:
        checks = case["checks"]
        audit = case["provider_audit"]
        error = audit.get("error") or {}
        usage = case.get("api_usage") or {}
        rows.append(
            {
                "version": version,
                "case_id": case["case_id"],
                "category": case["category"],
                "difficulty": case["difficulty"],
                "language": case["language"],
                "routing_pass": checks["routing"],
                "tool_selection_pass": checks["tool_selection"],
                "missing_info_applicable": checks["missing_info_applicable"],
                "missing_info_pass": checks["missing_info"],
                "escalation_pass": checks["escalation"],
                "final_fields_pass": checks["final_fields"],
                "overall_pass": case["pass"],
                "unsafe_action": checks["unsafe_action"],
                "api_attempts": audit["attempt_count"],
                "api_success": audit.get("error") is None,
                "provider_error_type": error.get("type"),
                "provider_error_code": error.get("code"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }
        )

    frame = pd.DataFrame(rows, columns=COLUMNS).convert_dtypes()
    boolean_columns = [
        "routing_pass",
        "tool_selection_pass",
        "missing_info_applicable",
        "missing_info_pass",
        "escalation_pass",
        "final_fields_pass",
        "overall_pass",
        "unsafe_action",
        "api_success",
    ]
    frame[boolean_columns] = frame[boolean_columns].astype("boolean")
    return frame


def validate_inputs(v1: dict, v2: dict) -> dict:
    """Fail early if the two runs are not a valid frozen-benchmark pair."""
    v1_ids = [case["case_id"] for case in v1["cases"]]
    v2_ids = [case["case_id"] for case in v2["cases"]]

    if v1["benchmark_sha256"] != FROZEN_BENCHMARK_SHA256:
        raise ValueError("V1 benchmark SHA-256 does not match the frozen benchmark")
    if v2["benchmark_sha256"] != FROZEN_BENCHMARK_SHA256:
        raise ValueError("V2 benchmark SHA-256 does not match the frozen benchmark")
    if len(v1_ids) != 50 or len(v2_ids) != 50:
        raise ValueError("Both Decision Eval runs must contain exactly 50 cases")
    if len(set(v1_ids)) != len(v1_ids) or len(set(v2_ids)) != len(v2_ids):
        raise ValueError("Duplicate case_id found")
    if v1_ids != v2_ids:
        raise ValueError("V1 and V2 case IDs or ordering do not match")

    metadata_fields = ("category", "difficulty", "language")
    for v1_case, v2_case in zip(v1["cases"], v2["cases"], strict=True):
        if any(v1_case[field] != v2_case[field] for field in metadata_fields):
            raise ValueError(f"Case metadata mismatch: {v1_case['case_id']}")

    return {
        "benchmark_sha256": FROZEN_BENCHMARK_SHA256,
        "v1_case_count": len(v1_ids),
        "v2_case_count": len(v2_ids),
        "case_ids_match": True,
        "case_order_matches": True,
        "case_metadata_matches": True,
    }


def prepare_decision_regression_data() -> tuple[pd.DataFrame, dict]:
    """Return a long-format V1/V2 DataFrame plus validation evidence."""
    v1 = read_result(V1_RESULT)
    v2 = read_result(V2_RESULT)
    validation = validate_inputs(v1, v2)
    frame = pd.concat(
        [flatten_cases(v1, "V1"), flatten_cases(v2, "V2")],
        ignore_index=True,
    )
    return frame, validation


def main() -> None:
    frame, validation = prepare_decision_regression_data()
    print("Validation")
    for key, value in validation.items():
        print(f"- {key}: {value}")
    print(f"\nDataFrame shape: {frame.shape}")
    print("\nColumns")
    for column in frame.columns:
        print(f"- {column}: {frame.dtypes[column]}")
    print("\nFirst 5 rows")
    print(frame.head().to_string(index=False))


if __name__ == "__main__":
    main()
