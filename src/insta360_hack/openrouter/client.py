import base64

import httpx

from insta360_hack.config import Settings

MODEL = "google/gemini-3.1-flash-image"
IMAGE_ENDPOINT = "https://openrouter.ai/api/v1/images"


def _image_parts(images: list[tuple[bytes, str]]) -> list[dict]:
    parts = []
    for raw, media_type in images:
        encoded = base64.b64encode(raw).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}})
    return parts


class OpenRouterError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class OpenRouterClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self.http = http
        self.settings = settings

    async def plan_cutaway(self, *, prompt: str, images: list[tuple[bytes, str]]) -> str:
        payload = {
            "model": self.settings.deepseek_model,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}, *_image_parts(images)],
                }
            ],
        }
        if not self.settings.deepseek_api_key:
            raise OpenRouterError("CONFIG", "缺少 DEEPSEEK_API_KEY")
        body = await self._post(
            f"{self.settings.deepseek_base_url}/chat/completions",
            payload,
            "整理屋剖面说明失败",
            api_key=self.settings.deepseek_api_key,
        )
        message = ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
        if isinstance(message, list):
            text = "".join(part.get("text", "") for part in message if isinstance(part, dict))
        else:
            text = str(message or "")
        text = text.strip()
        if not text:
            raise OpenRouterError("IMAGE", "整理屋剖面说明没有返回文字")
        return text

    async def generate(self, *, prompt: str, images: list[tuple[bytes, str]]) -> tuple[bytes, str]:
        payload = {
            "model": MODEL,
            "prompt": prompt,
            "n": 1,
            "resolution": "1K",
            "aspect_ratio": "16:9",
            "input_references": _image_parts(images),
        }
        body = await self._post(IMAGE_ENDPOINT, payload, "优化参考图失败")
        images = body.get("data") or []
        if not images or not images[0].get("b64_json"):
            raise OpenRouterError("IMAGE", "优化参考图没有返回图片")
        media = images[0].get("media_type") or "image/png"
        return base64.b64decode(images[0]["b64_json"]), media

    async def _post(self, url: str, payload: dict, failure: str, *, api_key: str | None = None) -> dict:
        token = api_key if api_key is not None else self.settings.openrouter_api_key
        if not token:
            raise OpenRouterError("CONFIG", "缺少 OPENROUTER_API_KEY")
        try:
            response = await self.http.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=180,
            )
        except httpx.HTTPError as exc:
            raise OpenRouterError("IMAGE", f"{failure}: {type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            detail = response.text[:300].replace("\n", " ")
            raise OpenRouterError("IMAGE", f"{failure}: HTTP {response.status_code} {detail}")
        return response.json()
