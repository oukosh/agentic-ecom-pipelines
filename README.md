# Agentic Product Categorizer (Portfolio Demo)

A tool-calling LLM agent that decides how to categorize e-commerce products
from supplier WhatsApp posts — checking for duplicates, picking a category,
or escalating to human review when it isn't confident. Runs end-to-end with
no setup required.

## What this is (and isn't)

This is a **sanitized portfolio demo**, not the production system. It
demonstrates the actual agent architecture I use in production on a live
e-commerce marketplace — but wired to fake, in-memory data
(`sample_data.py`) instead of a live MySQL catalog and real supplier data,
so it's safe to share publicly.

What's real: the tool-calling loop, the tool schemas, the escalation logic,
and the orchestration code — copy-pasted from what runs in production.

What's swapped out: `search_similar_products`, `get_category_taxonomy`, and
`check_seller_history` here read from Python lists in `sample_data.py`
instead of a real database. In production these query live tables.

No performance numbers are claimed here (throughput, accuracy, uptime)
because none are measured in this demo — that data exists in production
logs, not in a portfolio repo with fake data.

## How it works

```
WhatsApp supplier post (image description + caption + sender JID)
        |
        v
  Agent loop (agentic_categorizer.py)
        |
        +--> get_category_taxonomy      (always called first)
        +--> search_similar_products    (checks for duplicates)
        +--> check_seller_history       (available, not always used)
        +--> flag_for_review            (if too ambiguous to decide)
        +--> propose_product_record     (final structured output)
```

The model is given the tools above and decides, step by step, which ones
to call and in what order — it isn't a fixed sequence. See
`SYSTEM_PROMPT` in `agentic_categorizer.py` for the exact rules it's given.

## Running it

**Option A — no setup, scripted mock LLM:**

```bash
pip install -r requirements.txt
python agentic_categorizer.py --mock
```

This uses a small rule-based stand-in for the LLM (see `_call_mock_llm`)
so you can see the tool-calling loop mechanics without installing
anything else. It is clearly not a real model — it's there so this repo
runs in under a minute for anyone reviewing it.

**Option B — real local LLM via Ollama:**

```bash
ollama pull qwen2.5:7b-instruct
ollama serve   # if not already running
pip install -r requirements.txt
python agentic_categorizer.py
```

This uses an actual tool-calling model running locally — same mechanism
as production, just against the fake sample data instead of a live
catalog.

## Example output

```
--- Message 1 ---
Status: proposed
Record: {
  "name": "sieve bei rahisi 250",
  "category": "Kitchen & Dining",
  "is_duplicate_of": 101,
  "confidence": 0.55
}
Tool calls made: ['get_category_taxonomy', 'search_similar_products', 'propose_product_record']

--- Message 3 ---
Status: flagged
Record: {"status": "flagged", "reason": "Image description is too vague to identify the product"}
Tool calls made: ['flag_for_review']
```

Message 3 uses a deliberately blurry sample image description to show the
escalation path — the agent recognizes it can't confidently categorize
the item and stops instead of guessing.

## Files

- `agentic_categorizer.py` — the agent loop, tool schemas, and tool
  implementations (wired to fake data)
- `sample_data.py` — fake catalog, category list, and seller history used
  by the demo
- `test_demo.py` — smoke test confirming all sample messages run without
  errors and produce a valid status
- `requirements.txt` — one dependency (`requests`)

## Related work

Part of a broader set of e-commerce automation systems I've built,
including a WhatsApp-based supplier ingestion pipeline (Baileys + FastAPI
+ Ollama vision) and a competitive market-gap scraper. This repo focuses
specifically on the agentic decision layer.
