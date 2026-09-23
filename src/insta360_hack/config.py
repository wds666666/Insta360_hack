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
    deepseek_api_key: str
    deepseek_model: str
    deepseek_base_url: str
    base_url: str
    region: str
    cors_origins: list[str]
    data_dir: Path
    run_timeout_seconds: float
    poll_interval_seconds: float
    insta360_base_url: str = "http://192.168.42.1"
    insta360_request_timeout: float = 15.0
    insta360_capture_timeout: float = 120.0
    insta360_poll_interval: float = 1.0
    ffmpeg_bin: str = "ffmpeg"
    ffmpeg_timeout: float = 120.0
    projection_view_size: int = 1600
    projection_view_fov: int = 90
    projection_planet_size: int = 1600
    projection_planet_fov: int = 300

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
        for item in os.environ.get("CORS_ORIGINS", "http://localhost").split(",")
        if item.strip()
    ]
    return Settings(
        api_key=os.environ.get("LUX3D_API_KEY", "").strip(),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", "").strip(),
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-flash").strip() or "deepseek-flash",
        deepseek_base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        base_url=base_url,
        region=region,
        cors_origins=origins,
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        run_timeout_seconds=float(os.environ.get("RUN_TIMEOUT_SECONDS", "2400")),
        poll_interval_seconds=float(os.environ.get("POLL_INTERVAL_SECONDS", "12")),
        insta360_base_url=os.environ.get(
            "INSTA360_BASE_URL", "http://192.168.42.1"
        ).rstrip("/"),
        insta360_request_timeout=float(
            os.environ.get("INSTA360_REQUEST_TIMEOUT", "15")
        ),
        insta360_capture_timeout=float(
            os.environ.get("INSTA360_CAPTURE_TIMEOUT", "120")
        ),
        insta360_poll_interval=float(
            os.environ.get("INSTA360_POLL_INTERVAL", "1")
        ),
        ffmpeg_bin=os.environ.get("FFMPEG_BIN", "ffmpeg").strip() or "ffmpeg",
        ffmpeg_timeout=float(os.environ.get("FFMPEG_TIMEOUT", "120")),
        projection_view_size=int(os.environ.get("INSTA360_VIEW_SIZE", "1600")),
        projection_view_fov=int(os.environ.get("INSTA360_VIEW_FOV", "90")),
        projection_planet_size=int(
            os.environ.get("INSTA360_PLANET_SIZE", "1600")
        ),
        projection_planet_fov=int(os.environ.get("INSTA360_PLANET_FOV", "300")),
    )
