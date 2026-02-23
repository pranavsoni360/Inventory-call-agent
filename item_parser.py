# item_parser.py
# Stateless item parser. Takes a text string, returns a ParseResult.
# No side effects. No state access. Fully unit-testable in isolation.
#
# Three-tier pipeline:
#   Tier 1 — Regex pattern matching (fastest, most precise)
#   Tier 2 — Token scanning (catches partial inputs)
#   Tier 3 — LLM fallback (caller's responsibility, only if result is empty)

import re
from dataclasses import dataclass
from typing import Optional

from constants import (
    UNIT_CANONICAL, KNOWN_UNITS, KNOWN_ITEMS,
    STOP_WORDS, ACCUMULATE_WORDS,
    MAX_ITEM_QUANTITY,
)


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ParseResult:
    name:          Optional[str]   = None
    quantity:      Optional[float] = None
    unit:          Optional[str]   = None
    is_accumulate: bool            = False
    is_update:     bool            = False
    confidence:    str             = "none"  # "high" | "medium" | "low" | "none"

    def has_any(self) -> bool:
        return any([self.name, self.quantity is not None, self.unit])

    def is_complete(self) -> bool:
        return (
            self.name     is not None
            and self.quantity is not None
            and self.unit     is not None
        )

    def missing(self) -> list:
        slots = []
        if self.name     is None: slots.append("name")
        if self.quantity is None: slots.append("quantity")
        if self.unit     is None: slots.append("unit")
        return slots

    def __repr__(self):
        return (
            f"ParseResult(name={self.name!r}, qty={self.quantity}, "
            f"unit={self.unit!r}, accum={self.is_accumulate}, "
            f"update={self.is_update}, conf={self.confidence!r})"
        )


# ── Public entry point ────────────────────────────────────────────────────────

def parse_item(raw_text: str) -> ParseResult:
    """
    Main parser. Always returns a ParseResult. Never raises.
    """
    if not raw_text or not raw_text.strip():
        return ParseResult()

    text = _normalize(raw_text)
    result = ParseResult()

    # Intent flags
    result.is_accumulate = _detect_accumulate(text)
    result.is_update     = _detect_update(text)

    # Tier 1: pattern matching
    result = _tier1(text, result)

    # Tier 2: token scan for anything still missing
    if not result.is_complete():
        result = _tier2(text, result)

    # Set confidence
    if result.is_complete():
        result.confidence = "high" if result.name in KNOWN_ITEMS else "medium"
    elif result.has_any():
        name_only_unknown = (
            result.name     is not None
            and result.quantity is None
            and result.unit     is None
            and result.name not in KNOWN_ITEMS
        )
        if name_only_unknown:
            result.confidence = "none"
            result.name = None
        else:
            result.confidence = "medium" if (result.name or result.quantity is not None) else "low"
    else:
        result.confidence = "none"

    # Sanity clamp on quantity
    if result.quantity is not None:
        if result.quantity <= 0 or result.quantity > MAX_ITEM_QUANTITY:
            result.quantity = None
            if result.confidence == "high":
                result.confidence = "medium"

    return result


# ── Normalizer ────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    import string
    text = text.lower().strip()
    # Strip punctuation from each word so "sugar." "oil," "milk!" all parse correctly
    text = " ".join(w.strip(string.punctuation) for w in text.split())
    text = re.sub(r'\s+', ' ', text)

    number_words = {
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
        "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
        "half": "0.5", "quarter": "0.25",
        "ek": "1", "do": "2", "teen": "3", "char": "4", "paanch": "5",
        "chhe": "6", "saat": "7", "aath": "8", "nau": "9", "das": "10",
    }
    for word, digit in number_words.items():
        text = re.sub(rf'\b{word}\b', digit, text)

    # Hindi / transliteration item name mappings
    hindi_items = {
        # Grains
        "chawal": "rice", "chaawal": "rice", "चावल": "rice",
        "gehu": "wheat", "gehun": "wheat", "गेहूं": "wheat",
        "makki": "corn", "makai": "corn", "मक्का": "corn",
        "jowar": "jowar", "bajra": "bajra", "ragi": "ragi",
        # Pulses
        "daal": "dal", "dhal": "dal", "दाल": "dal",
        "chana": "besan", "chanay": "besan",
        # Sugar & Salt
        "cheeni": "sugar", "shakkar": "sugar", "chini": "sugar",
        "शक्कर": "sugar", "चीनी": "sugar", "शुगर": "sugar",
        "namak": "salt", "नमक": "salt",
        # Oils
        "tel": "oil", "sarson ka tel": "mustard oil", "तेल": "oil",
        # Dairy
        "dudh": "milk", "दूध": "milk",
        "dahi": "curd",
        # Spices
        "haldi": "turmeric", "हल्दी": "turmeric",
        "mirch": "chilli", "मिर्च": "chilli",
        "jeera": "cumin", "जीरा": "cumin",
        "sarson": "mustard", "सरसों": "mustard",
        "adrak": "ginger", "अदरक": "ginger",
        "lahsun": "garlic", "लहसुन": "garlic",
        # Vegetables
        "aloo": "potato", "aaloo": "potato", "आलू": "potato",
        "pyaaz": "onion", "pyaz": "onion", "प्याज": "onion",
        "tamatar": "tomato", "टमाटर": "tomato",
        "palak": "spinach", "पालक": "spinach",
        "gajar": "carrot", "गाजर": "carrot",
        "gobhi": "cabbage", "gobi": "cabbage", "गोभी": "cabbage",
        "matar": "peas", "मटर": "peas",
        "brinjal": "brinjal", "baingan": "brinjal", "बैंगन": "brinjal",
        # Other
        "atta": "atta", "आटा": "atta",
        "maida": "maida", "मैदा": "maida",
        "sooji": "sooji", "suji": "sooji",
        "poha": "poha", "पोहा": "poha",
        "chai": "tea", "चाय": "tea",
        "nariyal": "coconut", "नारियल": "coconut",
        "mungfali": "groundnut",
        # Packaged
        "maggi": "maggi", "नूडल्स": "maggi", "मैगी": "maggi",
        "namkeen": "namkeen",
    }

    # Hindi filler words to remove
    hindi_fillers = {
        "थोड़ी", "थोड़ा", "थोड़े", "कुछ", "भी", "चाहिए",
        "दीजिए", "देना", "करना", "वाला", "जरा",
    }

    for hindi, english in hindi_items.items():
        text = re.sub(rf'(?<!\w){re.escape(hindi)}(?!\w)', english, text)

    for filler in hindi_fillers:
        text = re.sub(rf'(?<!\w){re.escape(filler)}(?!\w)', '', text)

    # Clean up extra spaces after removals
    text = re.sub(r'\s+', ' ', text).strip()

    # Strip natural speech prefixes so parser can find the item
    speech_prefixes = [
        r"^i would like to order\s+",
        r"^i want to order\s+",
        r"^please add\s+",
        r"^can you add\s+",
        r"^add\s+",
        r"^i need\s+",
        r"^order\s+",
        r"^mujhe\s+chahiye\s+",
        r"^mujhe\s+",
        r"^dena\s+",
        r"^mujhe\s+",
        r"^haan\s+",
        r"^bhi\s+",
    ]
    for prefix in speech_prefixes:
        text = re.sub(prefix, "", text)

    return text


# ── Intent flag detectors ─────────────────────────────────────────────────────

def _detect_accumulate(text: str) -> bool:
    tokens = set(text.split())
    return bool(tokens & ACCUMULATE_WORDS)


def _detect_update(text: str) -> bool:
    update_triggers = {"change", "update", "modify", "replace", "set", "correct", "edit"}
    tokens = set(text.split())
    return bool(tokens & update_triggers)


# ── Tier 1: Regex pattern matching ───────────────────────────────────────────

_UNIT_PATTERN = "|".join(
    sorted(KNOWN_UNITS, key=len, reverse=True)
)

_PATTERNS = [
    # "5 kg rice" | "5kg rice" | "5 kilograms of rice"
    rf'(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})\s+(?:of\s+)?(?P<n>[a-z]+)',
    # "rice 5 kg" | "rice 5kg"
    rf'(?P<n>[a-z]+)\s+(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})',
    # "5 kg" alone — name comes from slot buffer
    rf'(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})',
    # "rice 5" — unit will be asked
    rf'(?P<n>[a-z]+)\s+(?P<qty>\d+(?:\.\d+)?)\b',
]


def _tier1(text: str, result: ParseResult) -> ParseResult:
    for pattern in _PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue

        groups = m.groupdict()

        if 'qty' in groups and groups['qty'] is not None and result.quantity is None:
            result.quantity = float(groups['qty'])

        if 'unit' in groups and groups['unit'] is not None and result.unit is None:
            raw_unit = groups['unit']
            result.unit = UNIT_CANONICAL.get(raw_unit, raw_unit)

        if 'n' in groups and groups['n'] is not None and result.name is None:
            candidate = groups['n']
            if _is_valid_name(candidate):
                result.name = candidate

        if result.quantity is not None:
            break

    return result


# ── Tier 2: Token scanning ────────────────────────────────────────────────────

def _tier2(text: str, result: ParseResult) -> ParseResult:
    tokens = text.split()

    for token in tokens:

        if result.quantity is None:
            try:
                val = float(token)
                result.quantity = val
                continue
            except ValueError:
                pass

        if result.unit is None and token in UNIT_CANONICAL:
            result.unit = UNIT_CANONICAL[token]
            continue

        if result.name is None:
            # Check KNOWN_ITEMS first — direct match
            if token in KNOWN_ITEMS:
                result.name = token
                continue
            # Then general validity check
            if _is_valid_name(token):
                result.name = token

    return result


# ── Name validator ────────────────────────────────────────────────────────────

def _is_valid_name(word: str) -> bool:
    if not word or len(word) < 3:
        return False
    if word in STOP_WORDS:
        return False
    if word in UNIT_CANONICAL:
        return False
    try:
        float(word)
        return False
    except ValueError:
        pass
    if not word.isalpha():
        return False
    return True


def extract_items_with_llm(text: str) -> list[dict]:
    """
    Returns list of {name, quantity, unit} dicts from natural speech.
    Used when regex parser fails on complex Hindi/mixed utterances.
    """
    try:
        from groq import Groq
        import os, json
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"""
Extract all grocery items from this text. Text may be Hindi, English or mixed.
Text: "{text}"
Respond ONLY with JSON array:
[{{"name": "rice", "quantity": 2.0, "unit": "kg"}}, ...]
If quantity or unit unknown, use null.
Common Hindi→English: चावल=rice, दाल=dal, शक्कर/चीनी=sugar, प्याज=onion, 
अदरक=ginger, शेंगदाना/मूंगफली=groundnut, तेल=oil, आटा=atta
"""}],
            temperature=0,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except Exception:
        return []