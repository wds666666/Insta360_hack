# 触见

把一张全景和一句空间说明，做成视障者可以触摸的空间地图。

我们做了一个将视觉空间转化为触觉语言的 AI 空间地图，给视障者使用，解决他们无法通过视觉建立空间认知的问题。真正做到「人人平等」，让残障人士也可以更好的理解世界。

页面上传全景和说明。后端先看这张全景，写成一段 3D 屋剖面说明，再交给 Gemini 画出可触摸的空间结构，然后把这张图交给 Lux3D 生成网格。视障者摸到的形状，和页面上预览的是同一份 `model.glb`。

接口和节点的完整约定在 [docs/architecture.md](docs/architecture.md)。页面细节在 [frontend/README.md](frontend/README.md)。

## 怎么跑

需要 Python 3.12 和 Node.js。密钥只放在仓库根目录的 `.env`，不进前端。

```bash
cp .env.example .env
# 填上 LUX3D_API_KEY 和 OPENROUTER_API_KEY
uv sync
./scripts/dev.sh
```

后端在 <http://127.0.0.1:8000>，页面在 <http://127.0.0.1>。`Ctrl+C` 会同时停下两边。脚本启动前会先结束已经占用 `8000` 和 `80` 的旧进程；后端如果没有起来，前端不会再启动。

只开后端：`uv run python main.py`。只开前端时，后端要已经在 `8000`：`npm run dev --prefix frontend`。

命令行跑同一条工作流：

```bash
uv run python -m insta360_hack.cli --prompt "只留一个房间的墙和家具" --image ./room.jpg
uv run python -m insta360_hack.cli --resume <run_id>
```

测试：`uv run pytest -q`。

## 页面上怎么用

1. 参考图可以手动上传，也可以直接用 Insta360 X5 拍摄：
   - 手动上传：最多 8 张，可以点选、多选、拖入或按 `Ctrl+V` / `⌘V` 粘贴。
   - X5 拍摄：Mac 先连接相机 Wi-Fi，页面点击拍摄。后端保存 ERP 全景、小行星和前后左右上下视图；拍完恢复互联网连接，再勾选要交给 DeepSeek 的图片。默认不选上视图。
   选中的图片会立即显示在「全景原图」，不必等提交。
2. 「给 DeepSeek 的说明」打开时已经写好一段 3D 屋剖面的示例，可以改，也可以清空再自己写。提交的就是 DeepSeek 看到的第一级说明。
3. 选生成方式，默认是分步确认。
   - **分步确认**：先看剖面说明，再决定出图；空间结构出来后，再按「用这张图生成触觉模型」。
   - **全自动**：提交后一直做到可触摸的模型。
4. 左侧「已有任务」来自 `data/runs`。点一条回到那次的原图、空间结构和模型。地址栏带 `?run=`，刷新不会丢掉正在看的任务。

优化参考图和网格生成都会显示已经用了多久，结束后保留用时。网格还在生成时，预览外圈和右下角的计时框会有一道光在流动。

## 一次任务留下什么

```text
data/runs/{run_id}/
  run.json
  reference.jpg
  optimized.png
  model.glb
  model.stl
```

`run.json` 就是查询接口的正文。服务重启后，已经提交给厂商的网格会从轮询接着跑。还没创建厂商任务的进行中记录，才会标成中断。

## 配置

| 变量 | 说明 |
|------|------|
| `LUX3D_API_KEY` | 必填 |
| `OPENROUTER_API_KEY` | 必填，只用于 Gemini 图像优化 |
| `DEEPSEEK_API_KEY` | 必填，看全景并写成 3D 屋剖面说明 |
| `DEEPSEEK_MODEL` | 默认 `deepseek-flash`（V4.1-Flash） |
| `LUX3D_REGION` | `cn`（默认）或 `global` |
| `LUX3D_BASE_URL` | 可选，覆盖区域默认地址 |
| `CORS_ORIGINS` | 逗号分隔，默认 `http://localhost` |
| `ACCESS_PASSWORD` | 生成触觉地图前要输入的密码，默认 `insta360`。留空则不校验 |
| `DATA_DIR` | 默认 `data` |
| `RUN_TIMEOUT_SECONDS` | 网格生成和 STL 导出的超时，默认 `2400` |
| `POLL_INTERVAL_SECONDS` | 轮询间隔，默认 `12` |
| `INSTA360_BASE_URL` | 相机 OSC 地址，默认 `http://192.168.42.1` |
| `INSTA360_CAPTURE_TIMEOUT` | 等待拍照和机内拼接的秒数，默认 `120` |
| `FFMPEG_BIN` | 带 `v360` 滤镜的 FFmpeg 命令，默认 `ffmpeg` |
| `FFMPEG_TIMEOUT` | 单张投影导出的超时秒数，默认 `120` |
