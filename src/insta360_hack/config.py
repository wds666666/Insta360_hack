import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    path = Path(".env")
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass(frozen=True)
class Settings:
    api_key: str
    openrouter_api_key: str
    base_url: str
    region: str
    cors_origins: list[str]
    data_dir: Path
    run_timeout_seconds: float
    poll_interval_seconds: float

    @property
    def path_prefix(self) -> str:
        return "/global" if self.region == "global" else ""


def load_settings() -> Settings:
    _load_dotenv()
    region = os.environ.get("LUX3D_REGION", "cn").strip() or "cn"
    if region not in {"cn", "global"}:
        raise RuntimeError("LUX3D_REGION 只能是 cn 或 global")
    default_host = "https://api.aholo3d.com" if region == "global" else "https://api.aholo3d.cn"
    base_url = os.environ.get("LUX3D_BASE_URL", default_host).rstrip("/")
    origins = [
        item.strip()
        for item in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
        if item.strip()
    ]
    return Settings(
        api_key=os.environ.get("LUX3D_API_KEY", "").strip(),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", "").strip(),
        base_url=base_url,
        region=region,
        cors_origins=origins,
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        run_timeout_seconds=float(os.environ.get("RUN_TIMEOUT_SECONDS", "2400")),
        poll_interval_seconds=float(os.environ.get("POLL_INTERVAL_SECONDS", "12")),
    )
