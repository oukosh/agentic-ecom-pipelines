"""
Smoke test: confirms every sample message runs through the agent loop
(mock mode) without errors and produces a valid, expected status.

This is intentionally simple -- it's here so a reviewer can run one
command and see the demo is actually functional, not just present.

    python test_demo.py
"""

from agentic_categorizer import run_agent
from sample_data import SAMPLE_MESSAGES

VALID_STATUSES = {"proposed", "flagged", "max_iterations"}


def test_all_sample_messages_produce_valid_results():
    for i, msg in enumerate(SAMPLE_MESSAGES, 1):
        result = run_agent(**msg, use_mock=True)
        assert result.status in VALID_STATUSES, f"Message {i}: unexpected status {result.status}"
        assert len(result.tool_trace) > 0, f"Message {i}: agent made no tool calls"
        if result.status == "proposed":
            assert result.record.get("category") in {
                "Kitchen & Dining", "Home & Living", "Electronics & Accessories",
                "Fashion & Apparel", "Beauty & Personal Care", "Baby & Kids",
                "Phone Accessories", "Office Supplies",
            }, f"Message {i}: category not in taxonomy"
    print(f"OK: all {len(SAMPLE_MESSAGES)} sample messages produced valid results")


def test_vague_image_gets_flagged_not_guessed():
    vague_msg = {
        "image_description": "Blurry, out-of-focus photo of an indeterminate small object, possibly electronic",
        "caption_text": "bei poa",
        "jid": "254798765432@s.whatsapp.net",
    }
    result = run_agent(**vague_msg, use_mock=True)
    assert result.status == "flagged", "Agent should escalate ambiguous items instead of guessing"
    print("OK: ambiguous item correctly flagged for review instead of auto-categorized")


if __name__ == "__main__":
    test_all_sample_messages_produce_valid_results()
    test_vague_image_gets_flagged_not_guessed()
    print("\nAll tests passed.")
