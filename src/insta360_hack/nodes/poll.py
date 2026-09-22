import asyncio
import time
from datetime import datetime, timezone

from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError
from insta360_hack.lux3d.models import STATUS_LABELS


class PollLux3D:
    def __init__(self, name: str, task_key: str, urls_key: str, stage: str):
        self.name = name
        self.task_key = task_key
        self.urls_key = urls_key
        self.stage = stage

    async def execute(self, ctx: RunContext) -> None:
        task_id = int(ctx.record["artifacts"][self.task_key])
        limit = int(ctx.settings.run_timeout_seconds)
        started_key = f"{self.name}_started_at"
        elapsed_key = f"{self.name}_elapsed_seconds"
        artifacts = ctx.record["artifacts"]
        if not artifacts.get(started_key):
            artifacts[started_key] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            ctx.touch()
        started = datetime.fromisoformat(artifacts[started_key])
        print(f"{self.stage} 开始轮询 task_id={task_id}，超时上限 {limit}s", flush=True)
        while True:
            elapsed = int(ctx.settings.run_timeout_seconds - (ctx.deadline - time.monotonic()))
            stage_elapsed = max(0, int(time.time() - started.timestamp()))
            if time.monotonic() > ctx.deadline:
                artifacts[elapsed_key] = stage_elapsed
                artifacts["lux3d_elapsed_seconds"] = stage_elapsed
                ctx.touch()
                raise NodeError("TIMEOUT", f"{self.stage}超时，已等待 {elapsed}s，上限 {limit}s")
            task = await ctx.client.get_task(task_id)
            label = STATUS_LABELS.get(task.status, "未知")
            artifacts["lux3d_status"] = task.status
            artifacts["lux3d_status_label"] = label
            artifacts["lux3d_stage"] = self.stage
            artifacts["lux3d_elapsed_seconds"] = stage_elapsed
            artifacts[elapsed_key] = stage_elapsed
            ctx.touch()
            print(
                f"{self.stage} task_id={task_id} status={task.status} {label}  本阶段 {stage_elapsed}s / 已等待 {max(elapsed, 0)}s / 超时 {limit}s",
                flush=True,
            )
            if task.status == 3:
                ctx.record["artifacts"][self.urls_key] = task.outputs
                return
            if task.status == 4:
                raise NodeError("LUX3D_FAILED", f"{self.stage}失败")
            if task.status == 6:
                raise NodeError("LUX3D_CANCELLED", f"{self.stage}已取消")
            await asyncio.sleep(ctx.settings.poll_interval_seconds)
