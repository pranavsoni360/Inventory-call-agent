# services/voice_agent/conversation_controller.py
# Orchestrates the full pipeline: Audio → STT → Agent → TTS → Audio

import asyncio
import os
import sys
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
sys.path.insert(0, str(Path(__file__).resolve().parents[0] / "llm"))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

from livekit import rtc
from shared.logging.logger import get_logger
from memory_manager import MemoryManager
from decision_engine import decide
from action_executor import execute
from conversation_state import ConversationState
from stt.sarvam_stt import SarvamSTT
from tts.sarvam_tts import SarvamTTS

logger = get_logger("conversation_controller")


class ConversationController:
    def __init__(self, room: rtc.Room, session_id: str):
        self.room       = room
        self.session_id = session_id
        self.memory     = MemoryManager()
        self.state      = ConversationState(session_id=session_id)
        self.memory._cache[session_id] = self.state
        self.stt        = SarvamSTT()
        self.tts        = SarvamTTS()
        self._audio_buf = bytearray()
        self._silence   = 0
        self._speaking  = False
        self._agent_speaking = False  # prevent listening while agent speaks
        self.SAMPLE_RATE    = 16000
        self.CHANNELS       = 1
        self.SILENCE_FRAMES = 25    # ~1.25s silence = end of utterance
        self.MIN_SPEECH_MS  = 400   # ignore clips shorter than this
        self.VAD_THRESHOLD  = 150   # energy threshold — lower = more sensitive
        self._source        = None

    # ── Start ─────────────────────────────────────────────────────────────────

    async def start(self):
        logger.info(f"[Controller] Session {self.session_id} started")

        # Set up audio output
        self._source = rtc.AudioSource(self.SAMPLE_RATE, self.CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("agent-voice", self._source)
        await self.room.local_participant.publish_track(track)

        # Wire up room events
        @self.room.on("track_subscribed")
        def on_track(track, pub, participant):
            logger.info(f"[Controller] Track subscribed: {track.kind} from {participant.identity}")
            asyncio.ensure_future(self._subscribe(track))

        @self.room.on("participant_connected")
        def on_participant(participant):
            logger.info(f"[Controller] Participant connected: {participant.identity}")

        @self.room.on("track_published")
        def on_published(pub, participant):
            logger.info(f"[Controller] Track published by {participant.identity}")
            if pub.track:
                asyncio.ensure_future(self._subscribe(pub.track))

        # Subscribe to any already-present tracks
        for participant in self.room.remote_participants.values():
            for pub in participant.track_publications.values():
                if pub.track:
                    asyncio.ensure_future(self._subscribe(pub.track))

        # Greet caller
        await self._speak(
            "Hello! This is your monthly ration reminder. "
            "What items would you like to order this month?"
        )

        logger.info("[Controller] Ready and listening...")

        # Keep alive
        while self.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1)

    # ── Audio subscription ────────────────────────────────────────────────────

    async def _subscribe(self, track):
        if not isinstance(track, rtc.RemoteAudioTrack):
            return
        logger.info(f"[Controller] Subscribed to audio track: {track.sid}")
        audio_stream = rtc.AudioStream(track, sample_rate=self.SAMPLE_RATE, num_channels=self.CHANNELS)
        async for frame_event in audio_stream:
            await self._process_frame(frame_event.frame)

    # ── VAD + frame processing ────────────────────────────────────────────────

    async def _process_frame(self, frame: rtc.AudioFrame):
        # Don't listen while agent is speaking
        if self._agent_speaking:
            return

        pcm = bytes(frame.data)
        if len(pcm) < 2:
            return

        samples   = struct.unpack(f"{len(pcm)//2}h", pcm)
        energy    = sum(abs(s) for s in samples) / max(len(samples), 1)

        # Log energy every 50 frames so we can see what's coming in
        if not hasattr(self, '_frame_count'):
            self._frame_count = 0
        self._frame_count += 1
        if self._frame_count % 50 == 0:
            logger.info(f"[Controller] Frame energy: {energy:.1f} (threshold: {self.VAD_THRESHOLD}), speaking: {self._speaking}")

        is_speech = energy > self.VAD_THRESHOLD

        if is_speech:
            self._speaking = True
            self._silence  = 0
            self._audio_buf.extend(pcm)
        elif self._speaking:
            self._silence += 1
            self._audio_buf.extend(pcm)
            if self._silence >= self.SILENCE_FRAMES:
                await self._flush_utterance()

    # ── Utterance handler ─────────────────────────────────────────────────────

    async def _flush_utterance(self):
        audio = bytes(self._audio_buf)
        self._audio_buf.clear()
        self._speaking = False
        self._silence  = 0

        duration_ms = len(audio) / (self.SAMPLE_RATE * self.CHANNELS * 2) * 1000
        if duration_ms < self.MIN_SPEECH_MS:
            logger.info(f"[Controller] Utterance too short ({duration_ms:.0f}ms), skipping")
            return

        logger.info(f"[Controller] Utterance captured ({duration_ms:.0f}ms)")

        # Wrap raw PCM in a proper WAV container before sending to STT
        import wave, io
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(audio)
        wav_bytes = wav_buf.getvalue()

        logger.info(f"[Controller] WAV prepared: {len(wav_bytes)} bytes")

        # STT
        transcript = await asyncio.get_event_loop().run_in_executor(
            None, self.stt.transcribe, wav_bytes
        )
        if not transcript or not transcript.strip():
            logger.info("[Controller] Empty transcript, skipping")
            return

        logger.info(f"[Controller] Transcript: {transcript!r}")

        # Agent
        intent_result = decide(transcript, self.state)
        response      = execute(intent_result, self.state)
        self.memory.save_session(self.state)

        if response == "__EXIT__":
            await self._speak("Thank you for your order. Goodbye!")
            await self.room.disconnect()
            return

        logger.info(f"[Controller] Response: {response!r}")
        await self._speak(response)
    # ── TTS + playback ────────────────────────────────────────────────────────

    async def _speak(self, text: str):
        if not self._source:
            return

        self._agent_speaking = True
        try:
            audio_bytes = await asyncio.get_event_loop().run_in_executor(
                None, self.tts.synthesize, text, None
            )
            if not audio_bytes:
                return

            import wave, io, numpy as np
            from scipy import signal

            with wave.open(io.BytesIO(audio_bytes)) as wf:
                pcm_data     = wf.readframes(wf.getnframes())
                src_rate     = wf.getframerate()
                src_channels = wf.getnchannels()

            logger.info(f"[Controller] TTS audio: {src_rate}Hz, {src_channels}ch, {len(pcm_data)} bytes")

            # Convert to numpy
            samples = np.frombuffer(pcm_data, dtype=np.int16).copy()

            # Stereo → mono
            if src_channels == 2:
                samples = samples.reshape(-1, 2).mean(axis=1).astype(np.int16)

            # Resample to 16kHz if needed
            if src_rate != self.SAMPLE_RATE:
                num_samples = int(len(samples) * self.SAMPLE_RATE / src_rate)
                samples     = signal.resample(samples, num_samples).astype(np.int16)

            pcm_data = samples.tobytes()

            # Push in 10ms frames
            samples_per_frame = self.SAMPLE_RATE // 100
            bytes_per_frame   = samples_per_frame * 2

            for i in range(0, len(pcm_data), bytes_per_frame):
                chunk = pcm_data[i:i + bytes_per_frame]
                if len(chunk) < bytes_per_frame:
                    chunk = chunk + b'\x00' * (bytes_per_frame - len(chunk))
                frame = rtc.AudioFrame(
                    data=chunk,
                    sample_rate=self.SAMPLE_RATE,
                    num_channels=self.CHANNELS,
                    samples_per_channel=samples_per_frame,
                )
                await self._source.capture_frame(frame)
                await asyncio.sleep(0.01)

            logger.info("[Controller] Finished speaking")

        except Exception as e:
            logger.error(f"[Controller] TTS/playback error: {e}", exc_info=True)
        finally:
            self._agent_speaking = False