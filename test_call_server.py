import sys
sys.path.insert(0, 'services/voice_agent')
sys.path.insert(0, 'services/voice_agent/llm')
sys.path.insert(0, 'services/telephony/livekit_bridge')
from room_handler import RoomHandler
from call_server import app
print('call_server OK')