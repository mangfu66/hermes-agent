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
DEFAULT_MODEL = "mimo-v2.5"
HERMES_ENV_PATH = Path.home() / ".hermes" / ".env"
DEFAULT_PROMPT = (
    "请逐字转写这段音频内容，只输出转写文本本身，不要解释，不要总结，"
    "不要加引号，不要补充额外说明，不要标注说话人。"
    "保留原始语言；若为中文请输出简体中文；听不清的部分写[听不清]。"
)
MIME_BY_SUFFIX = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


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


def guess_mime(path: Path) -> str:
    return MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


def build_payload(audio_data_uri: str, prompt: str, model: str) -> dict:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_data_uri,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
        "max_completion_tokens": 4096,
    }


def parse_transcript(body: str) -> str:
    data = json.loads(body)
    message = data["choices"][0]["message"]
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text") or item.get("content")
                if txt:
                    parts.append(str(txt))
        return "\n".join(parts).strip()
    return str(content).strip()


def local_fallback(file_path: str, language: str) -> str:
    from faster_whisper import WhisperModel

    model_name = os.getenv("MIMO_STT_FALLBACK_MODEL", "base")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(file_path, language=language or None)
    text = "".join(segment.text for segment in segments).strip()
    return text


def transcribe_via_mimo(file_path: Path, prompt: str, model: str, base_url: str) -> str:
    api_key = get_secret("MIMO_TOKEN_PLAN_API_KEY")
    if not api_key:
        raise RuntimeError("MIMO_TOKEN_PLAN_API_KEY is not set")

    audio_bytes = file_path.read_bytes()
    mime = guess_mime(file_path)
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    audio_data_uri = f"data:{mime};base64,{audio_b64}"
    payload = build_payload(audio_data_uri=audio_data_uri, prompt=prompt, model=model)
    endpoint = base_url.rstrip("/") + "/chat/completions"
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
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")
    transcript = parse_transcript(body)
    if not transcript:
        raise RuntimeError("empty transcript from MiMo")
    return transcript


def main() -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio with Xiaomi MiMo, fallback to local whisper")
    parser.add_argument("--input", required=True, help="Path to input audio file")
    parser.add_argument("--output-dir", required=True, help="Directory where a .txt transcript will be written")
    parser.add_argument("--language", default=os.getenv("MIMO_STT_LANGUAGE", "zh"))
    parser.add_argument("--model", default=os.getenv("MIMO_STT_MODEL", DEFAULT_MODEL))
    parser.add_argument("--prompt", default=os.getenv("MIMO_STT_PROMPT", DEFAULT_PROMPT))
    parser.add_argument("--base-url", default=os.getenv("MIMO_STT_BASE_URL", DEFAULT_BASE_URL))
    args = parser.parse_args()

    input_path = Path(args.input).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}.txt"

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    try:
        transcript = transcribe_via_mimo(
            file_path=input_path,
            prompt=args.prompt,
            model=args.model,
            base_url=args.base_url,
        )
        provider = "mimo"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"MiMo STT HTTP {exc.code}: {detail}", file=sys.stderr)
        try:
            transcript = local_fallback(str(input_path), args.language)
            provider = "local-fallback"
        except Exception as fallback_exc:
            print(f"Local fallback failed after MiMo HTTP error: {fallback_exc}", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"MiMo STT failed: {exc}", file=sys.stderr)
        try:
            transcript = local_fallback(str(input_path), args.language)
            provider = "local-fallback"
        except Exception as fallback_exc:
            print(f"Local fallback failed after MiMo error: {fallback_exc}", file=sys.stderr)
            return 1

    transcript = transcript.strip()
    if not transcript:
        print("Transcript is empty", file=sys.stderr)
        return 1

    output_path.write_text(transcript + "\n", encoding="utf-8")
    print(f"{provider}:{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
