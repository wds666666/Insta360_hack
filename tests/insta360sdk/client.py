"""兼容旧测试脚本；正式实现位于 insta360_hack.insta360.client。"""

from insta360_hack.insta360.client import (
    DEFAULT_BASE_URL,
    Insta360OSCClient,
    OSCError,
    OSCResponseError,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "Insta360OSCClient",
    "OSCError",
    "OSCResponseError",
]
