# services/api/main.py
# REST API + WebSocket for the ration ordering agent.

import sys
import os
import base64
import asyncio
import io
import wave
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

_root = Path(__file__).resolve().parents[2]
_va   = _root / "services" / "voice_agent"
_llm  = _va / "llm"
for p in [str(_root), str(_va), str(_llm)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=_root / ".env")

from memory_manager import MemoryManager
from decision_engine import decide
from action_executor import execute
from conversation_state import ConversationState, Phase

app = FastAPI(title="Ration Ordering Agent API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

memory   = MemoryManager()
executor = ThreadPoolExecutor(max_workers=4)


# ── Audio helpers ─────────────────────────────────────────────────────────────

def webm_to_wav_python(webm_bytes: bytes) -> bytes:
    # Try pydub
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(io.BytesIO(webm_bytes), format="webm")
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        buf = io.BytesIO()
        audio.export(buf, format="wav")
        return buf.getvalue()
    except Exception:
        pass

    # Try ffmpeg subprocess
    try:
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(webm_bytes)
            inp = f.name
        out = inp.replace(".webm", ".wav")
        r   = subprocess.run(
            ["ffmpeg", "-y", "-i", inp, "-ar", "16000", "-ac", "1", "-f", "wav", out],
            capture_output=True, timeout=10
        )
        if r.returncode == 0:
            with open(out, "rb") as f:
                wav = f.read()
            os.unlink(inp)
            os.unlink(out)
            return wav
        os.unlink(inp)
    except Exception:
        pass

    return webm_bytes


def run_sync(fn, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(executor, fn, *args)


# ── Frontend ──────────────────────────────────────────────────────────────────

@app.get("/voice-test", response_class=HTMLResponse)
def voice_test():
    p = _root / "frontend" / "voice_test" / "index.html"
    return HTMLResponse(content=p.read_text(encoding="utf-8"))


# ── REST models ───────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "service": "ration-ordering-agent", "version": "1.0.0"}


@app.get("/health")
def health():
    checks = {}
    try:
        from shared.database.mongo_client import get_db
        get_db().command("ping")
        checks["mongodb"] = "ok"
    except Exception as e:
        checks["mongodb"] = f"error: {e}"

    try:
        import redis as r
        r.from_url(os.getenv("REDIS_URL", "redis://localhost:6379")).ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    checks["groq"]   = "ok" if os.getenv("GROQ_API_KEY")   else "missing"
    checks["sarvam"] = "ok" if os.getenv("SARVAM_API_KEY") else "missing"

    try:
        import subprocess
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=3)
        checks["ffmpeg"] = "ok"
    except Exception:
        checks["ffmpeg"] = "not found (using pydub fallback)"

    return {"status": "healthy", "checks": checks}


@app.post("/chat")
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")
    state         = memory.get_session(req.session_id)
    intent_result = decide(req.message, state)
    response      = execute(intent_result, state)
    memory.save_session(state)
    if response == "__EXIT__":
        response = "Thank you for your order. Goodbye!"
    return {"session_id": req.session_id, "response": response,
            "phase": state.phase.value, "cart": state.items,
            "turn_count": state.turn_count}


@app.get("/session/{session_id}")
def get_session(session_id: str):
    state = memory.get_session(session_id)
    return {"session_id": session_id, "phase": state.phase.value,
            "cart": state.items, "turn_count": state.turn_count,
            "llm_calls": state.llm_calls, "history": state.history[-20:]}


@app.delete("/session/{session_id}")
def reset_session(session_id: str):
    state = ConversationState(session_id=session_id)
    memory._cache[session_id] = state
    memory.save_session(state)
    return {"status": "reset", "session_id": session_id}


@app.get("/orders")
def get_orders(limit: int = 20):
    try:
        from shared.database.mongo_client import get_db
        orders = list(get_db().orders.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))
        for o in orders:
            if "created_at" in o:
                o["created_at"] = o["created_at"].isoformat()
        return {"orders": orders, "count": len(orders)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── WebSocket voice endpoint ──────────────────────────────────────────────────

@app.websocket("/voice/{session_id}")
async def voice_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    print(f"[Voice] Connected: {session_id}")

    from tts.sarvam_tts import SarvamTTS
    from stt.sarvam_stt import SarvamSTT
    from action_executor import _handle_add_item

    tts   = SarvamTTS()
    stt   = SarvamSTT()
    state = memory.get_session(session_id)
    state.slot_buffer.clear()
    state.force_transition(Phase.IDLE)

    async def send_response(text: str):
        audio = await run_sync(tts.synthesize, text, None)
        audio_b64 = base64.b64encode(audio).decode("utf-8") if audio else ""
        await websocket.send_json({
            "type":      "agent_response",
            "text":      text,
            "audio_b64": audio_b64,
            "phase":     state.phase.value,
            "cart":      state.items,
        })
        await asyncio.sleep(0.3)

    async def handle_followup():
        """Send queued follow-up item if any (from multi-item utterances)."""
        followup = None
        for h in state.history:
            if h.get("speaker") == "__followup__":
                followup = h
                break
        if followup:
            state.history.remove(followup)
            next_raw          = followup["text"]
            followup_response = _handle_add_item(next_raw, state)
            memory.add_history(state, "agent", followup_response)
            print(f"[Voice] Followup: {followup_response}")
            await asyncio.sleep(0.8)
            await send_response(followup_response)

    # Opening greeting
    opening = "Hello! This is your monthly ration reminder. What items would you like to order this month?"
    await send_response(opening)

    try:
        while True:
            data = await websocket.receive_json()

            # ── Audio message ─────────────────────────────────────────────────
            if data.get("type") == "audio":
                raw        = base64.b64decode(data["audio_b64"])
                wav        = await run_sync(webm_to_wav_python, raw)
                transcript = await run_sync(stt.transcribe, wav)

                if not transcript or len(transcript.strip()) < 2:
                    await websocket.send_json({
                        "type": "info", "message": "Didn't catch that — please try again."
                    })
                    continue

                print(f"[Voice] User: {transcript}")
                await websocket.send_json({"type": "transcript", "text": transcript})

                memory.add_history(state, "user", transcript)
                intent   = decide(transcript, state)
                response = execute(intent, state)
                memory.save_session(state)

                if response == "__EXIT__":
                    await send_response("Thank you for your order. Goodbye!")
                    break

                memory.add_history(state, "agent", response)
                print(f"[Voice] Agent: {response}")
                await send_response(response)
                await handle_followup()

            # ── Text message ──────────────────────────────────────────────────
            elif data.get("type") == "text":
                message = data.get("message", "").strip()
                if not message:
                    continue

                memory.add_history(state, "user", message)
                intent   = decide(message, state)
                response = execute(intent, state)
                memory.save_session(state)

                if response == "__EXIT__":
                    response = "Thank you for your order. Goodbye!"

                memory.add_history(state, "agent", response)
                print(f"[Voice] Text — Agent: {response}")
                await send_response(response)
                await handle_followup()

    except WebSocketDisconnect:
        print(f"[Voice] Disconnected: {session_id}")
    except Exception as e:
        print(f"[Voice] Error: {type(e).__name__}: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
