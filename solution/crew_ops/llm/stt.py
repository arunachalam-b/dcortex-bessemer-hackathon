"""Speech-to-text via the Sarvam Saarika API (stdlib-only).

Used by the web UI's mic button: the browser records audio, converts it to
16 kHz mono WAV, and POSTs it here; Sarvam returns the transcript. This is
independent of LLM_PROVIDER — audio is always transcribed by Sarvam.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid

from .config import ConfigError, load_env
from .providers import ProviderError

STT_URL = "https://api.sarvam.ai/speech-to-text"
STT_DEFAULT_MODEL = "saarika:v2.5"


def transcribe(audio: bytes, mime: str = "audio/wav") -> dict:
    """Transcribe one short audio clip; returns {transcript, language_code}."""
    load_env()
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise ConfigError("audio input needs SARVAM_API_KEY in solution/.env")
    model = os.environ.get("SARVAM_STT_MODEL", STT_DEFAULT_MODEL)

    boundary = uuid.uuid4().hex
    ext = mime.rsplit("/", 1)[-1] or "wav"
    body = b"".join([
        f"--{boundary}\r\nContent-Disposition: form-data; "
        f"name=\"model\"\r\n\r\n{model}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; "
        f"name=\"language_code\"\r\n\r\nunknown\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"clip.{ext}\"\r\nContent-Type: {mime}\r\n\r\n".encode(),
        audio, f"\r\n--{boundary}--\r\n".encode(),
    ])
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}",
               "api-subscription-key": key}

    last = None
    for attempt in range(3):
        req = urllib.request.Request(STT_URL, data=body, headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                out = json.loads(resp.read().decode())
            return {"transcript": (out.get("transcript") or "").strip(),
                    "language_code": out.get("language_code")}
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode()[:500]
            except Exception:
                detail = ""
            if e.code == 429 or e.code >= 500:
                last = ProviderError(f"Sarvam STT {e.code}: {detail or e.reason}")
                time.sleep(2 ** attempt)
                continue
            if e.code in (401, 403):
                raise ProviderError(
                    "Sarvam rejected the API key (check SARVAM_API_KEY)")
            raise ProviderError(f"Sarvam STT {e.code}: {detail or e.reason}")
        except (urllib.error.URLError, TimeoutError) as e:
            last = ProviderError(f"cannot reach the Sarvam STT API: {e}")
            time.sleep(2 ** attempt)
    raise last if last else ProviderError("Sarvam STT request failed")
