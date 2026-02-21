# shared/events/event_bus.py
# Redis Streams based event bus.
# Services publish events here. Other services consume them.
# No direct calls between services — everything goes through this.

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Callable, Optional
from dotenv import load_dotenv
import redis

load_dotenv()

# ── Redis connection ──────────────────────────────────────────────────────────

_redis_client: Optional[redis.Redis] = None

def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _redis_client = redis.from_url(url, decode_responses=True)
    return _redis_client


# ── Stream config ─────────────────────────────────────────────────────────────

STREAM_NAME   = "agent:events"
MAX_STREAM_LEN = 10_000  # cap to avoid unbounded memory growth


# ── Base event ────────────────────────────────────────────────────────────────

@dataclass
class BaseEvent:
    event_type:  str
    call_id:     str
    session_id:  str
    timestamp:   str = ""
    payload:     dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def serialize(self) -> str:
        return json.dumps(asdict(self))


# ── Event types ───────────────────────────────────────────────────────────────

def CallScheduledEvent(call_id, session_id, payload=None):
    return BaseEvent(event_type="call.scheduled", call_id=call_id, session_id=session_id, payload=payload or {})

def CallConnectedEvent(call_id, session_id, payload=None):
    return BaseEvent(event_type="call.connected", call_id=call_id, session_id=session_id, payload=payload or {})

def CallEndedEvent(call_id, session_id, payload=None):
    return BaseEvent(event_type="call.ended", call_id=call_id, session_id=session_id, payload=payload or {})

def AudioStreamReadyEvent(call_id, session_id, payload=None):
    return BaseEvent(event_type="audio.stream_ready", call_id=call_id, session_id=session_id, payload=payload or {})

def OrderIntentEvent(call_id, session_id, payload=None):
    return BaseEvent(event_type="order.intent_detected", call_id=call_id, session_id=session_id, payload=payload or {})

def OrderConfirmedEvent(call_id, session_id, payload=None):
    return BaseEvent(event_type="order.confirmed", call_id=call_id, session_id=session_id, payload=payload or {})

def OutcomeClassifiedEvent(call_id, session_id, payload=None):
    return BaseEvent(event_type="analytics.outcome_classified", call_id=call_id, session_id=session_id, payload=payload or {})

# ── Publisher ─────────────────────────────────────────────────────────────────

def publish(event: BaseEvent) -> str:
    """
    Publishes an event to the Redis Stream.
    Returns the message ID assigned by Redis.
    """
    r = get_redis()
    msg_id = r.xadd(
        STREAM_NAME,
        {"data": event.serialize()},
        maxlen=MAX_STREAM_LEN,
        approximate=True
    )
    print(f"[EventBus] Published: {event.event_type} | call={event.call_id} | id={msg_id}")
    return msg_id


# ── Consumer ──────────────────────────────────────────────────────────────────

def consume(
    consumer_group: str,
    consumer_name:  str,
    event_types:    list,
    handler:        Callable[[dict], None],
    block_ms:       int = 5000,
    run_once:       bool = False,
) -> None:
    """
    Blocking consumer. Runs in a loop processing events.
    Acknowledges each message after handler completes.
    Skips events not in event_types.

    Args:
        consumer_group: unique name for this service (e.g. "voice-agent-service")
        consumer_name:  unique name for this instance (e.g. "worker-1")
        event_types:    list of event_type strings to handle (others are skipped)
        handler:        function that receives event dict and processes it
        block_ms:       how long to wait for new messages before looping
        run_once:       if True, process pending messages and return (for testing)
    """
    r = get_redis()

    # Create consumer group if it doesn't exist
    try:
        r.xgroup_create(STREAM_NAME, consumer_group, id="0", mkstream=True)
        print(f"[EventBus] Created consumer group: {consumer_group}")
    except redis.exceptions.ResponseError:
        pass  # group already exists

    print(f"[EventBus] {consumer_name} listening for: {event_types}")

    while True:
        try:
            messages = r.xreadgroup(
                consumer_group,
                consumer_name,
                {STREAM_NAME: ">"},
                count=10,
                block=block_ms,
            )

            if not messages:
                if run_once:
                    break
                continue

            for stream, entries in messages:
                for msg_id, fields in entries:
                    try:
                        event_data = json.loads(fields["data"])
                        event_type = event_data.get("event_type")

                        # Skip events this consumer doesn't care about
                        if event_type not in event_types:
                            r.xack(STREAM_NAME, consumer_group, msg_id)
                            continue

                        print(f"[EventBus] Received: {event_type} | id={msg_id}")
                        handler(event_data)
                        r.xack(STREAM_NAME, consumer_group, msg_id)

                    except Exception as e:
                        print(f"[EventBus] Handler error: {e} | msg_id={msg_id}")
                        # Acknowledge anyway to avoid blocking the stream
                        r.xack(STREAM_NAME, consumer_group, msg_id)

            if run_once:
                break

        except KeyboardInterrupt:
            print(f"\n[EventBus] {consumer_name} shutting down.")
            break
        except Exception as e:
            print(f"[EventBus] Consumer error: {e}")
            if run_once:
                break

