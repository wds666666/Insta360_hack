# 3D 生成后端架构

> 状态：v1 按本文实现。本文是唯一规格。  
> 厂商长文在 `ref/lux3d.md`（gitignore）。Asset 上传以开放平台 OpenAPI 为准：`GET /asset/v1/token`，再在返回的 `globalDomain` 上调用 `/ous/api/v2/...`。

## 1. 系统是什么

前端负责上传参考图、填写提示词、看进度、读取并显示原图、优化图和 3D 模型。  
后端是手写的直线工作流，用 FastAPI 暴露。用户提示词和全部参考图先交给 DeepSeek `deepseek-flash`（V4.1-Flash，能看图），写成一段 3D 屋剖面说明，再连同这些参考图交给 OpenRouter 的 `google/gemini-3.1-flash-image` 生成一张优化图，然后把这张图交给 Lux3D **图生 3D**。提示词不传给 Lux3D。

```
浏览器
  手动上传，或先请求 X5 拍摄并选择服务端候选图
        │
        ▼
FastAPI
  POST /api/v1/camera/captures       后台拍摄并导出 8 张候选图
  GET  /api/v1/camera/captures/{id}  轮询拍摄状态和候选图
  POST /api/v1/runs          立即 202 + run_id
  GET  /api/v1/runs          列出 data/runs 里已有的任务，新的在前
  GET  /api/v1/runs/{id}     轮询状态；outputs 里已完成的图随时可读
  GET  /api/v1/runs/{id}/files/{name}   读原图、优化图和模型
  POST /api/v1/runs/{id}/image   确认剖面说明后出图
  POST /api/v1/runs/{id}/mesh    确认优化图后做网格
        │
        ▼
validate → save_image → plan_cutaway → optimize_image → upload_image → create_img_to_3d
        → poll_mesh → export_stl → poll_stl → download_model
        │
        ▼
本地 data/runs/{run_id}/
  reference.jpg
  optimized.png
  model.glb
  model.stl
  run.json

本地 data/captures/{capture_id}/
  capture.json
  panorama.jpg
  little_planet.jpg
  view_front.jpg ... view_down.jpg
```

Lux3D 的 `img` 必须是它能访问的 URL。本地文件不能直接当 `img`。所以顺序是：先把用户参考图写到本地，Gemini 优化后再把优化图写到同一目录，再走 Asset 上传拿到 URL，然后创建图生 3D。生成结束后把网格 GLB 和 STL 下载到同一个 run 目录。前端只访问我们的文件接口，不拿厂商的临时 URL（约 2 小时过期）。优化图一写入 `data/runs/{id}/`，查询接口就能返回它，不必等 3D 完成。

## 2. 为什么现在手写

输入是固定的参考图 + 提示词，节点顺序固定。理解图文并改图的是 Gemini，把优化图做成网格的是 Lux3D 图生 3D。

- 不引入 Agno、LangGraph、Prefect、Temporal。
- 第一级说明和全景交给 DeepSeek。它写的剖面说明再交给 Gemini。图生 3D 不收 prompt。

以后再换执行器，节点函数保持不变：

| 何时 | 换什么 |
|------|--------|
| 条件分支、人工确认、并行 | LangGraph 做图执行器 |
| 用户用自然语言选择走哪条工作流 | Agno 做对话层，调用已有 HTTP API |

在那之前，这些库不进依赖。

## 3. 范围

### v1 做

- 工作流 `img-to-3d`：一张参考图 + prompt → 本地保存参考图 → Gemini 优化图写入 `data/runs/{id}/optimized.*` → Asset 上传优化图 → 图生 3D `G1` → 轮询 → 把 `model.glb` / `model.stl` 下载到本地。
- FastAPI：创建 run、列出已有 run、查询 run、读取 run 目录里的文件。查询在每一步完成后就能看到已落地的原图、优化图和模型。网格生成时写入本阶段开始时间和已用秒数。
- X5：浏览器触发后端通过 OSC 完成机内拼接拍照，再用 FFmpeg `v360` 导出小行星和前后左右上下视图。拍摄结果先保存在 `data/captures`，用户勾选后才复制到 run 的参考图。
- 前端「触见」：上传全景和空间说明，显示原图、优化图、步骤进度，并用 Three.js 预览 GLB。说明见 [frontend/README.md](../frontend/README.md)。
- `run.json` 写在 run 目录里，进程重启后仍能查到已结束的任务。重启时若网格任务已经创建（有 `lux3d_task_id` 或导出任务），从对应轮询接着跑，不把这次网格丢掉。还没创建厂商任务的 `pending` / `running` 才标为失败 `INTERRUPTED`。

### v1 不做

- 文生 3D、多模态单图、四视图、材质重绘、登录、数据库、任务队列。
- 条件分支。

### 为什么现在是图生 3D

用户提示词用来让 Gemini 改参考图。3D 只根据优化后的那一张图生成，对应 `POST /lux3d/v1/generate/img-to-3d/task/create` 的 `img`。不把 prompt 再传给 Lux3D。

## 4. 分层

| 层 | 职责 |
|----|------|
| `api` | 校验表单、建 run、后台执行、返回状态和文件 |
| `engine` | 按节点列表执行，更新 `run.json` |
| `nodes` | 一个节点一件事，不决定下一个是谁 |
| `openrouter` | Gemini 图像优化 |
| `lux3d` | 鉴权、Asset 上传、图生 3D、查询、下载文件 |

## 5. 节点

失败抛 `NodeError(code, message)`。当前节点标 `failed`，后面的标 `skipped`，run 结束。厂商错误 `c != "0"` 同样结束 run，`error.code` 用厂商的 `c`。

```text
img-to-3d:
  validate           prompt 非空；参考图是文件或 image_url，二选一；文件最多 8 张；style 若有则必须在枚举内
  save_image         一张图写入 data/runs/{id}/reference.{jpg|png|webp}
                     多张图写入 reference-1、reference-2……
                     若是 image_url，先下载一份到 reference.*，供前端显示
                     写完立刻填 outputs.reference_image（第一张）和 outputs.reference_images
  plan_cutaway       用户提交的第一级说明和全部参考图交给 DeepSeek
                     送出前把每张图收成最长边 2048 的 JPEG，原图仍留在磁盘上显示
                     写成的剖面说明留在 artifacts.image_prompt
                     mode=confirm 时停在 awaiting_image，不出图
  optimize_image     只按 image_prompt 和全部参考图交给 Gemini
                     结果写入 data/runs/{id}/optimized.{png|jpg|webp}
                     写完立刻填 outputs.optimized_image
                     mode=confirm 时停在 awaiting_mesh，此时还没有模型
  upload_image       上传优化图，得到 artifacts.image_url。不把用户原图交给 Lux3D
  create_img_to_3d   POST img-to-3d，version 固定 G1，outputFormat 只传 glb，不传 prompt、ply
  poll_mesh          轮询网格任务。日志带状态含义和已等待时间，整段超时默认 2400 秒
  export_stl         用网格 GLB 创建多格式导出，只要 stl
  poll_stl           轮询导出任务
  download_model     只下载 model.glb 和 model.stl，完成后填这两个 outputs
```

加节点：新建 `nodes/` 文件，把名字加进 `workflows.py` 的列表。状态里的 `nodes[]` 按这次 run 的列表返回。

## 6. 运行与文件

run 状态：`pending → running → succeeded | failed`。`mode=confirm` 时剖面说明写完停在 `awaiting_image`，优化图完成后停在 `awaiting_mesh`，确认后再回到 `running`。  
节点状态：`pending → running → succeeded | failed | skipped`。  
Lux3D 任务状态单独放在 `artifacts.lux3d_status`，并带 `lux3d_status_label`：`0` 初始化，`1` 运行中，`3` 成功，`4` 失败，`6` 已取消。产物只要网格，不保存高斯 PLY。

```text
data/runs/{run_id}/
  run.json
  reference.jpg
  optimized.png
  model.glb
  model.stl
```

`run.json` 就是查询接口的正文。创建 Lux3D 任务失败不自动重试。查询允许少量网络重试。并发超限（`GENERATION_CONCURRENCY_LIMIT_EXCEEDED`）直接失败，不排队。

## 7. HTTP

Base：`/api/v1`。CORS 来源读 `CORS_ORIGINS`。

### 创建

`POST /api/v1/runs`，`multipart/form-data`。

| 字段 | 必填 | 说明 |
|------|------|------|
| `workflow_id` | 是 | 只接受 `img-to-3d` |
| `prompt` | 是 | 交给 DeepSeek 的第一级说明，原文发送，不传给 Lux3D |
| `image` | 与 `image_url` 二选一 | 参考图，可重复上传，最多 8 张。同一间房的全景、行星图或其他视角。jpg / png / webp，每张最大 20MB |
| `image_url` | 与 `image` 二选一 | 已是公网 URL，仍会先下载再优化 |
| `capture_id` | 与 `image`、`image_url` 三选一 | 已成功完成的 X5 拍摄 ID |
| `capture_views` | 使用 `capture_id` 时必填 | JSON 字符串数组，可选 `panorama`、`little_planet`、`front`、`right`、`back`、`left`、`up`、`down`，至少 1 项、最多 8 项 |
| `style` | 否 | `photorealistic` `cartoon` `anime` `hand_painted` `cyberpunk` `fantasy` `glass`。有值时拼进交给 DeepSeek 的说明 |
| `mode` | 否 | `auto` 一直做到网格。`confirm` 在剖面说明后停在 `awaiting_image`，出图后再停在 `awaiting_mesh` |

缺字段、两个图都传、类型不对：`422`，不创建 run。成功 `202`：

```json
{ "run_id": "...", "workflow_id": "img-to-3d", "status": "pending" }
```

### X5 拍摄

`POST /api/v1/camera/captures` 返回 `202`：

```json
{ "capture_id": "...", "status": "pending" }
```

同一后端实例一次只允许一个 X5 拍摄；相机忙时返回 `409`，错误码为 `CAMERA_BUSY`。同步 OSC、图片下载和 FFmpeg 在工作线程中执行，不阻塞 FastAPI 事件循环。

`GET /api/v1/camera/captures/{capture_id}` 返回 `pending | running | succeeded | failed`、当前 `step_label`、相机信息、错误和候选图片 URL。完成后候选键固定为 ERP 全景、小行星和六方向。页面默认选择除 `up` 外的 7 张，用户可以自行调整。

`GET /api/v1/camera/captures/{capture_id}/files/{name}` 只允许 `panorama.jpg`、`little_planet.jpg` 和六个 `view_*.jpg`。服务重启时，未完成的拍摄会标记为 `INTERRUPTED`。

相机热点可能没有互联网，因此推荐操作顺序是：连接 X5 Wi-Fi完成拍摄 → 候选图落盘 → 恢复互联网 → 勾选图片并创建 run。

### 列出已有任务

`GET /api/v1/runs`

读 `data/runs/*/run.json`，按 `created_at` 新的在前。更早的任务如果没有 `created_at`，用 `run.json` 的修改时间。每条只返回打开任务需要的摘要：

```json
{
  "runs": [
    {
      "run_id": "...",
      "status": "succeeded",
      "created_at": "2026-09-22T07:30:00+00:00",
      "prompt": "...",
      "current_label": null,
      "reference_image": "/api/v1/runs/.../files/reference.jpg"
    }
  ]
}
```

### 查询

`GET /api/v1/runs/{run_id}`

`outputs` 从创建起就有四个键，没完成的是 `null`。文件一落到 `data/runs/{id}/` 就填对应路径，前端用它们显示，不必等整个 run 成功：

```json
{
  "run_id": "...",
  "workflow_id": "img-to-3d",
  "status": "running",
  "created_at": "2026-09-22T07:30:00+00:00",
  "current_node": "optimize_image",
  "nodes": [{ "name": "save_image", "label": "保存参考图", "status": "succeeded" }],
  "inputs": { "prompt": "...", "style": null, "image_url": null },
  "artifacts": {
    "reference_file": "/api/v1/runs/.../files/reference.jpg",
    "optimized_file": "/api/v1/runs/.../files/optimized.png",
    "image_url": "https://...厂商可访问的优化图...",
    "lux3d_task_id": 1256173,
    "lux3d_status": 1,
    "lux3d_status_label": "运行中",
    "lux3d_stage": "网格生成",
    "lux3d_elapsed_seconds": 96,
    "poll_mesh_started_at": "2026-09-22T07:31:00+00:00",
    "poll_mesh_elapsed_seconds": 96
  },
  "outputs": {
    "reference_image": "/api/v1/runs/.../files/reference.jpg",
    "optimized_image": "/api/v1/runs/.../files/optimized.png",
    "model_glb": null,
    "model_stl": null
  },
  "error": null
}
```

`nodes[].label` 是中文步骤名。厂商临时 URL 留在 `artifacts`，页面不用它们。网格生成开始时写入 `poll_mesh_started_at`，轮询中更新 `poll_mesh_elapsed_seconds`。结束后这个秒数保留，用来显示用时。

未知 run：`404`。失败时 `error` 为 `{ "code", "message" }`，已创建的 `lux3d_task_id` 保留。

### 确认后继续

`POST /api/v1/runs/{run_id}/image`，JSON `{ "prompt": "..." }`。只在 `awaiting_image` 时可用，否则 `409`。`prompt` 非空就覆盖 `artifacts.image_prompt`，然后从 `optimize_image` 继续。成功 `202`。

`POST /api/v1/runs/{run_id}/mesh`。只在 `awaiting_mesh` 时可用，否则 `409`。从 `upload_image` 继续。成功 `202`。

`awaiting_image` 和 `awaiting_mesh` 在服务重启后保持原状态，不标成中断。

### 读文件

`GET /api/v1/runs/{run_id}/files/{name}`

只允许该 run 目录下的 `reference.jpg|png|webp`、`reference-N.jpg|png|webp`、`optimized.jpg|png|webp`、`model.glb`、`model.stl`。前端显示优化图用 `outputs.optimized_image`，显示模型用 `outputs.model_glb`。多张原图用 `outputs.reference_images`，任务列表缩略图仍用第一张 `reference_image`。

## 8. Lux3D 约定

| 项 | 约定 |
|----|------|
| 国内 | `https://api.aholo3d.cn`，路径无前缀 |
| 国际 | `https://api.aholo3d.com`，路径前缀 `/global` |
| 鉴权 | `Authorization: <ApiKey>`，不加 `Bearer` |
| 图生 3D | `POST /lux3d/v1/generate/img-to-3d/task/create` |
| 查询 | `GET /lux3d/v1/generate/task/get?taskid=` |
| 成功 | `c == "0"`。创建结果 `d` 是 taskid。查询结果看 `d.status`，完成后再读 `d.outputs[].content` |
| G1 图生 3D 请求 | `img`、`version=G1`、`outputFormat=["glb"]`。不传 `prompt`、`ply` |
| 网格 GLB | 生成结果按槽位取第 2 项。ZIP 里可能夹带高斯资源，不作为交付物 |
| STL | `POST /lux3d/v1/multi-format-export/task/create`，`modelUrl` 用上面的 GLB，`outputFormat=["stl"]`。导出结果 7 个槽位，STL 在第 6 项 |
| 轮询日志 | `status=1 运行中  已等待 36s / 超时 2400s` |

Asset（优化图变成 `img`）：

1. `GET /asset/v1/token`，正文是 `ousToken`、`globalDomain`、`blockSize`（不是 `c/m/d`）。
2. 文件不超过 `blockSize`：`POST {globalDomain}/ous/api/v2/single/upload`，表单字段 `md5` + `file`，头 `ous-token-v2`。
3. 更大：`POST {globalDomain}/ous/api/v2/block/upload/init?md5&blocks&size&name`，再逐片 `POST /ous/api/v2/block/upload/part`。
4. `GET {globalDomain}/ous/api/v2/upload/status`，`d.status == 5` 时取 `d.url`。`6` 和 `8` 为失败。OUS 路径不加 `/global`。

### 图生 3D

当前工作流调用 `POST /lux3d/v1/generate/img-to-3d/task/create`。`version` 固定 `G1`。单图传 `img`，不传 `imgs`，不传 prompt。`outputFormat` 只传 `glb`。G1 在不含 `ply` 时仍返回 ZIP 和 GLB；只使用第 2 槽的网格 GLB。查询接口与生成任务相同。

## 9. 代码放哪

```text
docs/architecture.md
src/insta360_hack/
  app.py
  config.py
  cli.py
  api/runs.py
  engine/          runner、store、错误
  nodes/           校验、存图、剖面说明、优化、上传、图生 3D、轮询、导出、下载
  openrouter/      DeepSeek 看图写说明，Gemini 出图
  lux3d/           client 与 G1 槽位解析
data/runs/         gitignore，含 reference、optimized、model.glb、model.stl
frontend/            触见页面，见 frontend/README.md
scripts/dev.sh       同时启动后端和前端
```

一起启动：`./scripts/dev.sh`。后端默认 `0.0.0.0:8000`，前端 `http://127.0.0.1`。  
开发自测：`uv run python -m insta360_hack.cli --prompt "..." --image ./ref.jpg`  
只开后端：`uv run python main.py`。

## 10. 配置

| 变量 | 说明 |
|------|------|
| `LUX3D_API_KEY` | 必填 |
| `OPENROUTER_API_KEY` | 必填，只用于 Gemini 图像优化 |
| `DEEPSEEK_API_KEY` | 必填，看图并写成 3D 屋剖面说明 |
| `DEEPSEEK_MODEL` | 默认 `deepseek-flash`，即 V4.1-Flash |
| `DEEPSEEK_BASE_URL` | 默认 `https://api.deepseek.com` |
| `LUX3D_REGION` | `cn`（默认）或 `global` |
| `LUX3D_BASE_URL` | 可选，覆盖区域默认 Host |
| `CORS_ORIGINS` | 逗号分隔，默认 `http://localhost` |
| `DATA_DIR` | 默认 `data` |
| `RUN_TIMEOUT_SECONDS` | 默认 `2400`。网格生成和 STL 导出共用这一上限 |
| `POLL_INTERVAL_SECONDS` | 默认 `12` |
| `INSTA360_BASE_URL` | OSC 地址，默认 `http://192.168.42.1` |
| `INSTA360_REQUEST_TIMEOUT` | 单次 OSC 请求超时，默认 `15` 秒 |
| `INSTA360_CAPTURE_TIMEOUT` | 拍照及机内拼接等待，默认 `120` 秒 |
| `INSTA360_POLL_INTERVAL` | 拍照命令状态轮询间隔，默认 `1` 秒 |
| `FFMPEG_BIN` | 带 `v360` 的 FFmpeg 命令，默认 `ffmpeg` |
| `FFMPEG_TIMEOUT` | 每张投影图导出超时，默认 `120` 秒 |
| `INSTA360_VIEW_SIZE` | 六方向图边长，默认 `1600` |
| `INSTA360_VIEW_FOV` | 六方向图视场角，默认 `90` |
| `INSTA360_PLANET_SIZE` | 小行星图边长，默认 `1600` |
| `INSTA360_PLANET_FOV` | 小行星投影视场角，默认 `300` |

密钥只放服务端 `.env`，不进仓库，不进前端。

## 11. 验收

- [ ] 上传参考图 + prompt，run 成功后 `data/runs/{id}/model.glb` 和 `optimized.png`（或 jpg / webp）存在。
- [ ] Gemini 优化图写入后，`GET .../files/optimized.png` 能读到，此时可以还没有模型。
- [ ] `GET .../files/model.glb` 能读到该文件。
- [ ] Lux3D 的 `img` 是优化图的上传 URL，请求里没有 prompt。
- [ ] 缺图返回 422，不调用 Gemini，也不调用 Lux3D。
- [ ] 查询能看到当前节点、中文步骤名和 `lux3d_task_id`。
- [ ] 网页触发 X5 后能看到 ERP、小行星和六方向候选图，默认不勾选上视图。
- [ ] 创建 run 时只有用户勾选的 capture 视图进入 DeepSeek/Gemini。
- [ ] 第二个并发拍摄返回 `409 CAMERA_BUSY`，不能向相机并发发命令。
- [ ] 依赖里没有 agno、langgraph、langchain。
