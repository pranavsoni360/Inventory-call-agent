# services/api/main.py
# REST API for the ration ordering agent.
# Exposes endpoints for frontend dashboard and external integrations.

import sys
import os
from pathlib import Path

# Path setup
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "voice_agent"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "voice_agent" / "llm"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

from memory_manager import MemoryManager
from decision_engine import decide
from action_executor import execute
from conversation_state import ConversationState

app = FastAPI(
    title="Ration Ordering Agent API",
    description="REST API for the AI calling agent",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

memory = MemoryManager()


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    session_id: str
    response: str
    phase: str
    cart: list
    turn_count: int

class SessionResponse(BaseModel):
    session_id: str
    phase: str
    cart: list
    turn_count: int
    llm_calls: int
    history: list


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "ration-ordering-agent", "version": "1.0.0"}


@app.get("/health")
def health():
    checks = {}

    # MongoDB
    try:
        from shared.database.mongo_client import get_db
        db = get_db()
        db.command("ping")
        checks["mongodb"] = "ok"
    except Exception as e:
        checks["mongodb"] = f"error: {e}"

    # Redis
    try:
        import redis as redis_lib
        from dotenv import load_dotenv
        import os
        r = redis_lib.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Groq
    try:
        from groq import Groq
        checks["groq"] = "configured" if os.getenv("GROQ_API_KEY") else "missing key"
    except Exception:
        checks["groq"] = "not installed"

    all_ok = all(v == "ok" or v == "configured" for v in checks.values())
    return {"status": "healthy" if all_ok else "degraded", "checks": checks}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Send a message to the agent and get a response.
    Creates a new session if session_id doesn't exist.
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    state = memory.get_session(req.session_id)

    intent_result = decide(req.message, state)
    response      = execute(intent_result, state)
    memory.save_session(state)

    if response == "__EXIT__":
        response = "Thank you for your order. Goodbye!"

    return ChatResponse(
        session_id=req.session_id,
        response=response,
        phase=state.phase.value,
        cart=state.items,
        turn_count=state.turn_count,
    )


@app.get("/session/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    """Get current session state."""
    state = memory.get_session(session_id)
    return SessionResponse(
        session_id=session_id,
        phase=state.phase.value,
        cart=state.items,
        turn_count=state.turn_count,
        llm_calls=state.llm_calls,
        history=state.history[-20:],  # last 20 turns only
    )


@app.delete("/session/{session_id}")
def reset_session(session_id: str):
    """Reset a session to fresh state."""
    state = ConversationState(session_id=session_id)
    memory._cache[session_id] = state
    memory.save_session(state)
    return {"status": "reset", "session_id": session_id}


@app.get("/orders")
def get_orders(limit: int = 20):
    """Get recent confirmed orders from MongoDB."""
    try:
        from shared.database.mongo_client import get_db
        db     = get_db()
        orders = list(
            db.orders.find({}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        # Convert datetime to string for JSON
        for o in orders:
            if "created_at" in o:
                o["created_at"] = o["created_at"].isoformat()
        return {"orders": orders, "count": len(orders)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    """Get a specific order by ID."""
    try:
        from shared.database.mongo_client import get_db
        db    = get_db()
        order = db.orders.find_one({"order_id": order_id}, {"_id": 0})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if "created_at" in order:
            order["created_at"] = order["created_at"].isoformat()
        return order
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
