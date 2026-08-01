"""
Agentic tool-calling layer for WhatsApp-sourced e-commerce product ingestion.

This is a PORTFOLIO DEMO, not the production system. It runs end-to-end
against the fake in-memory data in sample_data.py, so you can clone this
repo and watch it actually work with no database or API keys required.

The production version (running live) wires the same tool interfaces
to a live MySQL catalog, a real seller-mapping table, and the existing
TF-IDF/LogReg classifier -- swapped in behind these same function
signatures. That part is not included here because it touches proprietary
business data.

Two ways to run this:

    python agentic_categorizer.py            # uses a local Ollama model
    python agentic_categorizer.py --mock     # no Ollama required, uses a
                                              # scripted fake "LLM" so you
                                              # can see the loop mechanics
                                              # without any setup

Ollama mode requires a tool-calling-capable model pulled locally, e.g.:
    ollama pull qwen2.5:7b-instruct
"""

import argparse
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

from sample_data import CATEGORY_TAXONOMY, EXISTING_CATALOG, SELLER_HISTORY, SAMPLE_MESSAGES

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:7b-instruct"
MAX_TOOL_ITERATIONS = 5

logger = logging.getLogger("agentic_categorizer")


# ---------------------------------------------------------------------------
# 1. Tool schemas -- what the model is told it can call
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_similar_products",
            "description": (
                "Search the catalog for products similar to a given name/"
                "description. Always call this before proposing a new "
                "product, to avoid inserting a duplicate."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_category_taxonomy",
            "description": "Return the list of valid categories. You must use one of these exact names.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_seller_history",
            "description": "Look up how reliable this supplier (by JID) has historically been.",
            "parameters": {
                "type": "object",
                "properties": {"jid": {"type": "string"}},
                "required": ["jid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_for_review",
            "description": (
                "Escalate this item to a human review queue instead of "
                "auto-inserting it. Use when the image description is "
                "vague or the text gives no usable product info."
            ),
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_product_record",
            "description": "FINAL STEP. Submit the structured product record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "description": {"type": "string"},
                    "is_duplicate_of": {"type": ["integer", "null"], "description": "catalog id if this is a duplicate"},
                    "confidence": {"type": "number"},
                },
                "required": ["name", "category", "description", "confidence"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# 2. Tool implementations -- wired to the fake in-memory data
# ---------------------------------------------------------------------------

def search_similar_products(query: str) -> dict:
    query_words = set(query.lower().split())
    matches = []
    for product in EXISTING_CATALOG:
        name_words = set(product["name"].lower().split())
        overlap = query_words & name_words
        if overlap:
            matches.append({
                "id": product["id"],
                "name": product["name"],
                "category": product["category"],
                "overlap": list(overlap),
                "overlap_count": len(overlap),
            })
    matches.sort(key=lambda m: m["overlap_count"], reverse=True)
    return {"matches": matches}


def get_category_taxonomy() -> dict:
    return {"categories": CATEGORY_TAXONOMY}


def check_seller_history(jid: str) -> dict:
    return SELLER_HISTORY.get(jid, {"known_since_days": 0, "items_submitted": 0, "approval_rate": None, "common_categories": []})


def flag_for_review(reason: str) -> dict:
    logger.info("FLAGGED FOR REVIEW: %s", reason)
    return {"status": "flagged", "reason": reason}


def propose_product_record(**fields) -> dict:
    logger.info("PROPOSED RECORD: %s", json.dumps(fields))
    return {"status": "proposed", "record": fields}


TOOL_IMPL = {
    "search_similar_products": search_similar_products,
    "get_category_taxonomy": get_category_taxonomy,
    "check_seller_history": check_seller_history,
    "flag_for_review": flag_for_review,
    "propose_product_record": propose_product_record,
}


# ---------------------------------------------------------------------------
# 3. Orchestration loop
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an autonomous catalog agent for an e-commerce marketplace.

You receive a WhatsApp supplier post: an image description (already
generated by a vision model), the caption text, and the sender's JID.

Decide whether to add this as a new product -- or flag it for human
review if you're not confident. Use the tools; do not guess.

Rules:
1. Always call get_category_taxonomy before proposing a category.
2. Always call search_similar_products before proposing a new product.
   If a close match exists, set is_duplicate_of to its id instead of
   proposing a fresh entry with confidence above 0.5.
3. If the image description is vague or the text gives no usable
   product info, call flag_for_review and stop.
4. End every successful run with exactly one call to propose_product_record.
"""


@dataclass
class AgentResult:
    status: str
    record: Optional[dict] = None
    tool_trace: list = field(default_factory=list)


def _call_ollama(messages: list) -> dict:
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "messages": messages, "tools": TOOLS, "stream": False},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["message"]


def _call_mock_llm(messages: list) -> dict:
    """
    A scripted stand-in for the LLM, with no network calls, so this repo
    runs with zero setup. It follows the same rules a real tool-calling
    model would, using simple heuristics on the message content -- it's
    here to demonstrate the LOOP MECHANICS, not to replace a real model.
    """
    user_msg = next(m["content"] for m in messages if m["role"] == "user")
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    step = len(tool_msgs)

    if "blurry" in user_msg.lower() or "indeterminate" in user_msg.lower():
        if step == 0:
            return {"role": "assistant", "tool_calls": [{"function": {"name": "flag_for_review", "arguments": {"reason": "Image description is too vague to identify the product"}}}]}

    if step == 0:
        return {"role": "assistant", "tool_calls": [{"function": {"name": "get_category_taxonomy", "arguments": {}}}]}
    if step == 1:
        query = user_msg.split("Image description: ")[1].split("\n")[0]
        return {"role": "assistant", "tool_calls": [{"function": {"name": "search_similar_products", "arguments": {"query": query}}}]}
    if step == 2:
        last_result = json.loads(tool_msgs[-1]["content"])
        matches = last_result.get("matches", [])
        if matches:
            return {"role": "assistant", "tool_calls": [{"function": {"name": "propose_product_record", "arguments": {
                "name": user_msg.split("Caption text: ")[1].split("\n")[0],
                "category": matches[0]["category"],
                "description": "Auto-generated description would go here",
                "is_duplicate_of": matches[0]["id"],
                "confidence": 0.55,
            }}}]}
        return {"role": "assistant", "tool_calls": [{"function": {"name": "propose_product_record", "arguments": {
            "name": user_msg.split("Caption text: ")[1].split("\n")[0],
            "category": "Electronics & Accessories",
            "description": "Auto-generated description would go here",
            "is_duplicate_of": None,
            "confidence": 0.8,
        }}}]}
    return {"role": "assistant", "content": "done"}


def run_agent(image_description: str, caption_text: str, jid: str, use_mock: bool = False) -> AgentResult:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Image description: {image_description}\nCaption text: {caption_text}\nSender JID: {jid}"},
    ]
    trace = []

    for step in range(MAX_TOOL_ITERATIONS):
        msg = _call_mock_llm(messages) if use_mock else _call_ollama(messages)
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            logger.warning("No tool call at step %d: %s", step, msg.get("content"))
            continue

        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"].get("arguments", {})
            trace.append({"tool": fn_name, "args": fn_args})

            impl = TOOL_IMPL.get(fn_name)
            result = impl(**fn_args) if impl else {"error": f"unknown tool {fn_name}"}
            messages.append({"role": "tool", "content": json.dumps(result)})

            if fn_name == "propose_product_record":
                return AgentResult(status="proposed", record=result.get("record"), tool_trace=trace)
            if fn_name == "flag_for_review":
                return AgentResult(status="flagged", record=result, tool_trace=trace)

    return AgentResult(status="max_iterations", tool_trace=trace)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Run without Ollama, using a scripted fake LLM")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    for i, msg in enumerate(SAMPLE_MESSAGES, 1):
        print(f"\n--- Message {i} ---")
        result = run_agent(**msg, use_mock=args.mock)
        print(f"Status: {result.status}")
        if result.record:
            print(f"Record: {json.dumps(result.record, indent=2)}")
        print(f"Tool calls made: {[t['tool'] for t in result.tool_trace]}")
