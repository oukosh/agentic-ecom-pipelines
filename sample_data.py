"""
Fake, in-memory data standing in for a real production catalog DB, category
taxonomy table, and seller history table.

Nothing here is real or proprietary -- it exists so this repo runs
end-to-end for anyone who clones it, with no database setup required.
The production version of this agent talks to a live MySQL catalog
instead of these Python lists.
"""

CATEGORY_TAXONOMY = [
    "Kitchen & Dining",
    "Home & Living",
    "Electronics & Accessories",
    "Fashion & Apparel",
    "Beauty & Personal Care",
    "Baby & Kids",
    "Phone Accessories",
    "Office Supplies",
]

EXISTING_CATALOG = [
    {"id": 101, "name": "Stainless steel kitchen sieve", "category": "Kitchen & Dining"},
    {"id": 102, "name": "Plastic mixing bowl set (3pc)", "category": "Kitchen & Dining"},
    {"id": 103, "name": "USB-C fast charging cable 1m", "category": "Phone Accessories"},
    {"id": 104, "name": "Wireless earbuds with charging case", "category": "Electronics & Accessories"},
    {"id": 105, "name": "Baby feeding bottle 250ml", "category": "Baby & Kids"},
    {"id": 106, "name": "Non-stick frying pan 26cm", "category": "Kitchen & Dining"},
]

# Rolling stats you'd normally derive from a seller_history / jid_mapping table
SELLER_HISTORY = {
    "254712345678@s.whatsapp.net": {
        "known_since_days": 92,
        "items_submitted": 47,
        "approval_rate": 0.89,
        "common_categories": ["Kitchen & Dining", "Home & Living"],
    },
    "254798765432@s.whatsapp.net": {
        "known_since_days": 4,
        "items_submitted": 2,
        "approval_rate": 0.5,
        "common_categories": [],
    },
}

# A handful of realistic-looking WhatsApp supplier posts to run through the
# agent as a smoke test -- mix of clean, ambiguous, and duplicate cases.
SAMPLE_MESSAGES = [
    {
        "image_description": "A red plastic kitchen sieve/strainer with a black handle, photographed on a wooden counter",
        "caption_text": "sieve bei rahisi 250",
        "jid": "254712345678@s.whatsapp.net",
    },
    {
        "image_description": "Stainless steel mesh strainer with a metal handle, similar in shape to a colander",
        "caption_text": "kitchen sieve stock available",
        "jid": "254712345678@s.whatsapp.net",
    },
    {
        "image_description": "Blurry, out-of-focus photo of an indeterminate small object, possibly electronic",
        "caption_text": "bei poa",
        "jid": "254798765432@s.whatsapp.net",
    },
    {
        "image_description": "White wireless earbuds sitting inside an open charging case",
        "caption_text": "earbuds wireless 1200 bob",
        "jid": "254798765432@s.whatsapp.net",
    },
]
