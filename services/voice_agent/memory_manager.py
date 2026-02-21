# services/voice_agent/memory_manager.py
# Loads and saves ConversationState to MongoDB.
# In-process cache avoids redundant DB reads within the same session.

from datetime import datetime
from conversation_state import ConversationState, Phase, SlotBuffer


class MemoryManager:

    def __init__(self):
        # In-process cache: session_id -> ConversationState
        # Avoids hitting MongoDB on every single turn
        self._cache: dict = {}
        self._db = None

    def _get_db(self):
        """
        Lazy DB connection — only connects when first needed.
        This way if MongoDB is not running, the agent still starts.
        """
        if self._db is None:
            try:
                from shared.database.mongo_client import get_db
                self._db = get_db()
            except Exception as e:
                print(f"[MemoryManager] WARNING: MongoDB unavailable: {e}")
                print("[MemoryManager] Running in memory-only mode.")
                self._db = False  # False = tried and failed, don't retry
        return self._db if self._db is not False else None

    # ── Session load ──────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> ConversationState:
        """
        Returns ConversationState for this session.
        Checks cache first, then MongoDB, then creates fresh state.
        """
        # 1. Return from cache if available
        if session_id in self._cache:
            return self._cache[session_id]

        # 2. Try loading from MongoDB
        db = self._get_db()
        if db is not None:
            try:
                doc = db.sessions.find_one({"session_id": session_id})
                if doc:
                    state = ConversationState.from_mongo_doc(doc)
                    self._cache[session_id] = state
                    return state
            except Exception as e:
                print(f"[MemoryManager] WARNING: Could not load session: {e}")

        # 3. Fresh state
        state = ConversationState(session_id=session_id)
        self._cache[session_id] = state
        return state

    # ── Session save ──────────────────────────────────────────────────────────

    def save_session(self, state: ConversationState) -> None:
        """
        Saves ConversationState to MongoDB.
        Always updates cache regardless of DB success.
        """
        # Always update cache
        self._cache[state.session_id] = state

        # Try persisting to MongoDB
        db = self._get_db()
        if db is not None:
            try:
                doc = state.to_mongo_doc()
                doc["updated_at"] = datetime.utcnow()
                db.sessions.update_one(
                    {"session_id": state.session_id},
                    {"$set": doc},
                    upsert=True
                )
            except Exception as e:
                print(f"[MemoryManager] WARNING: Could not save session: {e}")

    # ── History ───────────────────────────────────────────────────────────────

    def add_history(self, state: ConversationState, speaker: str, text: str) -> None:
        """
        Appends a turn to conversation history.
        Stored inside ConversationState — persisted on next save_session() call.
        """
        state.history.append({
            "speaker": speaker,
            "text":    text,
            "ts":      datetime.utcnow().isoformat()
        })