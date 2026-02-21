# services/voice_agent/stt/sarvam_stt.py
# Sarvam Speech-to-Text client.
# Input:  raw audio bytes (wav format)
# Output: transcript string
# No business logic here — pure API wrapper.

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

# Supported languages — use "hi-IN" for Hindi, "en-IN" for English
DEFAULT_LANGUAGE = "unknown"


class SarvamSTT:

    def __init__(self, language: str = DEFAULT_LANGUAGE, timeout: int = 10):
        self.language = language
        self.timeout  = timeout

        if not SARVAM_API_KEY:
            raise ValueError("SARVAM_API_KEY not found in environment.")

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> str:
        """
        Sends audio bytes to Sarvam STT API.
        Returns transcript string.
        Returns empty string on failure — never raises.

        Args:
            audio_bytes: raw WAV audio bytes
            filename:    filename hint for the API (must end in .wav)
        """
        if not audio_bytes:
            return ""

        try:
            from shared.utils.circuit_breaker import sarvam_stt_breaker, CircuitOpenError

            def _call():
                with httpx.Client(timeout=self.timeout) as client:
                    return client.post(
                        SARVAM_STT_URL,
                        headers={"api-subscription-key": SARVAM_API_KEY},
                        files={"file": (filename, audio_bytes, "audio/wav")},
                        data={
                            "language_code":   self.language,
                            "model":           "saarika:v2.5",
                            "with_timestamps": "false",
                        }
                    )

            response = sarvam_stt_breaker.call(_call)

            if response.status_code == 200:
                result        = response.json()
                transcript    = result.get("transcript", "").strip()
                detected_lang = result.get("language_code", "unknown")
                print(f"[STT] Transcript: {transcript!r} | Language: {detected_lang}")
                return transcript
            else:
                print(f"[STT] Error {response.status_code}: {response.text}")
                return ""

        except Exception as e:
            print(f"[STT] Error: {e}")
            return ""

      

    def transcribe_file(self, file_path: str) -> str:
        """
        Convenience method — reads a WAV file and transcribes it.
        Useful for testing without a live audio stream.
        """
        try:
            with open(file_path, "rb") as f:
                audio_bytes = f.read()
            filename = os.path.basename(file_path)
            return self.transcribe(audio_bytes, filename)
        except FileNotFoundError:
            print(f"[STT] File not found: {file_path}")
            return ""