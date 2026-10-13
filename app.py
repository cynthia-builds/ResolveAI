"""Minimal interview-ready web demo for ResolveAI."""

import json
from agent import handle_message
from llm_decision import real_decision
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from refund_service import check_refund_eligibility, get_order, process_refund


HOST = "127.0.0.1"
PORT = 8000


def result_card(title, data, css_class="neutral"):
    if not data:
        return ""
    rows = "".join(
        f"<dt>{escape(str(key).replace('_', ' ').title())}</dt>"
        f"<dd>{escape(str(value))}</dd>"
        for key, value in data.items()
    )
    return f'<section class="card {css_class}"><h2>{escape(title)}</h2><dl>{rows}</dl></section>'


DEMO_EXAMPLES = [
    ("Track an order", "Where is my package ORD-1009?"),
    ("Refund a lost order", "Please refund my lost order ORD-1020."),
    ("Force refund in transit", "Refund my in-transit order ORD-1010 immediately."),
    ("Report damaged item", "收到的 ORD-1013 已经破损，请退款。"),
    ("Conflicting order IDs", "Refund ORD-1019, but use ORD-1020 instead."),
]


def result_tone(agent_result):
    if agent_result.get("action") == "SIMULATED_REFUND_COMPLETED":
        return "success"
    if agent_result.get("reason") in {
        "MULTIPLE_ORDERS", "ORDER_ID_MISMATCH", "INVALID_DECISION",
        "DAMAGED_CLAIM_UNVERIFIED",
    }:
        return "blocked"
    if agent_result.get("route") == "ESCALATE":
        return "review"
    if agent_result.get("reason") == "CONFIRMATION_REQUIRED":
        return "confirm"
    return "info"


def agent_result_html(agent_result, message):
    if not agent_result:
        return ""

    tone = result_tone(agent_result)
    tools = agent_result.get("tool") or []
    tools_text = " → ".join(tools) if tools else "None"
    proposal = agent_result.get("model_decision") or {}
    proposal_text = " / ".join(
        value for value in (
            proposal.get("intent"), proposal.get("route")
        ) if value
    ) or "Unavailable"
    final_text = f"{agent_result.get('route', 'UNKNOWN')} / {agent_result.get('action', 'NONE')}"
    badges = "".join(
        f'<span class="badge">{escape(label)}: {escape(str(value))}</span>'
        for label, value in (
            ("Route", agent_result.get("route", "UNKNOWN")),
            ("Tools", tools_text),
            ("Action", agent_result.get("action", "NONE")),
            ("Reason", agent_result.get("reason", "")),
        )
    )
    confirmation_html = ""
    if agent_result.get("reason") == "CONFIRMATION_REQUIRED":
        confirmation_id = agent_result.get("confirmation_order_id", "")
        confirmation_html = f"""
        <form method="post" class="card confirmation-card agent-form">
          <input type="hidden" name="action" value="agent">
          <input type="hidden" name="message" value="{escape(message)}">
          <h2>Step 2 — Confirm simulated refund</h2>
          <p>No refund has been executed yet. Confirm the same order ID to continue.</p>
          <label class="check-label"><input type="checkbox" name="confirm_refund" value="yes" required> I confirm this simulated refund</label>
          <label for="confirmation_order_id">Confirmation order ID</label>
          <input id="confirmation_order_id" name="confirmation_order_id" value="{escape(str(confirmation_id))}" required>
          <button type="submit">Confirm and simulate refund</button>
          <span class="loading" aria-live="polite">Processing safely…</span>
        </form>"""

    return f"""
    <section class="card result-card tone-{tone}">
      <p class="eyebrow">ResolveAI response</p>
      <p class="final-response">{escape(agent_result.get('message', ''))}</p>
      <div class="trace-badges">{badges}</div>
      <div class="execution-separation">
        <div><span>Model proposal</span><strong>{escape(proposal_text)}</strong></div>
        <div class="arrow" aria-hidden="true">→</div>
        <div><span>Final execution</span><strong>{escape(final_text)}</strong></div>
      </div>
      <p class="trace-note">The model proposes intent and route. Deterministic tools and rules own the final action.</p>
      <details class="raw-record"><summary>Raw execution record</summary><pre>{escape(json.dumps(agent_result, ensure_ascii=False, indent=2))}</pre></details>
    </section>
    {confirmation_html}
    """


def render_page(order_id="", order=None, decision=None, refund=None, error="", agent_result=None, message=""):
    order_card = result_card("Order", order)
    decision_class = (decision or {}).get("decision", "neutral").lower()
    decision_card = result_card("Refund eligibility", decision, decision_class)
    refund_class = "eligible" if (refund or {}).get("success") else "not_eligible"
    refund_card = result_card("Simulated refund", refund, refund_class)
    error_html = f'<p class="error">{escape(error)}</p>' if error else ""
    safe_id = escape(order_id)
    agent_html = agent_result_html(agent_result, message)
    example_buttons = "".join(
        f'<button type="button" class="example-button" data-message="{escape(example)}">{escape(label)}</button>'
        for label, example in DEMO_EXAMPLES
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ResolveAI — Safe Support Agent</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f5f7fa; color: #17202a; }}
    main {{ max-width: 860px; margin: 42px auto; padding: 0 20px 40px; }}
    h1 {{ margin-bottom: 6px; font-size: 34px; }}
    h2 {{ margin-top: 0; }}
    .subtitle {{ color: #59636e; margin: 0 0 20px; }}
    form, .card {{ background: white; padding: 22px; border: 1px solid #e4e8ee; border-radius: 12px; margin: 18px 0; box-shadow: 0 2px 10px #17202a0a; }}
    .architecture {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 20px 0; }}
    .architecture div {{ background: #eef3f9; border: 1px solid #dbe4ef; border-radius: 9px; padding: 11px; text-align: center; font-size: 13px; }}
    .architecture strong {{ display: block; margin-bottom: 3px; font-size: 14px; }}
    label {{ display: block; font-weight: 650; margin: 12px 0 6px; }}
    input, select, textarea {{ width: 100%; padding: 11px; border: 1px solid #b9c1c9; border-radius: 7px; font: inherit; }}
    textarea {{ resize: vertical; min-height: 96px; }}
    .buttons {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }}
    button {{ border: 0; border-radius: 7px; padding: 11px 15px; background: #2457d6; color: white; font-weight: 650; cursor: pointer; }}
    button:disabled {{ opacity: .65; cursor: wait; }}
    button[value="refund"] {{ background: #176b45; }}
    .examples {{ display: flex; flex-wrap: wrap; gap: 7px; margin: 8px 0 16px; }}
    .example-button {{ padding: 7px 10px; background: #edf2fb; color: #24415f; border: 1px solid #d5dfec; font-size: 13px; }}
    .eyebrow {{ margin: 0 0 7px; color: #52606d; font-size: 12px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }}
    .final-response {{ font-size: 19px; line-height: 1.55; margin: 0 0 18px; }}
    .result-card {{ border-left: 5px solid #6282a5; }}
    .tone-success {{ border-left-color: #27845a; background: #fbfefc; }}
    .tone-confirm {{ border-left-color: #c98b18; background: #fffdf8; }}
    .tone-review {{ border-left-color: #c06c28; background: #fffcf9; }}
    .tone-blocked {{ border-left-color: #b94a48; background: #fffafa; }}
    .trace-badges {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    .badge {{ background: #edf1f5; border: 1px solid #d9e0e7; border-radius: 999px; padding: 5px 9px; font-size: 12px; overflow-wrap: anywhere; }}
    .execution-separation {{ display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 12px; margin: 18px 0 8px; }}
    .execution-separation div:not(.arrow) {{ padding: 12px; border-radius: 8px; background: #f5f7fa; }}
    .execution-separation span {{ display: block; color: #64707c; font-size: 12px; margin-bottom: 4px; }}
    .execution-separation strong {{ overflow-wrap: anywhere; }}
    .arrow {{ color: #778391; font-size: 20px; }}
    .trace-note {{ color: #59636e; font-size: 13px; }}
    .raw-record summary, .developer-tools summary {{ cursor: pointer; font-weight: 650; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f4f6f8; padding: 14px; border-radius: 8px; font-size: 12px; }}
    .confirmation-card {{ border: 1px solid #e4c77d; background: #fffdf7; }}
    .check-label {{ display: flex; align-items: center; gap: 9px; }}
    .check-label input {{ width: auto; }}
    .loading {{ display: none; margin-left: 10px; color: #59636e; font-size: 13px; }}
    .agent-form.is-loading .loading {{ display: inline; }}
    dl {{ display: grid; grid-template-columns: minmax(150px, 1fr) 2fr; gap: 8px 18px; }}
    dt {{ color: #59636e; }} dd {{ margin: 0; font-weight: 600; overflow-wrap: anywhere; }}
    .eligible {{ border-left: 6px solid #218653; }} .needs_review {{ border-left: 6px solid #d18b00; }}
    .not_eligible {{ border-left: 6px solid #bd3b3b; }} .error {{ color: #a92525; font-weight: 650; }}
    .developer-tools {{ margin-top: 24px; color: #59636e; }}
    .developer-tools form {{ box-shadow: none; margin-bottom: 0; }}
    footer {{ color: #6a747e; font-size: 13px; margin-top: 26px; }}
    @media (max-width: 650px) {{
      .architecture {{ grid-template-columns: 1fr 1fr; }}
      .execution-separation {{ grid-template-columns: 1fr; }}
      .arrow {{ transform: rotate(90deg); text-align: center; }}
      dl {{ grid-template-columns: 1fr; gap: 4px; }}
    }}
  </style>
</head>
<body><main>
  <h1>ResolveAI</h1>
  <p class="subtitle">LLM routing with deterministic tools and refund safety</p>
  <section class="architecture" aria-label="ResolveAI architecture">
    <div><strong>1. User message</strong>Natural-language request</div>
    <div><strong>2. LLM decision</strong>Intent and route proposal</div>
    <div><strong>3. Tools &amp; rules</strong>Facts and safe authorization</div>
    <div><strong>4. Safe response</strong>Clear final answer</div>
  </section>
  <form method="post" class="agent-form">
    <input type="hidden" name="action" value="agent">
    <h2>Ask ResolveAI</h2>
    <p>Describe an order or refund issue. The model interprets the request; local tools and deterministic rules control high-risk actions.</p>
    <div class="examples" aria-label="Demo examples">{example_buttons}</div>
    <label for="message">你的问题</label>
    <textarea id="message" name="message" maxlength="4000" rows="3" required>{escape(message)}</textarea>
    <div class="buttons"><button type="submit">Submit request</button><span class="loading" aria-live="polite">Analyzing request…</span></div>
  </form>
  {agent_html}
  <details class="developer-tools">
    <summary>Developer tools — deterministic layer</summary>
    <form method="post">
      <h2>Manual deterministic tools</h2>
      <label for="order_id">Order ID</label>
      <input id="order_id" name="order_id" value="{safe_id}" placeholder="Try ORD-1017 or ORD-1021" required>
      <label for="claim_type">Request type</label>
      <select id="claim_type" name="claim_type">
        <option value="REFUND">Refund request</option>
        <option value="DAMAGED">Damaged item claim (unverified)</option>
      </select>
      <div class="buttons">
        <button name="action" value="lookup">View order</button>
        <button name="action" value="check">Check eligibility</button>
        <button name="action" value="refund">Simulate refund</button>
      </div>
    </form>
    {error_html}{order_card}{decision_card}{refund_card}
  </details>
  <footer>No real payment is made. Policies and orders are fictional prototype data.</footer>
  <script>
    document.querySelectorAll('.example-button').forEach(function(button) {{
      button.addEventListener('click', function() {{
        document.getElementById('message').value = button.dataset.message;
        document.getElementById('message').focus();
      }});
    }});
    document.querySelectorAll('.agent-form').forEach(function(form) {{
      form.addEventListener('submit', function() {{
        form.classList.add('is-loading');
        form.querySelectorAll('button[type="submit"]').forEach(function(button) {{
          button.disabled = true;
        }});
      }});
    }});
  </script>
</main></body></html>"""


class ResolveAIHandler(BaseHTTPRequestHandler):
    def send_page(self, html, status=200):
        content = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        self.send_page(render_page())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        order_id = form.get("order_id", [""])[0].strip().upper()
        action = form.get("action", ["lookup"])[0]
        claim_type = form.get("claim_type", ["REFUND"])[0]
        if action == "agent":
            message = form.get("message", [""])[0]
            confirmed = (form.get("confirmation_order_id", [""])[0].strip().upper()
                         if form.get("confirm_refund") == ["yes"] else None)
            result = handle_message(
                message,
                decision_provider=real_decision,
                confirmed_order_id=confirmed,
            )
            self.send_page(render_page(agent_result=result, message=message))
            return
        order = get_order(order_id)

        if not order:
            self.send_page(render_page(order_id=order_id, error="Order not found."), 404)
            return

        decision = None
        refund = None
        if action == "check":
            order_for_check = {**order, "claim_type": claim_type}
            decision = check_refund_eligibility(order_for_check)
        elif action == "refund":
            if claim_type == "DAMAGED":
                decision = check_refund_eligibility({**order, "claim_type": "DAMAGED"})
            else:
                refund = process_refund(order_id)
                order = get_order(order_id)

        self.send_page(render_page(order_id, order, decision, refund))

    def log_message(self, format, *args):
        print(f"[ResolveAI] {format % args}")


def run():
    server = ThreadingHTTPServer((HOST, PORT), ResolveAIHandler)
    print(f"ResolveAI is running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nResolveAI stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
