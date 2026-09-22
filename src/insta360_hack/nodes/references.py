from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError

MEDIA = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
SUFFIXES = set(MEDIA)
MAX_REFERENCE_IMAGES = 8


def reference_names(record: dict) -> list[str]:
    artifacts = record.get("artifacts") or {}
    names = artifacts.get("reference_names")
    if names:
        return list(names)
    name = artifacts.get("reference_name")
    return [name] if name else []


def load_reference_images(ctx: RunContext) -> list[tuple[bytes, str]]:
    names = reference_names(ctx.record)
    if not names:
        raise NodeError("INVALID_INPUT", "还没有参考图")
    loaded: list[tuple[bytes, str]] = []
    for name in names:
        suffix = name[name.rfind(".") :]
        media_type = MEDIA.get(suffix)
        if media_type is None:
            raise NodeError("INVALID_INPUT", "参考图只支持 jpg、png、webp")
        loaded.append(((ctx.run_dir() / name).read_bytes(), media_type))
    return loaded
