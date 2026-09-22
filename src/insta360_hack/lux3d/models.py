from dataclasses import dataclass


@dataclass(frozen=True)
class Lux3DTask:
    status: int
    outputs: list[str | None]


STATUS_LABELS = {
    0: "初始化",
    1: "运行中",
    3: "成功",
    4: "失败",
    6: "已取消",
}


def output_slots(items: list | None) -> list[str | None]:
    slots: list[str | None] = []
    for item in items or []:
        if not isinstance(item, dict):
            slots.append(None)
            continue
        content = item.get("content")
        if isinstance(content, str) and content and content not in {"null", "NOT_REQUESTED"}:
            slots.append(content)
        else:
            slots.append(None)
    return slots


def parse_g1_outputs(contents: list[str]) -> dict[str, str | None]:
    if len(contents) < 2:
        raise ValueError("G1 输出至少要有 ZIP 和 GLB")
    return {
        "zip_url": contents[0],
        "glb_url": contents[1],
        "ply_url": contents[2] if len(contents) > 2 else None,
    }
