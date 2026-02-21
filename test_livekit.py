# test_livekit.py
# Quick test to verify LiveKit connection works

import asyncio
import sys
import os

sys.path.insert(0, '.')

from services.telephony.livekit_bridge.room_handler import RoomHandler


async def test_livekit():
    print("Testing LiveKit connection...")
    
    # Create a test room
    handler = RoomHandler(call_id="test_001", session_id="test_session")
    
    try:
        # Create room
        room_name = await handler.create_room()
        print(f"✓ Room created: {room_name}")
        
        # Connect as agent
        room = await handler.connect_as_agent()
        print(f"✓ Agent connected to room")
        
        # Generate a token for a caller
        caller_token = handler.generate_token("test-caller")
        print(f"✓ Caller token generated: {caller_token[:20]}...")
        
        # Wait a bit
        await asyncio.sleep(2)
        
        # Disconnect
        await handler.disconnect()
        print("✓ Disconnected successfully")
        
        print("\n✅ LiveKit integration working!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_livekit())