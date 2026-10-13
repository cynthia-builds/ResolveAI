"""Prepare aligned V1/V2 human response-quality review data."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_REVIEW = PROJECT_ROOT / "eval/response_quality_review.json"
V2_REVIEW = PROJECT_ROOT / "eval/response_quality_review_v2.json"

SCORE_FIELDS = [
    "helpfulness",
    "completeness",
    "clarity",
    "groundedness",
    "no_unnecessary_friction",
]

COLUMNS = [
    "version",
    "case_id",
    "category",
    "language",
    "difficulty",
    *SCORE_FIELDS,
    "overall_pass",
    "reviewer_notes",
]


def read_json(path: Path) -> dict:
    """Read one human-review file without modifying it."""
    return json.loads(path.read_text(encoding="utf-8"))


def validate_reviews(v1: dict, v2: dict) -> dict:
    """Validate case alignment and binary human-review fields."""
    v1_cases = v1["cases"]
    v2_cases = v2["cases"]
    v1_ids = [case["case_id"] for case in v1_cases]
    v2_ids = [case["case_id"] for case in v2_cases]

    if len(v1_cases) != 15 or len(v2_cases) != 15:
        raise ValueError("V1 and V2 reviews must each contain exactly 15 cases")
    if len(set(v1_ids)) != 15 or len(set(v2_ids)) != 15:
        raise ValueError("Duplicate case_id found in response-quality reviews")
    if v1_ids != v2_ids:
        raise ValueError("V1 and V2 review case IDs or ordering do not match")

    required_scores = [*SCORE_FIELDS, "overall_response_pass"]
    for version, cases in (("V1", v1_cases), ("V2", v2_cases)):
        for case in cases:
            for field in required_scores:
                if field not in case or case[field] not in (0, 1):
                    raise ValueError(
                        f"{version} {case.get('case_id')} has an invalid {field}"
                    )

    return {
        "v1_case_count": len(v1_ids),
        "v2_case_count": len(v2_ids),
        "case_ids_match": True,
        "case_order_matches": True,
        "score_fields_valid": True,
    }


def flatten_reviews(v1: dict, v2: dict) -> pd.DataFrame:
    """Build a long-format table with one row per version and case."""
    metadata_by_id = {
        case["case_id"]: {
            "category": case["category"],
            "language": case["language"],
            "difficulty": case["difficulty"],
        }
        for case in v1["cases"]
    }

    rows = []
    for version, review in (("V1", v1), ("V2", v2)):
        for case in review["cases"]:
            metadata = metadata_by_id[case["case_id"]]
            rows.append(
                {
                    "version": version,
                    "case_id": case["case_id"],
                    **metadata,
                    **{field: case[field] for field in SCORE_FIELDS},
                    "overall_pass": case["overall_response_pass"],
                    "reviewer_notes": case.get("reviewer_notes"),
                }
            )

    frame = pd.DataFrame(rows, columns=COLUMNS).convert_dtypes()
    score_columns = [*SCORE_FIELDS, "overall_pass"]
    frame[score_columns] = frame[score_columns].astype("Int64")
    return frame


def prepare_response_quality_data() -> tuple[pd.DataFrame, dict]:
    """Return the aligned review DataFrame and validation evidence."""
    v1 = read_json(V1_REVIEW)
    v2 = read_json(V2_REVIEW)
    validation = validate_reviews(v1, v2)
    return flatten_reviews(v1, v2), validation


def main() -> None:
    frame, validation = prepare_response_quality_data()
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
