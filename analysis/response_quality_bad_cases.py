"""Filter and display V1 response-quality bad cases without interpreting them."""

from __future__ import annotations

import json
from pathlib import Path

from response_quality_prep import prepare_response_quality_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_TELEMETRY_RESULT = (
    PROJECT_ROOT / "eval/results/eval_20261010T084222_257784Z.json"
)

DISPLAY_COLUMNS = [
    "case_id",
    "category",
    "language",
    "helpfulness",
    "completeness",
    "clarity",
    "groundedness",
    "no_unnecessary_friction",
    "reviewer_notes",
    "final_response",
]


def load_v1_messages() -> dict[str, str | None]:
    result = json.loads(V1_TELEMETRY_RESULT.read_text(encoding="utf-8"))
    return {
        case["case_id"]: (case.get("response_quality_telemetry") or {}).get("message")
        for case in result["cases"]
    }


def prepare_v1_bad_cases():
    frame, _ = prepare_response_quality_data()
    bad_cases = frame.loc[
        (frame["version"] == "V1") & (frame["overall_pass"] == 0)
    ].copy()
    bad_cases["final_response"] = bad_cases["case_id"].map(load_v1_messages())
    if bad_cases["final_response"].isna().any():
        missing = bad_cases.loc[
            bad_cases["final_response"].isna(), "case_id"
        ].tolist()
        raise ValueError(f"Missing V1 response telemetry for: {missing}")
    return bad_cases[DISPLAY_COLUMNS].reset_index(drop=True)


def main() -> None:
    bad_cases = prepare_v1_bad_cases()
    print(f"V1 bad cases: {len(bad_cases)}")
    for row in bad_cases.to_dict(orient="records"):
        print("\n" + row["case_id"])
        for column in DISPLAY_COLUMNS[1:]:
            print(f"- {column}: {row[column]}")


if __name__ == "__main__":
    main()
