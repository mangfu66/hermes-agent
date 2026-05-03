#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5-tts"
DEFAULT_VOICE = "冰糖"
HERMES_ENV_PATH = Path.home() / ".hermes" / ".env"


def get_secret(name: str) -> str:
    if HERMES_ENV_PATH.exists():
        for line in HERMES_ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    value = os.getenv(name, "").strip()
    if value:
        return value
    return ""


def build_payload(text: str, voice: str, model: str, fmt: str, style: str | None):
    messages = []
    style = (style or "").strip()
    if style:
        messages.append({"role": "user", "content": style})
    messages.append({"role": "assistant", "content": text})
    return {
        "model": model,
        "messages": messages,
        "audio": {
            "format": fmt,
            "voice": voice,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate speech with Xiaomi MiMo TTS")
    parser.add_argument("--input", required=True, help="Path to UTF-8 text file")
    parser.add_argument("--output", required=True, help="Path to output audio file")
    parser.add_argument("--voice", default=os.getenv("MIMO_TTS_VOICE", DEFAULT_VOICE))
    parser.add_argument("--model", default=os.getenv("MIMO_TTS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--style", default=os.getenv("MIMO_TTS_STYLE", ""))
    parser.add_argument("--base-url", default=os.getenv("MIMO_TTS_BASE_URL", DEFAULT_BASE_URL))
    args = parser.parse_args()

    api_key = get_secret("MIMO_TOKEN_PLAN_API_KEY")
    if not api_key:
        print("MIMO_TOKEN_PLAN_API_KEY is not set", file=sys.stderr)
        return 2

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        print("Input text is empty", file=sys.stderr)
        return 2

    fmt = output_path.suffix.lower().lstrip(".") or "mp3"
    if fmt not in {"mp3", "wav", "ogg", "flac", "pcm16"}:
        fmt = "mp3"

    payload = build_payload(text=text, voice=args.voice, model=args.model, fmt=fmt, style=args.style)
    endpoint = args.base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "api-key": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"MiMo TTS HTTP {exc.code}: {detail}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"MiMo TTS request failed: {exc}", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
        message = data["choices"][0]["message"]
        audio_b64 = message["audio"]["data"]
    except Exception as exc:
        print(f"MiMo TTS response parse failed: {exc}; body={body[:1000]}", file=sys.stderr)
        return 1

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as exc:
        print(f"MiMo TTS audio decode failed: {exc}", file=sys.stderr)
        return 1

    output_path.write_bytes(audio_bytes)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
