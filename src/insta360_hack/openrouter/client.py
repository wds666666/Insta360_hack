import base64

import httpx

from insta360_hack.config import Settings

MODEL = "google/gemini-3.1-flash-image"
ENDPOINT = "https://openrouter.ai/api/v1/images"


class OpenRouterError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class OpenRouterClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self.http = http
        self.settings = settings

    async def generate(self, *, prompt: str, image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
        if not self.settings.openrouter_api_key:
            raise OpenRouterError("CONFIG", "缺少 OPENROUTER_API_KEY")
        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": MODEL,
            "prompt": prompt,
            "n": 1,
            "resolution": "1K",
            "aspect_ratio": "16:9",
            "input_references": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}}
            ],
        }
        try:
            response = await self.http.post(
                ENDPOINT,
                headers={
                    "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
        except httpx.HTTPError as exc:
            raise OpenRouterError("IMAGE", f"优化参考图失败: {type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            detail = response.text[:300].replace("\n", " ")
            raise OpenRouterError("IMAGE", f"优化参考图失败: HTTP {response.status_code} {detail}")
        body = response.json()
        images = body.get("data") or []
        if not images or not images[0].get("b64_json"):
            raise OpenRouterError("IMAGE", "优化参考图没有返回图片")
        media = images[0].get("media_type") or "image/png"
        return base64.b64decode(images[0]["b64_json"]), media
