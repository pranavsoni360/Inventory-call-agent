#services/telephony/livekit_bridge/call_server.py
import sys
import os
import asyncio
import uuid
from pathlib import Path

_root    = Path(__file__).resolve().parents[3]
_va      = _root / "services" / "voice_agent"
_llm     = _va / "llm"
_bridge  = Path(__file__).resolve().parent

for p in [str(_root), str(_va), str(_llm), str(_bridge)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(dotenv_path=_root / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared.logging.logger import get_logger
from room_handler import RoomHandler
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "voice_agent"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "voice_agent" / "llm"))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared.logging.logger import get_logger
from room_handler import RoomHandler

logger = get_logger("call_server")

app = FastAPI(title="Call Server", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

handler = RoomHandler()
active_rooms: dict = {}


class CallRequest(BaseModel):
    caller_number: str = "unknown"
    room_name:     str = ""
    session_id:    str = ""


@app.get("/")
def root():
    return {"status": "ok", "service": "call-server", "active_calls": len(active_rooms)}


@app.post("/call/inbound")
async def inbound_call(req: CallRequest):
    """
    Called by your SIP provider when a new call comes in.
    Spins up a LiveKit room and launches the agent.
    """
    session_id = req.session_id or str(uuid.uuid4())
    room_name  = req.room_name  or f"call-{session_id[:8]}"

    logger.info(f"[CallServer] Inbound call from {req.caller_number} → room {room_name}")

    # Generate token for the caller (frontend/SIP bridge uses this to join)
    caller_token = handler.generate_token(room_name, req.caller_number)

    # Launch agent in background
    task = asyncio.create_task(handler.handle_room(room_name, session_id))
    active_rooms[session_id] = {"task": task, "room": room_name, "caller": req.caller_number}

    return {
        "session_id":   session_id,
        "room_name":    room_name,
        "caller_token": caller_token,
        "livekit_url":  os.getenv("LIVEKIT_URL"),
    }


@app.get("/call/token")
def get_token(room_name: str, participant: str = "user"):
    """Generate a join token for any participant — useful for browser testing."""
    token = handler.generate_token(room_name, participant)
    return {"token": token, "room_name": room_name, "livekit_url": os.getenv("LIVEKIT_URL")}


@app.get("/calls/active")
def active_calls():
    return {
        "count": len(active_rooms),
        "rooms": [
            {"session_id": sid, "room": info["room"], "caller": info["caller"]}
            for sid, info in active_rooms.items()
        ]
    }


@app.delete("/call/{session_id}")
async def end_call(session_id: str):
    if session_id in active_rooms:
        active_rooms[session_id]["task"].cancel()
        del active_rooms[session_id]
        return {"status": "ended", "session_id": session_id}
    return {"status": "not_found"}


