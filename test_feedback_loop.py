# test_feedback_loop.py
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, '.')

from shared.events.event_bus import publish, CallEndedEvent
from shared.database.mongo_client import get_db


async def test_feedback_loop():
    print("=" * 60)
    print("  TESTING FEEDBACK LOOP")
    print("=" * 60)
    print()
    
    db = get_db()
    db.call_outcomes.delete_many({})
    db.retry_queue.delete_many({"session_id": {"$regex": "^test_"}})
    
    print("Test 1: Successful call (should NOT retry)")
    print("-" * 60)
    
    publish(CallEndedEvent(
        call_id="test_success_001",
        session_id="test_session_success",
        payload={
            "outcome": "completed",
            "turn_count": 5,
            "items_count": 3,
        }
    ))
    
    await asyncio.sleep(2)
    
    outcome = db.call_outcomes.find_one({"call_id": "test_success_001"})
    retry = db.retry_queue.find_one({"session_id": "test_session_success"})
    
    print(f"Outcome saved: {outcome is not None}")
    print(f"Retry scheduled: {retry is not None}")
    assert outcome is not None, "Outcome should be saved"
    assert retry is None, "Should NOT schedule retry for successful call"
    print(f"✓ Test 1 passed\n")
    
    print("Test 2: Silence timeout (should retry in 4 hours)")
    print("-" * 60)
    
    db.sessions.update_one(
        {"session_id": "test_session_timeout"},
        {"$set": {"session_id": "test_session_timeout", "created_at": datetime.utcnow()}},
        upsert=True
    )
    
    publish(CallEndedEvent(
        call_id="test_timeout_001",
        session_id="test_session_timeout",
        payload={
            "outcome": "silence_timeout",
            "turn_count": 2,
            "items_count": 0,
        }
    ))
    
    await asyncio.sleep(2)
    
    outcome = db.call_outcomes.find_one({"call_id": "test_timeout_001"})
    retry = db.retry_queue.find_one({"session_id": "test_session_timeout"})
    
    print(f"Outcome saved: {outcome is not None}")
    print(f"Retry scheduled: {retry is not None}")
    if retry:
        print(f"Retry attempt: {retry['retry_attempt']}")
        print(f"Scheduled for: {retry['scheduled_time']}")
    assert retry is not None, "Should schedule retry"
    assert retry['retry_attempt'] >= 1, "Should be scheduled for retry"
    print(f"✓ Test 2 passed\n")
    
    print("=" * 60)
    print("  ALL TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_feedback_loop())