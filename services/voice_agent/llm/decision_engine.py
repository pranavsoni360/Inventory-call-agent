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


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class IntentResult:
    intent:   str
    raw_text: str
    llm_used: bool = False


# ── Vocabulary sets ───────────────────────────────────────────────────────────

ACKNOWLEDGEMENTS = {
    "okay", "ok", "alright", "great", "fine", "cool", "sure",
    "thanks", "thank", "nice", "good", "perfect", "wonderful",
    "aight", "gotcha", "noted", "understood", "makes sense",
}

IDLE_DEAD_ENDS = {
    "no", "nope", "nah", "nothing", "nevermind", "never", "mind",
    "forget", "leave", "drop", "skip", "ignore",
}


# ── Main entry point ──────────────────────────────────────────────────────────

def decide(user_input: str, state: ConversationState) -> IntentResult:
    text   = user_input.lower().strip()
    tokens = set(text.split())

    # ── Phase: AWAITING_CONFIRM ───────────────────────────────────────────────
    if state.phase == Phase.AWAITING_CONFIRM:
        if tokens & AFFIRM_WORDS:
            return IntentResult(intent="user_confirmed", raw_text=text)
        if tokens & DENY_WORDS:
            return IntentResult(intent="user_denied", raw_text=text)
        return IntentResult(intent="confirmation_unclear", raw_text=text)

    # ── Phase: SLOT_FILLING ───────────────────────────────────────────────────
    if state.phase == Phase.SLOT_FILLING:
        if tokens & EXIT_WORDS:
            return IntentResult(intent="exit", raw_text=text)
        if tokens & DENY_WORDS:
            return IntentResult(intent="user_denied", raw_text=text)
        return IntentResult(intent="slot_response", raw_text=text)

    # ── Phase: IDLE ───────────────────────────────────────────────────────────

    # Exit
    if tokens & EXIT_WORDS:
        return IntentResult(intent="exit", raw_text=text)

    # Show cart
    if tokens & SHOW_CART_WORDS:
        return IntentResult(intent="show_cart", raw_text=text)

    # Confirm order
    if tokens & CONFIRM_ORDER_WORDS:
        return IntentResult(intent="confirm_order", raw_text=text)

    # Greeting — short inputs only
    if tokens & {"hello", "hi", "hey", "heya", "hiya"} and len(tokens) <= 3:
        return IntentResult(intent="greeting", raw_text=text)

    # Acknowledgements and dead-ends — never hit LLM for these
    if tokens & (ACKNOWLEDGEMENTS | IDLE_DEAD_ENDS) and not (tokens & KNOWN_ITEMS) and not re.search(r'\d', text):
        return IntentResult(intent="acknowledgement", raw_text=text)

    # Remove item
    if tokens & REMOVE_WORDS:
        return IntentResult(intent="remove_item", raw_text=text)

    # Update item
    if tokens & UPDATE_WORDS:
        return IntentResult(intent="update_item", raw_text=text)

    # Digits or known units → add_item
    if re.search(r'\d', text):
        return IntentResult(intent="add_item", raw_text=text)

    if tokens & KNOWN_UNITS:
        return IntentResult(intent="add_item", raw_text=text)

    # Known item word → add_item
    if tokens & KNOWN_ITEMS:
        return IntentResult(intent="add_item", raw_text=text)

    # ── LLM fallback — only for genuinely ambiguous inputs ───────────────────
    if state.llm_calls >= MAX_LLM_CALLS_PER_SESSION:
        return IntentResult(intent="clarify", raw_text=text)

    return _llm_classify(text, state)


# ── LLM classifier ────────────────────────────────────────────────────────────

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
Classify the user message into exactly one intent.

Current cart: {cart_summary if cart_summary else 'empty'}
User message: "{text}"

Respond with ONLY valid JSON, no explanation, no markdown:
{{"intent": "<one of: {', '.join(allowed_intents)}>"}}"""

    from shared.utils.rate_limiter import gemini_limiter
    if not gemini_limiter.acquire():
        logger.warning("[DecisionEngine] Rate limited — returning clarify")
        return IntentResult(intent="clarify", raw_text=text, llm_used=False)

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
        logger.info(f"[DecisionEngine] LLM classified: {text!r} → {intent}")
        return IntentResult(intent=intent, raw_text=text, llm_used=True)

    except Exception as e:
        logger.warning(f"[DecisionEngine] LLM error: {e}")
        return IntentResult(intent="clarify", raw_text=text, llm_used=True)