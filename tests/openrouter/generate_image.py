"""用 OpenRouter Image API 调用 google/gemini-3.1-flash-image 生成一张图。

密钥从环境变量 OPENROUTER_API_KEY 读取，不要写进仓库。
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import httpx

MODEL = "google/gemini-3.1-flash-image"
ENDPOINT = "https://openrouter.ai/api/v1/images"
OUT_DIR = Path(__file__).resolve().parent

PROMPT = (
    "Editorial product photograph of a small white ceramic cup on a pale oak table, "
    "soft daylight from the left, quiet empty background, realistic materials, no text, no people."
)


def main() -> None:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("缺少环境变量 OPENROUTER_API_KEY", file=sys.stderr)
        raise SystemExit(1)

    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "n": 1,
        "resolution": "1K",
        "aspect_ratio": "1:1",
    }

    print(f"request model={MODEL} resolution=1K aspect_ratio=1:1")
    with httpx.Client(timeout=180.0) as client:
        response = client.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code != 200:
        print(f"HTTP {response.status_code}", file=sys.stderr)
        print(response.text[:4000], file=sys.stderr)
        raise SystemExit(1)

    body = response.json()
    usage = body.get("usage") or {}
    images = body.get("data") or []
    print("usage:", json.dumps(usage, ensure_ascii=False))
    print(f"images: {len(images)}")
    if not images:
        print(json.dumps({k: v for k, v in body.items() if k != "data"}, ensure_ascii=False)[:2000])
        raise SystemExit(1)

    ext_by_type = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }
    for index, item in enumerate(images):
        media_type = item.get("media_type") or "image/png"
        raw = base64.b64decode(item["b64_json"])
        suffix = ext_by_type.get(media_type, "bin")
        name = f"gemini-3.1-flash-image.{suffix}" if index == 0 else f"gemini-3.1-flash-image-{index}.{suffix}"
        path = OUT_DIR / name
        path.write_bytes(raw)
        print(f"saved {path} bytes={len(raw)} media_type={media_type}")


if __name__ == "__main__":
    main()
