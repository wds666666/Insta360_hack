import time
from dataclasses import dataclass
from pathlib import Path

from insta360_hack.config import Settings
from insta360_hack.engine.store import RunStore


@dataclass
class RunContext:
    record: dict
    reference_images: list[tuple[bytes, str]]
    client: object
    images: object
    settings: Settings
    store: RunStore
    deadline: float

    def touch(self) -> None:
        self.store.save(self.record)

    def run_dir(self) -> Path:
        return self.settings.data_dir / "runs" / self.record["run_id"]


def make_context(
    record: dict,
    *,
    image_bytes: bytes | None = None,
    image_suffix: str | None = None,
    reference_images: list[tuple[bytes, str]] | None = None,
    client: object,
    images: object,
    settings: Settings,
    store: RunStore,
) -> RunContext:
    packed = list(reference_images or [])
    if image_bytes is not None:
        packed.append((image_bytes, image_suffix or ""))
    return RunContext(
        record=record,
        reference_images=packed,
        client=client,
        images=images,
        settings=settings,
        store=store,
        deadline=time.monotonic() + settings.run_timeout_seconds,
    )
