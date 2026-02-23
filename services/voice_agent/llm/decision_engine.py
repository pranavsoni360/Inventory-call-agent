# services/voice_agent/llm/decision_engine.py
# Phase-aware intent classifier.
# Returns an IntentResult — never modifies state.
# LLM is only called when all deterministic rules fail.

import os
import json
import re
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

from shared.logging.logger import get_logger

logger = get_logger("decision_engine")

load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env")

from constants import (
    AFFIRM_WORDS, DENY_WORDS, EXIT_WORDS,
    SHOW_CART_WORDS, CONFIRM_ORDER_WORDS,
    UPDATE_WORDS, REMOVE_WORDS, KNOWN_ITEMS,
    KNOWN_UNITS, MAX_LLM_CALLS_PER_SESSION,
)
from conversation_state import ConversationState, Phase


@dataclass
class IntentResult:
    intent:   str
    raw_text: str
    llm_used: bool = False


ACKNOWLEDGEMENTS = {
    "okay", "ok", "alright", "great", "fine", "cool", "sure",
    "thanks", "thank", "nice", "good", "perfect", "wonderful",
    "aight", "gotcha", "noted", "understood", "makes sense",
    # Hindi transliteration
    "theek", "accha", "acha", "shukriya", "dhanyawad",
}

IDLE_DEAD_ENDS = {
    "nothing", "nevermind", "never", "mind",
    "forget", "leave", "ignore",
}

# Hindi Devanagari affirmation tokens (single words)
HINDI_AFFIRM = {"हाँ", "हां", "हा", "जी", "बिल्कुल", "ज़रूर", "करो", "जोड़ो"}
HINDI_DENY   = {"नहीं", "नही", "मत", "रुको", "बंद", "गलत"}


def decide(user_input: str, state: ConversationState) -> IntentResult:
    import string
    text   = user_input.strip()
    lower  = text.lower()
    # Strip punctuation from each token so "yes." "yes," "yes!" all match
    tokens = set(w.strip(string.punctuation) for w in lower.split())

    # ── Hindi token check (Devanagari) ────────────────────────────────────────
    text_tokens = set(text.split())

    # ── Phase: AWAITING_CONFIRM ───────────────────────────────────────────────
    if state.phase == Phase.AWAITING_CONFIRM:
        if (tokens & AFFIRM_WORDS) or (text_tokens & HINDI_AFFIRM):
            return IntentResult(intent="user_confirmed", raw_text=lower)
        if (tokens & DENY_WORDS) or (text_tokens & HINDI_DENY):
            return IntentResult(intent="user_denied", raw_text=lower)
        return IntentResult(intent="confirmation_unclear", raw_text=lower)

    # ── Phase: SLOT_FILLING ───────────────────────────────────────────────────
    if state.phase == Phase.SLOT_FILLING:
        if tokens & EXIT_WORDS:
            return IntentResult(intent="exit", raw_text=lower)
        if (tokens & DENY_WORDS) or (text_tokens & HINDI_DENY):
            return IntentResult(intent="user_denied", raw_text=lower)
        return IntentResult(intent="slot_response", raw_text=lower)

    # ── Phase: IDLE ───────────────────────────────────────────────────────────

    if tokens & EXIT_WORDS:
        return IntentResult(intent="exit", raw_text=lower)

    if tokens & SHOW_CART_WORDS:
        return IntentResult(intent="show_cart", raw_text=lower)

    if tokens & CONFIRM_ORDER_WORDS:
        return IntentResult(intent="confirm_order", raw_text=lower)

    if tokens & {"hello", "hi", "hey", "heya", "hiya", "namaste", "namaskar"} and len(tokens) <= 4:
        return IntentResult(intent="greeting", raw_text=lower)

    if tokens & (ACKNOWLEDGEMENTS | IDLE_DEAD_ENDS) and not (tokens & KNOWN_ITEMS) and not re.search(r'\d', lower):
        return IntentResult(intent="acknowledgement", raw_text=lower)

    if tokens & REMOVE_WORDS:
        return IntentResult(intent="remove_item", raw_text=lower)

    if tokens & UPDATE_WORDS:
        return IntentResult(intent="update_item", raw_text=lower)

    if re.search(r'\d', lower):
        return IntentResult(intent="add_item", raw_text=lower)

    if tokens & KNOWN_UNITS:
        return IntentResult(intent="add_item", raw_text=lower)

    if tokens & KNOWN_ITEMS:
        return IntentResult(intent="add_item", raw_text=lower)

    # Direct known item name — always add_item
    if tokens & KNOWN_ITEMS:
        return IntentResult(intent="add_item", raw_text=lower)

    # ── LLM fallback ─────────────────────────────────────────────────────────
    if state.llm_calls >= MAX_LLM_CALLS_PER_SESSION:
        return IntentResult(intent="clarify", raw_text=lower)

    return _llm_classify(lower, state)


def _llm_classify(text: str, state: ConversationState) -> IntentResult:
    allowed_intents = [
        "add_item", "update_item", "remove_item",
        "show_cart", "confirm_order", "greeting",
        "exit", "clarify"
    ]

    cart_summary = [
        f"{i['quantity']} {i['unit']} {i['name']}"
        for i in state.items
    ]

    prompt = f"""You are an intent classifier for a ration ordering phone agent.
Works in Hindi and English. Classify the user message into exactly one intent.

Current cart: {cart_summary if cart_summary else 'empty'}
User message: "{text}"

Respond with ONLY valid JSON:
{{"intent": "<one of: {', '.join(allowed_intents)}>"}}"""

    try:
        from groq import Groq
        client   = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=50,
        )
        raw    = response.choices[0].message.content.strip()
        raw    = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(raw)
        intent = parsed.get("intent", "clarify")
        if intent not in allowed_intents:
            intent = "clarify"
        state.llm_calls += 1
        logger.info(f"[DecisionEngine] LLM: {text!r} → {intent}")
        return IntentResult(intent=intent, raw_text=text, llm_used=True)
    except Exception as e:
        logger.warning(f"[DecisionEngine] LLM error: {e}")
        return IntentResult(intent="clarify", raw_text=text, llm_used=True)