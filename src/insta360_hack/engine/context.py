import time
from dataclasses import dataclass
from pathlib import Path

from insta360_hack.config import Settings
from insta360_hack.engine.store import RunStore


@dataclass
class RunContext:
    record: dict
    image_bytes: bytes | None
    image_suffix: str | None
    client: object
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
    image_bytes: bytes | None,
    image_suffix: str | None,
    client: object,
    settings: Settings,
    store: RunStore,
) -> RunContext:
    return RunContext(
        record=record,
        image_bytes=image_bytes,
        image_suffix=image_suffix,
        client=client,
        settings=settings,
        store=store,
        deadline=time.monotonic() + settings.run_timeout_seconds,
    )
