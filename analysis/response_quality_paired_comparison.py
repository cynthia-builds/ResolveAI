"""Pair the seven V1 response-quality bad cases with their V2 results."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from response_quality_prep import SCORE_FIELDS, prepare_response_quality_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_RESULT = PROJECT_ROOT / "eval/results/eval_20261010T084222_257784Z.json"
V2_RESULT = PROJECT_ROOT / "eval/results/eval_20261010T115250_717028Z.json"
BAD_CASE_IDS = [
    "ORD-001",
    "ORD-006",
    "ORD-008",
    "MIS-001",
    "MIS-007",
    "POL-004",
    "POL-005",
]


def load_messages(path: Path) -> dict[str, str | None]:
    result = json.loads(path.read_text(encoding="utf-8"))
    return {
        case["case_id"]: (case.get("response_quality_telemetry") or {}).get("message")
        for case in result["cases"]
    }


def prepare_paired_comparison() -> pd.DataFrame:
    frame, _ = prepare_response_quality_data()
    selected = frame.loc[frame["case_id"].isin(BAD_CASE_IDS)].copy()

    value_columns = [
        "overall_pass",
        *SCORE_FIELDS,
        "reviewer_notes",
    ]
    v1 = selected.loc[selected["version"] == "V1"].set_index("case_id")
    v2 = selected.loc[selected["version"] == "V2"].set_index("case_id")

    paired = v1[["category"]].copy()
    for column in value_columns:
        paired[f"v1_{column}"] = v1[column]
        paired[f"v2_{column}"] = v2[column]

    paired["v1_final_response"] = pd.Series(load_messages(V1_RESULT))
    paired["v2_final_response"] = pd.Series(load_messages(V2_RESULT))
    paired = paired.loc[BAD_CASE_IDS].reset_index()

    if paired[["v1_final_response", "v2_final_response"]].isna().any().any():
        raise ValueError("Missing exact response telemetry for a selected case")
    return paired


def pass_increases(paired: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dimension in SCORE_FIELDS:
        v1_passes = int(paired[f"v1_{dimension}"].sum())
        v2_passes = int(paired[f"v2_{dimension}"].sum())
        rows.append(
            {
                "dimension": dimension,
                "v1_passes": v1_passes,
                "v2_passes": v2_passes,
                "pass_increase": v2_passes - v1_passes,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    paired = prepare_paired_comparison()
    fail_to_pass = int(
        (
            (paired["v1_overall_pass"] == 0)
            & (paired["v2_overall_pass"] == 1)
        ).sum()
    )

    print(f"Paired cases: {len(paired)}")
    print(f"V1 fail → V2 pass: {fail_to_pass}")
    print("\nPass increases by dimension")
    print(pass_increases(paired).to_string(index=False))

    for row in paired.to_dict(orient="records"):
        print("\n" + row["case_id"])
        for key, value in row.items():
            if key != "case_id":
                print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
