import time

from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError
from insta360_hack.lux3d.client import Lux3DError
from insta360_hack.nodes import NODES


async def run_workflow(ctx: RunContext) -> None:
    record = ctx.record
    record["status"] = "running"
    ctx.touch()
    nodes = NODES
    expected = [node.name for node in nodes]
    actual = [item["name"] for item in record["nodes"]]
    if expected != actual:
        raise RuntimeError("节点列表与 run 不一致")
    for index, node in enumerate(nodes):
        if time.monotonic() > ctx.deadline:
            _fail(ctx, index, NodeError("TIMEOUT", "任务超时"))
            return
        record["current_node"] = node.name
        record["nodes"][index]["status"] = "running"
        ctx.touch()
        try:
            await node.execute(ctx)
        except (NodeError, Lux3DError) as exc:
            _fail(ctx, index, exc)
            return
        record["nodes"][index]["status"] = "succeeded"
        ctx.touch()
    record["status"] = "succeeded"
    record["current_node"] = None
    ctx.touch()


def _fail(ctx: RunContext, index: int, exc: NodeError | Lux3DError) -> None:
    record = ctx.record
    record["nodes"][index]["status"] = "failed"
    for later in record["nodes"][index + 1 :]:
        later["status"] = "skipped"
    record["status"] = "failed"
    record["error"] = {"code": exc.code, "message": exc.message}
    ctx.touch()
