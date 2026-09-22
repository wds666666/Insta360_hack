import asyncio
import time

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
        print(f"{self.stage} 开始轮询 task_id={task_id}，超时上限 {limit}s", flush=True)
        while True:
            elapsed = int(ctx.settings.run_timeout_seconds - (ctx.deadline - time.monotonic()))
            if time.monotonic() > ctx.deadline:
                raise NodeError("TIMEOUT", f"{self.stage}超时，已等待 {elapsed}s，上限 {limit}s")
            task = await ctx.client.get_task(task_id)
            label = STATUS_LABELS.get(task.status, "未知")
            ctx.record["artifacts"]["lux3d_status"] = task.status
            ctx.record["artifacts"]["lux3d_status_label"] = label
            ctx.record["artifacts"]["lux3d_stage"] = self.stage
            ctx.touch()
            print(
                f"{self.stage} task_id={task_id} status={task.status} {label}  已等待 {max(elapsed, 0)}s / 超时 {limit}s",
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
