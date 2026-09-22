# 触见前端

给视障者做空间地图的页面。上传全景和空间说明，看整理后的空间结构，再用 Three.js 预览可触摸的模型。

我们做了一个将视觉空间转化为触觉语言的 AI 空间地图，给视障者使用，解决他们无法通过视觉建立空间认知的问题。

团队口号：真正做到「人人平等」，让残障人士也可以更好的理解世界。

## 页面上有什么

- 已有任务：打开页面就列出 `data/runs` 里的任务。点一条回到那次的原图、空间结构和模型。地址栏带 `?run=`，刷新仍停在这一条。「新任务」清空当前选择。
- 参考图，以及给 DeepSeek 的说明。参考图可以多张，例如全景加行星图，最多 8 张。说明框打开时已填好一段 3D 屋剖面示例，可以改或清空。可以点选、多选、拖入，或按 `Ctrl+V` / `⌘V` 粘贴图片。按下「生成触觉地图」后创建一次 `img-to-3d`。有任务还在进行时不能再开新的。停在确认说明或确认出图时不算正在进行。
- 生成方式默认分步确认。先停在剖面说明，按「用这段说明生成空间结构」才出图；图出来后再按「用这张图生成触觉模型」。全自动则提交后一直做到模型。
- 进度列出后端返回的十个步骤。优化参考图和网格生成进行中显示「已进行」，结束后保留「用时」。
- 全景原图：拍摄到的视觉空间。多张图并排显示。一有地址就显示，本地选中的图会先占这个位置。
- 空间结构：等确认说明时这里是可改的剖面说明。出图后是优化图。优化进行时，这里也显示已经用了多久。
- 触觉模型：只加载 `outputs.model_glb`。网格单面、偏金属，预览时改成双面并加上环境光，从外面也能看见。视障者摸到的是同一份形状，页面不渲染 STL。生成中，预览外圈和右下角计时框有流动光。

`pending` 和 `running` 时每 2 秒查询一次。`awaiting_image` 和 `awaiting_mesh` 停下，点继续后再查。

## 目录

```text
frontend/
  index.html          页面标题和字体
  package.json
  vite.config.ts      5173，把 /api 代理到 127.0.0.1:8000
  src/main.tsx
  src/App.tsx         名称、定位、口号，以及轮询
  src/api.ts          列出、创建和查询 run
  src/meshTime.ts     网格生成用时
  src/types.ts
  src/styles.css
  src/components/
    TaskList.tsx      data/runs 里的任务
    PromptForm.tsx    全景和空间说明
    StageList.tsx     步骤进度
    ImagePanel.tsx    原图和优化图
    GlbViewer.tsx     Three.js 视口
```

构建用 Vite。3D 用 `three` 的 `GLTFLoader` 和 `OrbitControls`。

## 启动

仓库根目录：

```bash
./scripts/dev.sh
```

脚本会在需要时安装前端依赖。启动前先结束占用 `8000` 和 `5173` 的旧进程，再后台启动后端、前台启动前端。后端没起来时不启动前端。`Ctrl+C` 同时停下两边。

只开前端时，后端要已经在 `8000`：

```bash
npm run dev --prefix frontend
```

页面请求走相对路径 `/api/v1/...`，不使用厂商的临时地址。

## 接口

| 动作 | 接口 |
|------|------|
| 已有任务 | `GET /api/v1/runs` |
| 创建 | `POST /api/v1/runs`，表单字段 `workflow_id=img-to-3d`、`prompt`、`image`、`mode`（`confirm` 或 `auto`） |
| 确认说明后出图 | `POST /api/v1/runs/{id}/image`，JSON `{ "prompt" }`，只在 `awaiting_image` 时可用 |
| 确认后继续做模型 | `POST /api/v1/runs/{id}/mesh`，只在 `awaiting_mesh` 时可用 |
| 进度 | `GET /api/v1/runs/{id}` |
| 图片和模型 | `GET /api/v1/runs/{id}/files/{name}` |

`outputs.reference_image`、`outputs.optimized_image`、`outputs.model_glb` 有路径就显示，不必等整个任务结束。
