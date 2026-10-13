# Response Quality Review Rubric

Score each dimension with **1 (PASS)** or **0 (FAIL)**. Leave scores as `null` until a human reviewer evaluates the actual user-facing response. A FAIL requires a specific, explainable negative impact on the user. Do not fail a response because of personal preferences about tone, wording, length, or writing style.

## Helpfulness

- **1 — PASS:** The response directly helps the user understand the outcome or take the appropriate next step.
- **0 — FAIL:** A wrong, irrelevant, or non-actionable response materially prevents progress or directs the user toward an inappropriate next step.

## Completeness

- **1 — PASS:** The response includes the information necessary for the user to understand the outcome and any required next action, confirmation, or limitation.
- **0 — FAIL:** A material omission leaves the user unable to understand the result or complete the next required step.

## Clarity

- **1 — PASS:** The response is understandable and unambiguous for the request at hand.
- **0 — FAIL:** Ambiguous, contradictory, or confusing wording creates a realistic risk that the user misunderstands the outcome or next step.

## Groundedness

- **1 — PASS:** Material claims are consistent with the tool, database, and policy facts already present in the review record.
- **0 — FAIL:** A material claim contradicts those facts or introduces an unsupported factual assertion that could affect the user's understanding or action.

Groundedness must be judged only against the recorded tool, database, and policy facts. Do not infer missing facts or penalize a response for omitting facts that are not needed for the user's request.

## No Unnecessary Friction

- **1 — PASS:** The response requests only information, confirmation, or human review that is necessary under the recorded outcome and safety rules.
- **0 — FAIL:** It creates avoidable work, repetition, delay, or escalation with a concrete negative impact on the user.

## Overall Response Pass

- Set `overall_response_pass` to **1** only when all five dimensions are **1**.
- Set it to **0** when any dimension is **0**.
- Keep it `null` until all five dimension scores have been completed by a human reviewer.

Use `reviewer_notes` to identify the concrete user impact for every FAIL score.
