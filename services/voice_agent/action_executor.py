# services/voice_agent/action_executor.py
# The ONLY place state is mutated.
# Receives IntentResult + ConversationState, returns response string.
import re
from conversation_state import ConversationState, Phase
from item_parser import parse_item
import os
import uuid
import random
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import random

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

from conversation_state import ConversationState, Phase, SlotBuffer
from item_parser import parse_item
from constants import MAX_CART_ITEMS


# ── Groq conversational response (used sparingly) ─────────────────────────────

def _groq_respond(user_text: str, state, context: str = "") -> str:
    cart_summary = ""
    if state:
        cart_summary = ", ".join(
            f"{i['quantity']} {i['unit']} {i['name']}" for i in state.items
        ) or "empty"

    system = """You are a friendly ration ordering assistant on a phone call.
Help customers place their monthly grocery orders.
Keep responses SHORT (1-2 sentences max), warm, and natural.
Respond in the same language the customer used — Hindi or English.
Never make up order details. Never confirm things the customer didn't say."""

    user_prompt = f"""{f'Customer said: "{user_text}"' if user_text else ''}
{f'Current cart: {cart_summary}' if cart_summary else ''}
{f'Context: {context}' if context else ''}
Respond naturally in 1-2 sentences."""

    try:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=80,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return context if context else "What items would you like to order today?"

# ── Main entry point ──────────────────────────────────────────────────────────

def execute(intent_result, state: ConversationState) -> str:
    intent = intent_result.intent
    raw    = intent_result.raw_text

    state.turn_count += 1

    if intent == "user_confirmed":
        return _handle_confirmed(state)

    if intent == "user_denied":
        return _handle_denied(state)

    if intent == "confirmation_unclear":
        buf = state.slot_buffer
        if buf.is_order_confirm():
            return "Please say yes to confirm your order, or no to cancel."
        return f"Please say yes or no — should I add {buf.quantity} {buf.unit} of {buf.name.title()}?"

    if intent == "slot_response":
        return _handle_slot_response(raw, state)

    if intent == "show_cart":
        return _format_cart(state)

    if intent == "confirm_order":
        if not state.items:
            return "Your cart is empty. Please add some items first."
        state.slot_buffer.clear()
        state.slot_buffer.name = "__ORDER_CONFIRM__"
        state.force_transition(Phase.AWAITING_CONFIRM)
        return (
            f"You want to place this order? "
            f"{_format_cart_inline(state)}. "
            f"Say yes to confirm or no to cancel."
        )

    if intent == "greeting":
        greetings = [
            "Hello! What items would you like to order this month?",
            "Hi there! What can I add to your cart today?",
            "Hey! Ready to place your ration order? What do you need?",
        ]
        return random.choice(greetings)

    if intent == "acknowledgement":
        cart_count = len(state.items)
        if cart_count == 0:
            options = [
                "Great! What would you like to add to your cart?",
                "Sure! Go ahead and tell me what items you need.",
                "Alright! What's first on your list?",
            ]
        else:
            options = [
                f"You have {cart_count} item(s) so far. Want to add more or confirm your order?",
                f"Got it! Should I add anything else, or are you ready to confirm?",
                f"Sure! Your cart has {cart_count} item(s). Continue adding or place the order?",
            ]
        return random.choice(options)

    if intent == "exit":
        return "__EXIT__"

    if intent == "clarify":
        # Use Groq only for clarify — it's genuinely ambiguous
        return _groq_respond(
            raw, state,
            "You didn't understand. Politely ask them to clarify or suggest 'add 5 kg rice'."
        )

    if intent == "add_item":
        return _handle_add_item(raw, state)

    if intent == "update_item":
        return _handle_add_item(raw, state, is_update=True)

    if intent == "remove_item":
        return _handle_remove_item(raw, state)

    return "Sorry, could you repeat that?"


# ── Add / update item ─────────────────────────────────────────────────────────

def _handle_add_item(raw: str, state: ConversationState,
                     is_update: bool = False) -> str:
    if len(state.items) >= MAX_CART_ITEMS:
        return f"Your cart is full ({MAX_CART_ITEMS} items maximum)."

    # Split on "and", commas, "aur", "और" — handles Hindi multi-item utterances
    parts = [p.strip() for p in re.split(r'\band\b|,|aur|और', raw) if p.strip()]

    if len(parts) > 1 and not state.slot_buffer.name:
        pending_entry = next(
            (h for h in state.history if h.get("speaker") == "__pending__"),
            None
        )
        if pending_entry:
            pending_entry["items"] = parts[1:] + pending_entry.get("items", [])
        else:
            state.history.append({"speaker": "__pending__", "items": parts[1:]})
        raw = parts[0]

    parsed = parse_item(raw)

    # LLM fallback if parser got nothing on complex Hindi/mixed input
    if not parsed.has_any() and len(raw.split()) >= 1:
        from item_parser import extract_items_with_llm
        llm_items = extract_items_with_llm(raw)
        if llm_items:
            first = llm_items[0]
            rest  = llm_items[1:]
            if rest:
                rest_texts = [
                    f"{i.get('quantity') or ''} {i.get('unit') or ''} {i['name']}".strip()
                    for i in rest
                ]
                pending_entry = next(
                    (h for h in state.history if h.get("speaker") == "__pending__"),
                    None
                )
                if pending_entry:
                    pending_entry["items"] = rest_texts + pending_entry.get("items", [])
                else:
                    state.history.append({"speaker": "__pending__", "items": rest_texts})
            # Apply first item to slot buffer
            if first.get("name")     and not state.slot_buffer.name:
                state.slot_buffer.name     = first["name"]
            if first.get("quantity") and not state.slot_buffer.quantity:
                state.slot_buffer.quantity = float(first["quantity"])
            if first.get("unit")     and not state.slot_buffer.unit:
                state.slot_buffer.unit     = first["unit"]
            # Re-parse to get confidence set correctly
            parsed = parse_item(
                f"{first.get('quantity') or ''} {first.get('unit') or ''} {first.get('name') or ''}".strip()
            )

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
    slot = buf.next_missing()
    name = buf.name.title() if buf.name else None
    qty  = buf.quantity
    unit = buf.unit

    if slot == "name":
        options = [
            "Which item would you like to add? For example rice, dal, sugar, or oil.",
            "What grocery item did you want? I can add rice, dal, wheat, sugar and more.",
            "Could you tell me the item name?",
        ]
        return random.choice(options)

    if slot == "quantity":
        options = [
            f"How much {name} would you like? For example 2 kg or 500 grams.",
            f"What quantity of {name} do you need?",
            f"How many kg or packets of {name}?",
        ]
        return random.choice(options)

    if slot == "unit":
        options = [
            f"Should that be in kg, grams, litres, or packets?",
            f"What unit for {name} — kg, gram, litre, or packet?",
        ]
        return random.choice(options)

    return "Could you clarify? Try something like '5 kg rice'."



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
            msg = f"Updated {name.title()} to {quantity} {unit}."
    else:
        state.items.append({"name": name, "quantity": quantity, "unit": unit})
        msg = f"Perfect! {quantity} {unit} of {name.title()} added to your cart."

    buf.clear()
    state.transition(Phase.IDLE)

    # Don't inline — store next item to process on next agent turn
    pending_entry = None
    for h in state.history:
        if h.get("speaker") == "__pending__" and h.get("items"):
            pending_entry = h
            break

    if pending_entry:
        next_raw = pending_entry["items"].pop(0)
        if not pending_entry["items"]:
            state.history.remove(pending_entry)
        # Tag it so main.py sends it as a follow-up after a pause
        state.history.append({"speaker": "__followup__", "text": next_raw})

    return msg


def _handle_denied(state: ConversationState) -> str:
    buf = state.slot_buffer

    if buf.is_order_confirm():
        buf.clear()
        state.force_transition(Phase.IDLE)
        return "No problem, order not placed. Your cart items are still saved. What would you like to do?"

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
        return "Your cart is empty. Try saying 'add 5 kg rice' to get started."
    lines = [f"Here's your cart ({len(state.items)} item(s)):"]
    for i, item in enumerate(state.items, 1):
        lines.append(f"  {i}. {item['name'].title()} — {item['quantity']} {item['unit']}")
    lines.append("Would you like to add more or confirm the order?")
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
        f"Your order has been confirmed! "
        f"Order ID: {order_id}. "
        f"Thank you! Is there anything else I can help you with?"
    )