"""Run the scoped V1/V2 Decision Regression analysis."""

from __future__ import annotations

import pandas as pd

from decision_regression_prep import prepare_decision_regression_data


def overall_by_version(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby("version", sort=False)["overall_pass"]
        .agg(pass_count="sum", case_count="count", pass_rate="mean")
        .reset_index()
    )


def pass_rate_by(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    return (
        frame.groupby(["version", dimension], sort=False)["overall_pass"]
        .agg(pass_count="sum", case_count="count", pass_rate="mean")
        .reset_index()
    )


def token_usage_by_version(frame: pd.DataFrame) -> pd.DataFrame:
    token_columns = ["input_tokens", "output_tokens", "total_tokens"]
    return (
        frame.groupby("version", sort=False)[token_columns]
        .agg(["mean", "sum"])
        .reset_index()
    )


def decision_pass_changes(frame: pd.DataFrame) -> pd.DataFrame:
    paired = frame.pivot(
        index="case_id",
        columns="version",
        values="overall_pass",
    )
    return paired.loc[paired["V1"] != paired["V2"]].reset_index()


def print_table(title: str, table: pd.DataFrame, percent_column=None) -> None:
    display = table.copy()
    if percent_column:
        display[percent_column] = display[percent_column].map(
            lambda value: f"{value:.1%}"
        )
    print(f"\n{title}")
    print(display.to_string(index=False))


def main() -> None:
    frame, validation = prepare_decision_regression_data()
    print("Input validation: PASS")
    print(f"Benchmark SHA-256: {validation['benchmark_sha256']}")

    print_table(
        "1. Overall pass by version",
        overall_by_version(frame),
        "pass_rate",
    )
    print_table(
        "2. Overall pass by version + category",
        pass_rate_by(frame, "category"),
        "pass_rate",
    )
    print_table(
        "3. Overall pass by version + difficulty",
        pass_rate_by(frame, "difficulty"),
        "pass_rate",
    )
    print_table(
        "4. Overall pass by version + language",
        pass_rate_by(frame, "language"),
        "pass_rate",
    )
    print_table(
        "5. API token usage by version",
        token_usage_by_version(frame),
    )

    changes = decision_pass_changes(frame)
    print("\n6. Cases with a V1→V2 decision-level pass change")
    if changes.empty:
        print("None")
    else:
        print(changes.to_string(index=False))


if __name__ == "__main__":
    main()
