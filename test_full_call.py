# test_full_call.py
# End-to-end test: Simulates a complete ration ordering call

import asyncio
import sys
import os

sys.path.insert(0, '.')
sys.path.insert(0, 'services/voice_agent')

from services.telephony.livekit_bridge.room_handler import RoomHandler
from services.voice_agent.conversation_controller import ConversationController


async def simulate_call():
    """
    Simulates a complete call flow.
    In production, this would be triggered by incoming phone call.
    """
    call_id = "test_call_001"
    session_id = "test_session_001"
    
    print("=" * 60)
    print("  STARTING TEST CALL")
    print("=" * 60)
    print()
    
    # Step 1: Create LiveKit room
    print("Step 1: Creating LiveKit room...")
    handler = RoomHandler(call_id, session_id)
    
    try:
        room_name = await handler.create_room()
        print(f"✓ Room created: {room_name}\n")
        
        # Step 2: Connect agent to room
        print("Step 2: Connecting agent...")
        room = await handler.connect_as_agent()
        print(f"✓ Agent connected\n")
        
        # Step 3: Start conversation controller
        print("Step 3: Starting conversation...")
        print("-" * 60)
        
        controller = ConversationController(call_id, session_id, room)
        
        # Run for 10 seconds (in production this runs until call ends)
        conversation_task = asyncio.create_task(controller.start())
        
        # Simulate waiting for call to complete
        await asyncio.sleep(10)
        
        # End the call
        controller.active = False
        
        try:
            await asyncio.wait_for(conversation_task, timeout=2)
        except asyncio.TimeoutError:
            pass
        
        print("-" * 60)
        print("\n✓ Conversation completed\n")
        
        # Step 4: Disconnect
        print("Step 4: Cleaning up...")
        await handler.disconnect()
        print("✓ Disconnected\n")
        
        print("=" * 60)
        print("  TEST CALL COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print()
        print("Note: In production, a real caller would join the room")
        print("and speak. The agent would transcribe their speech,")
        print("process it through the ordering logic, and respond.")
        print()
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(simulate_call())