# services/campaign_manager/retry_engine.py
# Consumes OutcomeClassifiedEvent and reschedules failed calls

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.events.event_bus import consume, publish, CallScheduledEvent
from shared.database.mongo_client import get_db

MAX_RETRY_ATTEMPTS = 3


def handle_retry(event_data: dict) -> None:
    call_id    = event_data.get("call_id")
    session_id = event_data.get("session_id")
    payload    = event_data.get("payload", {})
    
    retry_recommended = payload.get("retry_recommended", False)
    retry_delay_hours = payload.get("retry_delay_hours", 0)
    
    if not retry_recommended:
        print(f"[RetryEngine] Call {call_id}: No retry needed")
        return
    
    db = get_db()
    try:
        session_doc = db.sessions.find_one({"session_id": session_id})
        if not session_doc:
            print(f"[RetryEngine] Session not found: {session_id}")
            return
        
        retry_count = db.call_outcomes.count_documents({
            "session_id": session_id,
            "retry_recommended": True
        })
        
        if retry_count >= MAX_RETRY_ATTEMPTS:
            print(f"[RetryEngine] Max retries reached for {session_id}")
            return
        
        retry_time = datetime.utcnow() + timedelta(hours=retry_delay_hours)
        
        retry_doc = {
            "original_call_id": call_id,
            "session_id":       session_id,
            "retry_attempt":    retry_count + 1,
            "scheduled_time":   retry_time,
            "status":           "scheduled",
            "created_at":       datetime.utcnow(),
        }
        
        db.retry_queue.insert_one(retry_doc)
        
        print(f"[RetryEngine] Scheduled retry {retry_count + 1}/{MAX_RETRY_ATTEMPTS}")
        print(f"[RetryEngine] Retry time: {retry_time} ({retry_delay_hours}h from now)")
        
        publish(CallScheduledEvent(
            call_id=f"{call_id}-retry-{retry_count + 1}",
            session_id=session_id,
            payload={
                "is_retry":      True,
                "retry_attempt": retry_count + 1,
                "scheduled_for": retry_time.isoformat(),
            }
        ))
        
    except Exception as e:
        print(f"[RetryEngine] Error: {e}")


def start():
    print("[RetryEngine] Starting...")
    print("[RetryEngine] Listening for analytics.outcome_classified events")
    
    consume(
        consumer_group="campaign-manager-service",
        consumer_name="retry-engine-1",
        event_types=["analytics.outcome_classified"],
        handler=handle_retry,
    )


if __name__ == "__main__":
    start()