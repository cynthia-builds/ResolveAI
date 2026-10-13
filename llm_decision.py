"""Real LLM decision provider for ResolveAI Sprint 2B.

This module only converts natural language into a structured proposal. It does
not query orders, decide refund eligibility, or execute tools.
"""

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL = "gpt-5.6-luna"
API_URL = "https://api.openai.com/v1/responses"

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["policy", "order", "refund", "damage", "unknown"],
        },
        "route": {
            "type": "string",
            "enum": [
                "ANSWER_POLICY",
                "ASK_FOR_INFO",
                "GET_ORDER",
                "CHECK_REFUND",
                "PROCESS_REFUND",
                "ESCALATE",
            ],
        },
        "order_id": {
            "anyOf": [
                {"type": "string", "pattern": "^ORD-[0-9]+$"},
                {"type": "null"},
            ]
        },
        "tool": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "read_policy",
                    "get_order",
                    "check_refund_eligibility",
                    "process_refund",
                ],
            },
        },
        "action": {"type": "string", "enum": ["NONE"]},
        "reason": {"type": "string"},
        "escalated": {"type": "boolean"},
    },
    "required": [
        "intent",
        "route",
        "order_id",
        "tool",
        "action",
        "reason",
        "escalated",
    ],
    "additionalProperties": False,
}

INSTRUCTIONS = """You are the intent router for a fictional e-commerce support prototype.
Return only the decision object required by the supplied schema.

Classify the user's request using these rules:
- Policy questions: intent=policy, route=ANSWER_POLICY.
- Order or delivery-status questions with one order ID: intent=order, route=GET_ORDER.
- Refund requests with one order ID: intent=refund, route=CHECK_REFUND.
- Missing required order ID: route=ASK_FOR_INFO and order_id=null.
- Damaged or broken item claims: intent=damage, route=ESCALATE.
- Unknown or unsupported requests: intent=unknown, route=ESCALATE.
- If multiple order IDs appear, route=ASK_FOR_INFO and order_id=null.

Never determine refund eligibility. Never authorize or execute a refund. Never choose
PROCESS_REFUND; the deterministic executor owns that transition after confirmation.
Set action=NONE. tool is only a proposed plan. Set escalated=true only for ESCALATE.
Use a short uppercase reason code."""


class DecisionProviderError(RuntimeError):
    """Safe, non-secret-bearing error raised for any provider failure."""


def load_api_key():
    """Read the key from the process environment or local .env without logging it."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key

    env_path = Path(__file__).with_name(".env")
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise DecisionProviderError("OPENAI_API_KEY_NOT_CONFIGURED") from error

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("OPENAI_API_KEY="):
            key = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
            break
    raise DecisionProviderError("OPENAI_API_KEY_NOT_CONFIGURED")


def _extract_output_text(response):
    if response.get("status") != "completed":
        raise DecisionProviderError("INCOMPLETE_RESPONSE")
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "refusal":
                raise DecisionProviderError("MODEL_REFUSAL")
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise DecisionProviderError("MISSING_STRUCTURED_OUTPUT")


def real_decision(message):
    """Call Responses API once and return the model's structured decision proposal."""
    payload = {
        "model": MODEL,
        "instructions": INSTRUCTIONS,
        "input": message,
        "reasoning": {"effort": "none"},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "resolveai_decision",
                "strict": True,
                "schema": DECISION_SCHEMA,
            }
        },
        "max_output_tokens": 300,
        "store": False,
    }
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + load_api_key(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as http_response:
            response = json.load(http_response)
        return json.loads(_extract_output_text(response))
    except DecisionProviderError:
        raise
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        raise DecisionProviderError("LLM_REQUEST_FAILED") from error


real_decision.mode = "REAL_LLM"
