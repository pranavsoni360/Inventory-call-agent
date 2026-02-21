# services/voice_agent/action_executor.py
# The ONLY place state is mutated.
# Receives IntentResult + ConversationState, returns response string.
# For conversational turns, delegates response generation to Groq.

import os
import uuid
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

from conversation_state import ConversationState, Phase, SlotBuffer
from item_parser import parse_item
from constants import MAX_CART_ITEMS


# ── Smart conversational response via Groq ────────────────────────────────────

def _groq_respond(user_text: str, state: ConversationState, context: str = "") -> str:
    """
    Generates a natural conversational response using Groq.
    Used for greetings, acknowledgements, clarifications, and small talk.
    Falls back to a simple default if Groq fails.
    """
    cart_summary = ", ".join(
        f"{i['quantity']} {i['unit']} {i['name']}" for i in state.items
    ) or "empty"

    system = """You are a friendly ration ordering assistant on a phone call.
You help customers place their monthly grocery orders.
Keep responses SHORT (1-2 sentences max), warm, and natural.
If the customer is making small talk, respond naturally but gently guide them back to ordering.
Never make up order details. Never confirm things the customer didn't say.
Speak like a helpful human agent, not a robot."""

    user_prompt = f"""Customer said: "{user_text}"
Current cart: {cart_summary}
{f'Context: {context}' if context else ''}
Respond naturally in 1-2 sentences."""

    try:
        from groq import Groq
        client   = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=80,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return context if context else "What items would you like to order today?"


# ── Main entry point ──────────────────────────────────────────────────────────

def execute(intent_result, state: ConversationState) -> str:
    intent = intent_result.intent
    raw    = intent_result.raw_text

    state.turn_count += 1

    # ── Confirmation phase ────────────────────────────────────────────────────
    if intent == "user_confirmed":
        return _handle_confirmed(state)

    if intent == "user_denied":
        return _handle_denied(state)

    if intent == "confirmation_unclear":
        buf = state.slot_buffer
        if buf.is_order_confirm():
            return _groq_respond(raw, state, "Ask them to say yes or no to confirm their full order.")
        return _groq_respond(
            raw, state,
            f"Ask them to say yes or no to add {buf.quantity} {buf.unit} of {buf.name}."
        )

    # ── Slot filling ──────────────────────────────────────────────────────────
    if intent == "slot_response":
        return _handle_slot_response(raw, state)

    # ── Cart display ──────────────────────────────────────────────────────────
    if intent == "show_cart":
        return _format_cart(state)

    # ── Confirm full order ────────────────────────────────────────────────────
    if intent == "confirm_order":
        if not state.items:
            return _groq_respond(raw, state, "Their cart is empty. Ask them to add items first.")
        state.slot_buffer.clear()
        state.slot_buffer.name = "__ORDER_CONFIRM__"
        state.force_transition(Phase.AWAITING_CONFIRM)
        return (
            f"You want to place this order?\n"
            f"{_format_cart_inline(state)}\n"
            f"Say yes to confirm or no to cancel."
        )

    # ── Greeting ──────────────────────────────────────────────────────────────
    if intent == "greeting":
        return _groq_respond(raw, state, "Greet them warmly and ask what they'd like to order.")

    # ── Acknowledgement — smart contextual response ───────────────────────────
    if intent == "acknowledgement":
        cart_count = len(state.items)
        if cart_count == 0:
            return _groq_respond(raw, state, "They acknowledged. Invite them to start ordering.")
        return _groq_respond(
            raw, state,
            f"They acknowledged. They have {cart_count} item(s) in cart. Ask if they want to add more or confirm."
        )

    # ── Exit ──────────────────────────────────────────────────────────────────
    if intent == "exit":
        return "__EXIT__"

    # ── Clarify — smart response instead of fixed string ─────────────────────
    if intent == "clarify":
        return _groq_respond(
            raw, state,
            "You didn't understand. Politely ask them to clarify or suggest they say something like 'add 5 kg rice'."
        )

    # ── Add item ──────────────────────────────────────────────────────────────
    if intent == "add_item":
        return _handle_add_item(raw, state)

    # ── Update item ───────────────────────────────────────────────────────────
    if intent == "update_item":
        return _handle_add_item(raw, state, is_update=True)

    # ── Remove item ───────────────────────────────────────────────────────────
    if intent == "remove_item":
        return _handle_remove_item(raw, state)

    return _groq_respond(raw, state, "Something unexpected happened. Ask them to repeat.")


# ── Add / update item ─────────────────────────────────────────────────────────

def _handle_add_item(raw: str, state: ConversationState,
                     is_update: bool = False) -> str:
    if len(state.items) >= MAX_CART_ITEMS:
        return f"Your cart is full ({MAX_CART_ITEMS} items maximum)."

    if " and " in raw:
        raw = raw.split(" and ")[0].strip()

    parsed = parse_item(raw)
    state.slot_buffer.merge_from_parse(parsed)
    if is_update:
        state.slot_buffer.is_update = True

    if state.phase == Phase.IDLE:
        state.transition(Phase.SLOT_FILLING)

    if state.slot_buffer.is_complete():
        state.transition(Phase.AWAITING_CONFIRM)
        buf    = state.slot_buffer
        action = "update" if buf.is_update else "add"
        more   = " more" if buf.is_accumulate else ""
        return (
            f"Got it — {buf.quantity} {buf.unit} of {buf.name.title()}{more}. "
            f"Shall I {action} this? Say yes or no."
        )

    return _ask_for_missing(state.slot_buffer)


def _handle_slot_response(raw: str, state: ConversationState) -> str:
    parsed = parse_item(raw)
    state.slot_buffer.merge_from_parse(parsed)

    if state.slot_buffer.is_complete():
        state.transition(Phase.AWAITING_CONFIRM)
        buf    = state.slot_buffer
        action = "update" if buf.is_update else "add"
        more   = " more" if buf.is_accumulate else ""
        return (
            f"Got it — {buf.quantity} {buf.unit} of {buf.name.title()}{more}. "
            f"Shall I {action} this? Say yes or no."
        )

    return _ask_for_missing(state.slot_buffer)


def _ask_for_missing(buf: SlotBuffer) -> str:
    slot    = buf.next_missing()
    attempt = getattr(buf, '_ask_count', 0)
    buf._ask_count = attempt + 1

    if slot == "name":
        options = [
            "Which item would you like to add?",
            "What item did you have in mind?",
            "Could you tell me the item name? For example — rice, dal, or sugar.",
        ]
        return options[min(attempt, len(options) - 1)]

    if slot == "quantity":
        name = buf.name.title() if buf.name else "that item"
        options = [
            f"How much {name} would you like?",
            f"What quantity of {name} do you need?",
            f"Please tell me the amount of {name} — for example, 5 or 2.5.",
        ]
        return options[min(attempt, len(options) - 1)]

    if slot == "unit":
        options = [
            "In what unit? For example: kg, gram, litre, or packet.",
            "Should that be in kg, grams, litres, or packets?",
            "Please specify the unit — kg, gram, litre, packet, or piece.",
        ]
        return options[min(attempt, len(options) - 1)]

    return "Could you clarify your order? Try something like '5 kg rice'."


# ── Confirmation handlers ─────────────────────────────────────────────────────

def _handle_confirmed(state: ConversationState) -> str:
    buf = state.slot_buffer

    if buf.is_order_confirm():
        return _save_order(state)

    if not buf.is_complete():
        state.force_transition(Phase.IDLE)
        buf.clear()
        return "Something went wrong. Let's start over — what would you like to add?"

    name          = buf.name
    quantity      = buf.quantity
    unit          = buf.unit
    is_accumulate = buf.is_accumulate
    is_update     = buf.is_update

    existing = next((i for i in state.items if i["name"] == name), None)

    if existing:
        if is_accumulate:
            existing["quantity"] = round(existing["quantity"] + quantity, 3)
            msg = (
                f"Done! Added {quantity} {unit} more of {name.title()}. "
                f"You now have {existing['quantity']} {existing['unit']} total."
            )
        else:
            existing["quantity"] = quantity
            existing["unit"]     = unit
            msg = f"Got it, updated {name.title()} to {quantity} {unit}."
    else:
        state.items.append({"name": name, "quantity": quantity, "unit": unit})
        msg = f"Perfect! {quantity} {unit} of {name.title()} added to your cart."

    buf.clear()
    state.transition(Phase.IDLE)
    return msg


def _handle_denied(state: ConversationState) -> str:
    buf = state.slot_buffer

    if buf.is_order_confirm():
        buf.clear()
        state.force_transition(Phase.IDLE)
        return "No problem, order not placed. Your cart is still saved. What would you like to do?"

    if state.phase == Phase.SLOT_FILLING:
        buf.clear()
        state.force_transition(Phase.IDLE)
        return "Sure, dropped that. What else would you like to add?"

    buf.clear()
    state.force_transition(Phase.IDLE)
    return "Alright, no changes made. What would you like to do?"


# ── Remove item ───────────────────────────────────────────────────────────────

def _handle_remove_item(raw: str, state: ConversationState) -> str:
    parsed = parse_item(raw)
    if not parsed.name:
        return "Which item would you like to remove?"
    before      = len(state.items)
    state.items = [i for i in state.items if i["name"] != parsed.name]
    if len(state.items) < before:
        return f"Removed {parsed.name.title()} from your cart."
    return f"I couldn't find {parsed.name} in your cart."


# ── Cart formatters ───────────────────────────────────────────────────────────

def _format_cart(state: ConversationState) -> str:
    if not state.items:
        return "Your cart is empty. You can start by saying something like 'add 5 kg rice'."
    lines = [f"Here's your cart ({len(state.items)} item(s)):"]
    for i, item in enumerate(state.items, 1):
        lines.append(f"  {i}. {item['name'].title()} — {item['quantity']} {item['unit']}")
    lines.append("\nWould you like to add more or confirm the order?")
    return "\n".join(lines)


def _format_cart_inline(state: ConversationState) -> str:
    return ", ".join(
        f"{i['quantity']} {i['unit']} {i['name']}" for i in state.items
    )


# ── Save order ────────────────────────────────────────────────────────────────

def _save_order(state: ConversationState) -> str:
    try:
        from shared.database.mongo_client import get_db
        db    = get_db()
        order = {
            "order_id":   str(uuid.uuid4()),
            "session_id": state.session_id,
            "items":      state.items.copy(),
            "created_at": datetime.utcnow(),
        }
        db.orders.insert_one(order)
        order_id = order["order_id"]
    except Exception as e:
        print(f"[Executor] DB save failed: {e}")
        order_id = str(uuid.uuid4()) + " (not persisted)"

    state.items = []
    state.slot_buffer.clear()
    state.force_transition(Phase.IDLE)

    return (
        f"Your order has been confirmed!\n"
        f"Order ID: {order_id}\n"
        f"Thank you! Is there anything else I can help you with?"
    )