# Insta360 X5 OSC 拍照验证

这里是与主服务隔离的最小验证工具，用来确认下面这条链路：

```text
Mac 连接 X5 Wi-Fi
  → OSC 设置照片模式和机内拼接
  → OSC 触发拍照
  → 轮询拍照处理状态
  → 下载相机生成的 JPEG
  → 校验为接近 2:1 的 ERP 全景图
  → 导出小行星图
  → 导出前/右/后/左/上/下六个主要视角
```

本工具只覆盖当前需要的拍照链路，不测试录像、实时预览、文件列表和删除。

## 是否需要 Media SDK

本流程不需要 Media SDK，但必须同时满足：

1. `camera.getOptions` 返回的 `photoStitchingSupport` 包含 `ondevice`；
2. 拍照前成功设置 `photoStitching=ondevice`；
3. 拍摄结果是可解码、接近 2:1 的 JPEG。

脚本不会在机内拼接不可用时退回双鱼眼原图，而是直接报错并停止。这样可以避免把 `.insp` 或未拼接内容误交给主服务。

## 文件说明

- `client.py`：可供后续主服务复用的最小同步 OSC 客户端。
- `capture_x5.py`：连接实机、拍照、下载、校验和多视角导出的一键脚本。
- `projections.py`：将已有 ERP 全景图导出为小行星图和主要视角。
- `test_osc_client.py`：不连接相机的模拟协议测试。
- `output/`：实拍下载目录；照片默认不提交到 Git。

## 实机前置条件

1. 用 Insta360 官方 App 激活 X5。
2. 将相机固件升级到当前官方版本。
3. 相机装有状态正常且空间充足的存储卡。
4. 开启相机 Wi-Fi 热点。
5. **保持 Mac 的 Wi-Fi 开启，并连接 X5 热点。**
6. 临时关闭会接管私有网段的 VPN 或代理。
7. 安装带 `v360` filter 的 FFmpeg；macOS 可执行 `brew install ffmpeg`。

相机地址固定为 `192.168.42.1`。可先检查 macOS 路由：

```bash
route -n get 192.168.42.1
```

正确结果的 `interface` 应是 Wi-Fi 网卡，不能是 `utun`。也可以直接探测：

```bash
curl --noproxy '*' \
  -H 'Accept: application/json' \
  -H 'X-XSRF-Protected: 1' \
  http://192.168.42.1/osc/info
```

能返回相机型号、序列号和固件版本后，再运行拍照脚本。

## 运行测试

在仓库根目录执行模拟测试：

```bash
uv run pytest -q tests/insta360sdk/test_osc_client.py
```

运行 X5 实拍：

```bash
uv run python tests/insta360sdk/capture_x5.py
```

指定输出文件：

```bash
uv run python tests/insta360sdk/capture_x5.py \
  --output tests/insta360sdk/output/room.jpg
```

默认最多等待相机处理 120 秒。需要延长时：

```bash
uv run python tests/insta360sdk/capture_x5.py \
  --capture-timeout 180
```

脚本会实际拍摄一张照片，但不会删除相机中的原文件。下载结果默认写入：

```text
tests/insta360sdk/output/x5_YYYYMMDD_HHMMSS.jpg
tests/insta360sdk/output/x5_YYYYMMDD_HHMMSS_views/
  little_planet.jpg
  view_front.jpg
  view_right.jpg
  view_back.jpg
  view_left.jpg
  view_up.jpg
  view_down.jpg
```

六个视角默认使用 90° FOV，输出为 1600×1600 JPEG。小行星图默认使用 300° stereographic 投影，输出为 1600×1600 JPEG。

调整视角尺寸和 FOV：

```bash
uv run python tests/insta360sdk/capture_x5.py \
  --view-size 2048 \
  --view-fov 90 \
  --planet-size 2048 \
  --planet-fov 300
```

如果已经有 ERP 全景图，无需重新拍照，可以单独导出：

```bash
uv run python tests/insta360sdk/projections.py \
  tests/insta360sdk/output/x5_20260922_222830.jpg
```

指定派生图片目录：

```bash
uv run python tests/insta360sdk/projections.py \
  tests/insta360sdk/output/x5_20260922_222830.jpg \
  --output-dir tests/insta360sdk/output/demo_views
```

## 成功判据

命令退出码为 `0`，最后输出一段 JSON：

```json
{
  "ok": true,
  "camera": {
    "model": "Insta360 X5"
  },
  "stitching": {
    "used": "ondevice"
  },
  "image": {
    "path": ".../output/x5_20260922_220000.jpg",
    "format": "JPEG",
    "width": 11904,
    "height": 5952
  },
  "projections": {
    "littlePlanet": {
      "path": ".../little_planet.jpg"
    },
    "views": {
      "front": {"path": ".../view_front.jpg"},
      "right": {"path": ".../view_right.jpg"},
      "back": {"path": ".../view_back.jpg"},
      "left": {"path": ".../view_left.jpg"},
      "up": {"path": ".../view_up.jpg"},
      "down": {"path": ".../view_down.jpg"}
    }
  }
}
```

成功必须同时满足：

- 相机和存储卡状态正常；
- 相机报告支持 `ondevice`；
- 拍照命令最终状态为 `done`；
- `results.fileUrl` 可以下载；
- 文件是 JPEG；
- 宽高比接近 2:1。
- 小行星图及六个主要视角均生成成功，且尺寸符合参数。

脚本只校验格式和投影尺寸。第一次实拍后仍建议人工打开图片，确认接缝和方向符合业务要求。

## 本次验证记录

2026-09-22：

- 模拟测试：`8 passed`。
- 实机首次探测：未进入拍照阶段。
- 原因：`192.168.42.1` 当时被路由到 `utun5`（VPN 隧道），`/osc/info` 返回空响应。
- 结论：客户端协议逻辑已通过模拟测试；实机端到端结果仍需按上面的网络前置条件复验，不能标记为实机通过。
- 投影验证：已使用 X5 实拍 ERP 图片验证 FFmpeg stereographic 小行星投影。

## 本次使用的接口

1. `GET /osc/info`：获取型号、序列号和固件版本。
2. `POST /osc/state`：检查存储卡、电量和相机状态。
3. `camera.getOptions`：查询 `photoStitchingSupport`。
4. `camera.setOptions`：设置照片模式和 `ondevice`。
5. `camera.takePicture`：触发拍照。
6. `POST /osc/commands/status`：等待拍照和机内拼接完成。
7. `GET results.fileUrl`：下载最终 JPEG。

所有命令串行发送；收到上一条响应后才发送下一条。状态轮询默认间隔一秒。

## 主服务集成

正式实现已经迁到 `src/insta360_hack/insta360/`，这里的脚本只作为命令行实机验证入口。网页使用以下接口：

```text
POST /api/v1/camera/captures
GET  /api/v1/camera/captures/{capture_id}
GET  /api/v1/camera/captures/{capture_id}/files/{name}
```

拍摄成功后，页面提交 `capture_id` 和用户勾选的 `capture_views` 创建 run。图片始终保留在服务端，不经过浏览器下载再上传。默认选中 ERP、小行星、前后左右和下视图，上视图默认不选。

## 常见错误

- `unactivated`：先用 Insta360 官方 App 激活相机。
- `disabledCommand`：相机不在照片模式；脚本会先发送 `captureMode=image`。
- `noCard`：没有存储卡。
- `noSpace`：存储空间不足。
- `invalidFormat`：存储卡格式不正确。
- `writeProtect`：存储卡写保护。
- `ondevice` 不在支持列表：当前相机或固件无法走本流程，需要 Media SDK 或调整设备方案。
- `Server disconnected without sending a response`：优先检查 `route -n get 192.168.42.1`，通常是 VPN/代理接管路由或尚未连接 X5 Wi-Fi。
- 拍照超时：提高 `--capture-timeout`，并确认相机没有休眠、存储卡写入正常。
- `未找到 FFmpeg`：执行 `brew install ffmpeg`，再用 `ffmpeg -filters | grep v360` 确认投影滤镜可用。
