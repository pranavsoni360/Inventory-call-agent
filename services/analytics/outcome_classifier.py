# services/analytics/outcome_classifier.py
# Consumes CallEndedEvent, classifies outcome, emits OutcomeClassifiedEvent

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.events.event_bus import consume, publish, OutcomeClassifiedEvent
from shared.database.mongo_client import get_db

# Retry rules based on call outcome
RETRY_RULES = {
    "completed":       {"retry": False, "delay_hours": 0},
    "silence_timeout": {"retry": True,  "delay_hours": 4},
    "duration_cap":    {"retry": False, "delay_hours": 0},
    "no_answer":       {"retry": True,  "delay_hours": 2},
    "call_failed":     {"retry": True,  "delay_hours": 1},
    "user_hung_up":    {"retry": True,  "delay_hours": 6},
}


def classify_and_emit(event_data: dict) -> None:
    call_id    = event_data.get("call_id")
    session_id = event_data.get("session_id")
    payload    = event_data.get("payload", {})
    outcome    = payload.get("outcome", "unknown")
    
    rule = RETRY_RULES.get(outcome, {"retry": False, "delay_hours": 0})
    
    print(f"[OutcomeClassifier] Call {call_id}: {outcome} → retry={rule['retry']}")
    
    db = get_db()
    classification = {
        "call_id":              call_id,
        "session_id":           session_id,
        "outcome":              outcome,
        "retry_recommended":    rule["retry"],
        "retry_delay_hours":    rule["delay_hours"],
        "turn_count":           payload.get("turn_count", 0),
        "items_count":          payload.get("items_count", 0),
        "classified_at":        event_data.get("timestamp"),
    }
    
    try:
        db.call_outcomes.insert_one(classification)
        print(f"[OutcomeClassifier] Saved classification to MongoDB")
    except Exception as e:
        print(f"[OutcomeClassifier] MongoDB error: {e}")
    
    publish(OutcomeClassifiedEvent(
        call_id=call_id,
        session_id=session_id,
        payload={
            "outcome":             outcome,
            "retry_recommended":   rule["retry"],
            "retry_delay_hours":   rule["delay_hours"],
            "turn_count":          payload.get("turn_count", 0),
        }
    ))


def start():
    print("[OutcomeClassifier] Starting...")
    print("[OutcomeClassifier] Listening for call.ended events")
    
    consume(
        consumer_group="analytics-service",
        consumer_name="outcome-classifier-1",
        event_types=["call.ended"],
        handler=classify_and_emit,
    )


if __name__ == "__main__":
    start()