# conversation_state.py
# Formal FSM for conversation state.
# This is the ONLY object passed between modules.
# All mutations go through ConversationState methods only.

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


# ── Phases ────────────────────────────────────────────────────────────────────

class Phase(str, Enum):
    IDLE             = "IDLE"
    SLOT_FILLING     = "SLOT_FILLING"
    AWAITING_CONFIRM = "AWAITING_CONFIRM"
    CONFIRMED        = "CONFIRMED"


# Legal transitions — anything not listed here is forbidden
_ALLOWED = {
    Phase.IDLE:             {Phase.SLOT_FILLING, Phase.IDLE},
    Phase.SLOT_FILLING:     {Phase.SLOT_FILLING, Phase.AWAITING_CONFIRM, Phase.IDLE},
    Phase.AWAITING_CONFIRM: {Phase.CONFIRMED, Phase.SLOT_FILLING, Phase.IDLE},
    Phase.CONFIRMED:        {Phase.IDLE},
}


class InvalidTransitionError(Exception):
    pass


# ── Slot buffer ───────────────────────────────────────────────────────────────

@dataclass
class SlotBuffer:
    """
    Holds partial item data while slots are being filled.
    Cleared immediately after confirmation or cancellation.
    """
    name:          Optional[str]   = None
    quantity:      Optional[float] = None
    unit:          Optional[str]   = None
    is_accumulate: bool            = False
    is_update:     bool            = False

    def is_complete(self) -> bool:
        return (
            self.name     is not None
            and self.quantity is not None
            and self.unit     is not None
        )

    def missing_slots(self) -> list:
        missing = []
        if self.name     is None: missing.append("name")
        if self.quantity is None: missing.append("quantity")
        if self.unit     is None: missing.append("unit")
        return missing

    def next_missing(self) -> Optional[str]:
        m = self.missing_slots()
        return m[0] if m else None

    def is_order_confirm(self) -> bool:
        """True when awaiting yes/no for full order, not a single item."""
        return self.name == "__ORDER_CONFIRM__"

    def merge_from_parse(self, parsed) -> None:
        """
        Merges a ParseResult into this buffer.
        Only fills slots that are currently None — never overwrites.
        """
        if parsed.name     is not None and self.name     is None:
            self.name = parsed.name
        if parsed.quantity is not None and self.quantity is None:
            self.quantity = parsed.quantity
        if parsed.unit     is not None and self.unit     is None:
            self.unit = parsed.unit
        self.is_accumulate = self.is_accumulate or parsed.is_accumulate
        self.is_update     = self.is_update     or parsed.is_update

    def to_item_dict(self) -> dict:
        return {
            "name":     self.name,
            "quantity": self.quantity,
            "unit":     self.unit,
        }

    def clear(self) -> None:
        self.name          = None
        self.quantity      = None
        self.unit          = None
        self.is_accumulate = False
        self.is_update     = False

    def __repr__(self):
        return (
            f"SlotBuffer(name={self.name!r}, qty={self.quantity}, "
            f"unit={self.unit!r}, accum={self.is_accumulate}, "
            f"update={self.is_update})"
        )


# ── Conversation state ────────────────────────────────────────────────────────

@dataclass
class ConversationState:
    """
    Complete state for one call session.
    Loaded from MongoDB at session start, saved after every turn.
    """
    session_id:  str
    phase:       Phase      = Phase.IDLE
    slot_buffer: SlotBuffer = field(default_factory=SlotBuffer)
    items:       list       = field(default_factory=list)
    history:     list       = field(default_factory=list)
    llm_calls:   int        = 0
    turn_count:  int        = 0

    # ── Phase transitions ─────────────────────────────────────────────────────

    def transition(self, target: Phase) -> None:
        """
        Enforced transition. Raises InvalidTransitionError for illegal moves.
        Use this in normal execution flow.
        """
        allowed = _ALLOWED.get(self.phase, set())
        if target not in allowed:
            raise InvalidTransitionError(
                f"Illegal transition: {self.phase.value} -> {target.value}"
            )
        self.phase = target

    def force_transition(self, target: Phase) -> None:
        """
        Bypasses validation. Use ONLY for error recovery.
        Never use this in normal flow.
        """
        self.phase = target

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_mongo_doc(self) -> dict:
        return {
            "session_id": self.session_id,
            "phase":      self.phase.value,
            "slot_buffer": {
                "name":          self.slot_buffer.name,
                "quantity":      self.slot_buffer.quantity,
                "unit":          self.slot_buffer.unit,
                "is_accumulate": self.slot_buffer.is_accumulate,
                "is_update":     self.slot_buffer.is_update,
            },
            "items":      self.items,
            "history":    self.history,
            "llm_calls":  self.llm_calls,
            "turn_count": self.turn_count,
        }

    @classmethod
    def from_mongo_doc(cls, doc: dict) -> "ConversationState":
        state = cls(session_id=doc["session_id"])
        state.phase      = Phase(doc.get("phase", "IDLE"))
        state.items      = doc.get("items", [])
        state.history    = doc.get("history", [])
        state.llm_calls  = doc.get("llm_calls", 0)
        state.turn_count = doc.get("turn_count", 0)
        buf = doc.get("slot_buffer", {})
        state.slot_buffer = SlotBuffer(
            name          = buf.get("name"),
            quantity      = buf.get("quantity"),
            unit          = buf.get("unit"),
            is_accumulate = buf.get("is_accumulate", False),
            is_update     = buf.get("is_update", False),
        )
        return state

    def __repr__(self):
        return (
            f"ConversationState(session={self.session_id!r}, "
            f"phase={self.phase.value}, "
            f"items={len(self.items)}, "
            f"buffer={self.slot_buffer})"
        )
