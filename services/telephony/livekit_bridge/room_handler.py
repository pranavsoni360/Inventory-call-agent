# services/telephony/livekit_bridge/room_handler.py
# Creates and manages LiveKit rooms for calls.
# Launches ConversationController when a participant joins.

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "voice_agent"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "voice_agent" / "llm"))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env")

from livekit import rtc
from livekit.api import LiveKitAPI, AccessToken, VideoGrants
from shared.logging.logger import get_logger

logger = get_logger("room_handler")


class RoomHandler:
    def __init__(self):
        self.url    = os.getenv("LIVEKIT_URL")
        self.key    = os.getenv("LIVEKIT_API_KEY")
        self.secret = os.getenv("LIVEKIT_API_SECRET")

        if not all([self.url, self.key, self.secret]):
            raise ValueError("LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET must be set in .env")

    def generate_token(self, room_name: str, participant_name: str) -> str:
        """Generate a LiveKit access token for a participant."""
        token = AccessToken(self.key, self.secret)
        token.with_identity(participant_name)
        token.with_name(participant_name)
        token.with_grants(VideoGrants(room_join=True, room=room_name))
        return token.to_jwt()

    async def handle_room(self, room_name: str, session_id: str):
        """
        Connect to a LiveKit room as the agent and start the conversation.
        Called when an inbound call creates a new room.
        """
        room  = rtc.Room()
        token = self.generate_token(room_name, "ration-agent")

        logger.info(f"[RoomHandler] Connecting to room: {room_name}")

        @room.on("participant_connected")
        def on_participant(participant):
            logger.info(f"[RoomHandler] Participant joined: {participant.identity}")

        @room.on("disconnected")
        def on_disconnected(reason=None):
            logger.info(f"[RoomHandler] Room {room_name} disconnected: {reason}")

        await room.connect(self.url, token)
        logger.info(f"[RoomHandler] Agent connected to room: {room_name}")

        # Launch conversation pipeline
        from conversation_controller import ConversationController
        controller = ConversationController(room=room, session_id=session_id)
        await controller.start()

        # Keep alive until room disconnects
        while room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1)

        logger.info(f"[RoomHandler] Session {session_id} ended")


async def main():
    """Standalone test — connects to a room directly."""
    import uuid
    handler    = RoomHandler()
    room_name  = os.getenv("LIVEKIT_TEST_ROOM", "test-room")
    session_id = str(uuid.uuid4())
    await handler.handle_room(room_name, session_id)


if __name__ == "__main__":
    asyncio.run(main())
