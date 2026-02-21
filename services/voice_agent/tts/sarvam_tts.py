# services/voice_agent/tts/sarvam_tts.py
# Sarvam Text-to-Speech client.
# Input:  text string
# Output: audio bytes (wav format)
# Includes local cache for common phrases to avoid redundant API calls.

import os
import base64
import hashlib
import httpx
from dotenv import load_dotenv

load_dotenv()

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

DEFAULT_LANGUAGE = "en-IN"
DEFAULT_SPEAKER  = "anushka"  # options: meera, pavithra, maitreyi, arvind, amol

# Common phrases said on every call — cached at startup to save API calls
CACHEABLE_PHRASES = [
    "How much would you like?",
    "In what unit? For example: kg, gram, litre, or packet.",
    "Which item would you like to order?",
    "Shall I add this to your cart? Say yes or no.",
    "Your cart is empty.",
    "Say yes to confirm or no to cancel.",
    "Are you still there?",
    "Thank you for your order. Goodbye!",
    "Hello! This is your monthly ration reminder.",
    "What items would you like to order this month?",
]


class SarvamTTS:

    def __init__(self, language: str = DEFAULT_LANGUAGE,
                 speaker: str = DEFAULT_SPEAKER, timeout: int = 15):
        self.language = language
        self.speaker  = speaker
        self.timeout  = timeout
        self._cache: dict = {}  # text → audio bytes

        if not SARVAM_API_KEY:
            raise ValueError("SARVAM_API_KEY not found in environment.")

    def synthesize(self, text: str, language: str = None) -> bytes:
        """
        Converts text to speech audio bytes.
        Auto-detects language if not specified.
        Returns WAV audio bytes. Returns empty bytes on failure.
        """
        if not text or not text.strip():
            return b""

        text = text.strip()

        # Auto-detect language from text if not specified
        lang = language or self._detect_language(text)

        # Check cache
        cache_key = self._make_cache_key(text + lang)
        if cache_key in self._cache:
            print(f"[TTS] Cache hit: {text[:40]!r}")
            return self._cache[cache_key]

        audio_bytes = self._call_api(text, lang)

        if text in CACHEABLE_PHRASES and audio_bytes:
            self._cache[cache_key] = audio_bytes

        return audio_bytes

    def _detect_language(self, text: str) -> str:
        """
        Detects if text is Hindi or English based on character ranges.
        Hindi uses Devanagari script: Unicode range 0900-097F.
        """
        hindi_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
        ratio = hindi_chars / max(len(text), 1)

        if ratio > 0.3:
            return "hi-IN"
        return "en-IN"

    def synthesize_to_file(self, text: str, output_path: str) -> bool:
        """
        Synthesizes text and saves to a WAV file.
        Returns True on success, False on failure.
        Useful for testing without a live audio stream.
        """
        audio_bytes = self.synthesize(text)
        if not audio_bytes:
            return False
        try:
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            print(f"[TTS] Saved to: {output_path}")
            return True
        except Exception as e:
            print(f"[TTS] Failed to save file: {e}")
            return False

    def _call_api(self, text: str, language: str = None) -> bytes:
        """
        Makes the actual Sarvam TTS API call.
        Returns raw WAV bytes.
        """
        try:
            from shared.utils.circuit_breaker import sarvam_tts_breaker, CircuitOpenError

            def _call():
                with httpx.Client(timeout=self.timeout) as client:
                    return client.post(
                        SARVAM_TTS_URL,
                        headers={
                            "api-subscription-key": SARVAM_API_KEY,
                            "Content-Type": "application/json",
                        },
                        json={
                            "inputs":               [text],
                            "target_language_code": language or self.language,
                            "speaker":              self.speaker,
                            "model":                "bulbul:v2",
                            "enable_preprocessing": True,
                        }
                    )

            response = sarvam_tts_breaker.call(_call)

            if response.status_code == 200:
                result = response.json()
                audios = result.get("audios", [])
                if audios:
                    audio_bytes = base64.b64decode(audios[0])
                    print(f"[TTS] Synthesized {len(audio_bytes)} bytes for: {text[:40]!r}")
                    return audio_bytes
                print("[TTS] No audio in response.")
                return b""
            else:
                print(f"[TTS] Error {response.status_code}: {response.text}")
                return b""

        except Exception as e:
            print(f"[TTS] Error: {e}")
            return b""



    def _make_cache_key(self, text: str) -> str:
        return hashlib.md5(f"{text}:{self.language}:{self.speaker}".encode()).hexdigest()
