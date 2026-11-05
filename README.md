# Higgsfield AI 图片与视频制作平台

公司内部AI制作平台：统一接入模型，围绕项目上传/生成素材、复用元素、制作视频，并记录真实用量和费用。

## 文档入口

- [完整产品PRD](docs/AI图片与视频制作平台PRD-全流程版.md)：角色、项目和全生产流程，适合管理层阅读。
- [对应当前代码的技术方案](docs/技术架构方案.md)：C4、流程图、时序图及源码映射。
- [当前交付与验收边界](docs/当前交付状态.md)、[人工验收步骤](docs/人工验收操作手册.md)。
- [全部文档索引](docs/文档一致性与优先级索引.md)。

## 工程组成

| 路径 | 职责 |
|---|---|
| higgsfield-frontend | Vue3 + TypeScript 制作端 |
| ruoyi-fastapi-frontend/vue3/web | Vue3 管理端 |
| ruoyi-fastapi-backend | FastAPI共享后端、异步工作器、PostgreSQL迁移 |
| docs | 当前规范、业务技术方案及历史证据 |

本地PostgreSQL/Redis为Docker基础设施，应用在宿主机运行；不得未经授权启动Docker。正式环境计划内网服务器与NAS，具体部署仍需确认。

当前按实际用量事后计费，无预算预占；模型启用后全平台可用，但保留项目成员权限。角色层级Owner≥负责人≥制作人≥查看者。图片与视频生成结果保存为项目素材并关联提交目录。

## 本地日常启动（Windows PowerShell）

以下命令用于已经完成依赖安装、数据库初始化和配置的开发环境，示例项目位置为 `D:\laputta\higgsfield`。需要已有 `.env.local-infra`、后端 `.env.dev`、后端 `.venv` 和两个前端的依赖；数据库配置需与本地 Docker 基础设施一致。日常启动不需要重新初始化数据库或删除数据卷。

启动顺序：**PostgreSQL / Redis → 后端 API → 工作器 → 制作端前端**。管理端前端按需启动。工作器和前端之间没有严格的先后依赖，但开始生成前应确认工作器已运行。

### 1. 启动 PostgreSQL 和 Redis

先打开 Docker Desktop，等待 Docker 可用，再执行：

```powershell
cd D:\laputta\higgsfield
docker compose --env-file .env.local-infra -f docker-compose.local.yml up -d postgres redis
docker compose --env-file .env.local-infra -f docker-compose.local.yml ps
```

确认两个服务均为运行且健康状态。此 Compose 文件只启动基础设施，不会启动 API、工作器或前端。

### 2. 启动后端 API（单独一个终端，保持运行）

```powershell
cd D:\laputta\higgsfield\ruoyi-fastapi-backend
.\.venv\Scripts\ruoyi.exe app run --env=dev
```

API 负责登录、项目管理、接收生成请求及查询状态。**这条命令不会同时启动生成工作器。**

### 3. 启动工作器（另开一个 PowerShell 窗口）

```powershell
cd D:\laputta\higgsfield\ruoyi-fastapi-backend
..\scripts\image-workers.ps1 -Action status
..\scripts\image-workers.ps1 -Action start
..\scripts\image-workers.ps1 -Action status
```

脚本在后台启动以下工作器，并输出进程状态；API 终端仍需保持运行。

| 工作器 | 职责 |
|---|---|
| `image` | 图片生成 |
| `image-recovery` | 图片响应证据恢复处理 |
| `video` | 视频生成提交与状态查询 |
| `archive` | 生成结果下载归档 |
| `billing` | 用量费用处理 |
| `image-thumbnail` | 图片缩略图处理 |
| `credential-test` | 执行管理端主动提交的供应商测试任务 |

`运行中，PID …` 表示脚本管理的进程存在，不代表供应商调用一定成功；`未运行` 表示没有检测到对应进程。启动后会消费已有待执行任务，可能调用供应商，不需要为同一任务再次点击生成。

日志位于 `ruoyi-fastapi-backend\output\image-workers`。启动失败时查看对应模式最新的 `.err.log` 和 `.out.log`。脚本只管理由它启动并记录的工作器；通过其他终端手动启动的工作器需在原终端管理。

### 4. 启动制作端前端（另开终端，保持运行）

```powershell
cd D:\laputta\higgsfield\higgsfield-frontend
pnpm dev --port 5174
```

浏览器访问 `http://localhost:5174`，实际端口以终端输出为准。

### 5. 启动管理端前端（按需，另开终端）

```powershell
cd D:\laputta\higgsfield\ruoyi-fastapi-frontend\vue3\web
pnpm dev --port 5173
```

浏览器访问 `http://localhost:5173`，用于配置供应商、模型和查看调用记录，实际端口以终端输出为准。

### 修改代码后如何重启工作器

**只重启 API 或刷新浏览器，不会更新独立工作器内存中的代码。** `start` 会保留已经运行的进程，因此更新工作器需要先停止再启动。

先确认没有正在生成、等待供应商响应或保存结果的任务，再执行：

```powershell
cd D:\laputta\higgsfield\ruoyi-fastapi-backend
$workerModes = @('image', 'image-recovery', 'video', 'archive', 'billing', 'image-thumbnail', 'credential-test')

..\scripts\image-workers.ps1 -Action stop -Modes $workerModes
..\scripts\image-workers.ps1 -Action start -Modes $workerModes
..\scripts\image-workers.ps1 -Action status -Modes $workerModes
```

最后应全部显示“运行中”。只重启部分工作器时，调整 `$workerModes` 中的模式即可。停止脚本直接终止对应进程，执行中的请求可能变成结果未确认，因此不要在请求尚未返回时重启。关闭生成详情或浏览器不会取消后台任务。

本节为本地开发启动说明；正式部署应使用服务管理工具管理启动和重启，不从本地命令推断正式部署方式。

产品概述于2026-11-03按源码基线fdf3f612同步，本地启动说明于2026-11-05按当前脚本补充。文档和代码检查不代表已完成正式供应商、NAS与全部浏览器验收。历史逐次开发记录见[旧README](docs/历史版本/2026-11-03同步前/README.md)。
