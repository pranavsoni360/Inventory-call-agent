# constants.py
KNOWN_ITEMS = {
    "rice", "wheat", "sugar", "oil", "dal", "flour",
    "salt", "atta", "maida", "sooji", "poha", "tea",
    "coffee", "milk", "ghee", "butter", "bread", "ragi",
    "bajra", "jowar", "besan", "semolina", "suji",
    "mustard", "cumin", "turmeric", "chilli", "pepper",
    "onion", "potato", "tomato", "garlic", "ginger",
    "carrot", "cabbage", "brinjal", "spinach", "peas",
    "lemon", "coconut", "groundnut", "soya", "corn",
}

UNIT_CANONICAL = {
    "kg": "kg", "kilo": "kg", "kilos": "kg",
    "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gram": "g", "grams": "g",
    "litre": "litre", "litres": "litre",
    "liter": "litre", "liters": "litre",
    "l": "litre", "ltr": "litre", "ltrs": "litre",
    "ml": "ml", "millilitre": "ml", "milliliter": "ml",
    "packet": "packet", "packets": "packet",
    "pack": "packet", "pkt": "packet", "pkts": "packet",
    "piece": "piece", "pieces": "piece",
    "pcs": "piece", "pc": "piece",
    "barrel": "barrel", "barrels": "barrel",
    "dozen": "dozen", "box": "box", "boxes": "box",
    "bottle": "bottle", "bottles": "bottle",
    "tin": "tin", "tins": "tin",
    "bag": "bag", "bags": "bag",
    "sack": "bag", "sacks": "bag",
}

KNOWN_UNITS = set(UNIT_CANONICAL.keys())

STOP_WORDS = {
    "add", "put", "want", "i", "need", "of", "the", "a", "an",
    "please", "some", "more", "to", "and", "give", "me", "get",
    "would", "like", "could", "can", "also", "another", "few",
    "much", "many", "my", "your", "our", "this", "that", "it",
    "for", "with", "from", "in", "on", "at", "by", "about",
    "order", "buy", "purchase", "take", "bring", "send",
    "require", "have", "got", "man", "bro", "sir", "madam",
    "hey", "sup", "yo", "aight", "nah", "yep", "hmm", "okay",
    "ok", "oh", "ah", "uh", "um", "right", "sure", "well",
    "just", "now", "then", "here", "there", "let", "say",
    "tell", "know", "think", "said", "nothing", "something",
    "everything", "anything", "wrong", "reply", "properly",
    "what", "how", "when", "where", "why", "who", "which",
    "up", "down", "out", "off", "over", "under", "back",
}

AFFIRM_WORDS = {
    "yes", "yeah", "yep", "yup", "correct", "right",
    "ok", "okay", "sure", "confirm", "absolutely", "definitely",
    "fine", "agreed", "proceed", "haan", "bilkul",
}

DENY_WORDS = {
    "no", "nope", "nah", "cancel", "wrong", "incorrect",
    "dont", "not", "stop", "wait", "hold",
    "different", "mistake", "error", "nahi",
}

ACCUMULATE_WORDS = {
    "more", "extra", "additional", "another", "again",
}

EXIT_WORDS = {
    "bye", "goodbye", "exit", "quit",
    "finish", "thats all", "nothing else", "done",
}

SHOW_CART_WORDS = {
    "show", "cart", "list", "display",
    "review", "summary",
}

CONFIRM_ORDER_WORDS = {
    "confirm", "place", "finalize", "submit", "complete",
}

UPDATE_WORDS = {
    "change", "update", "modify", "replace", "correct",
    "edit", "fix", "set",
}

REMOVE_WORDS = {
    "remove", "delete", "drop",
}

MAX_CART_ITEMS            = 20
MAX_ITEM_QUANTITY         = 9999
MAX_TURNS_PER_SESSION     = 100
MAX_LLM_CALLS_PER_SESSION = 50