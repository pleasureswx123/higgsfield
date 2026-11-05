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

日常推荐：**PostgreSQL / Redis → 一条命令启动 API 与工作器 → 制作端前端**。管理端前端按需启动。

基础设施就绪后，在工程根目录执行：

```powershell
cd D:\laputta\higgsfield
.\scripts\start-local.ps1
```

脚本先确认工作器就绪，再在当前终端启动 API；保持终端开启。重复执行不会重复启动已有工作器，API 端口已占用时也不会启动第二个 API，但需要确认占用端口的是本工程。API 热重载、Ctrl+C 停止 API 不会重启或停止工作器。该命令不启动 Docker、不执行迁移、不安装依赖、不启动前端。

查看状态：

```powershell
.\scripts\start-local.ps1 -Action status
```

下面保留各组件独立启动方式，使用统一入口后无需再重复执行第 2、3 步。

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

`就绪，数据库连接正常` 表示工作器进程存在、健康心跳未过期且数据库探测成功，不代表供应商调用一定成功，也不代表已有任务实际执行成功；`未运行` 表示没有检测到对应进程。启动后会消费已有待执行任务，可能调用供应商，不需要为同一任务再次点击生成。

日志位于 `ruoyi-fastapi-backend\output\image-workers\模式-实例ID`，包含 `err.log`、`out.log`、`status.json`。脚本只管理由它启动并记录的工作器；通过其他终端手动启动的工作器需在原终端管理。

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

**只重启 API 或刷新浏览器，不会更新独立工作器内存中的代码。** `start` 会保留已有进程；更新代码或并发配置后，使用 `restart`。

新启动的工作器支持安全停止：先停止领取新任务，再等待在途任务。执行：

```powershell
cd D:\laputta\higgsfield\ruoyi-fastapi-backend
$workerModes = @('image', 'image-recovery', 'video', 'archive', 'billing', 'image-thumbnail', 'credential-test')

..\scripts\image-workers.ps1 -Action restart -Modes $workerModes -WaitSeconds 30
..\scripts\image-workers.ps1 -Action status -Modes $workerModes
```

最后应全部显示“就绪”。只重启部分工作器时，调整 `$workerModes` 即可。

`-WaitSeconds 30` 是命令等待时间，不是生成超时。超过后脚本会提示仍在安全停机，**不会强杀或启动重复进程**；稍后查看 `status`，退出后再执行 `start`。工作器自己的停机等待上限由 `drainSeconds` 控制，默认 1200 秒；到期会取消本地协程，已发送请求仍按结果未知/租约恢复规则处理，不能推断供应商停止或自动重发。关闭详情和浏览器不取消后台任务。

旧版脚本启动的进程没有控制目录，不能接受新的安全停止指令。本脚本会明确拒绝强杀；首次切换应在确认无在途任务后由原启动方式停止旧进程，再使用新入口启动。本次代码升级不会自动操作已运行的进程。

### 并发、唤醒与公平调度

配置文件：[scripts/worker-settings.json](scripts/worker-settings.json)。`concurrency` 对生成工作器表示本地并发，对部分辅助工作器表示批量大小，不保证每种模式均并行执行。当前初始值：图片 2、视频 4、归档 2、图片恢复 1、费用批量 10、缩略图批量 2、凭据测试 1。它们是保守起点，不是经供应商或机器压测得出的最优值；图片处理内存上限与并发相乘后需适合本机容量。供应商账号的共享容量控制继续生效，不能靠增加本地并发绕过账号限制。

生成任务提交与状态迁移会在同一事务中发送 PostgreSQL 通知，事务提交后唤醒生成/归档常驻调度器；断线重连先监听后补查，同时保留一秒兜底，覆盖通知丢失、视频查询到期与租约恢复。辅助工作器仍保留各自原有扫描周期。通知只含唤醒信号，不包含提示词、凭据或媒体，按数据库 schema 隔离。

图片/视频准备阶段按用户最近领取时间轮转，单批次交错领取；无竞争时可使用全部空闲名额。公平性只作用于尚未开始的任务，不抢占在途请求，供应商无容量的任务仍需等待。领取事务用数据库锁协调多个进程；最多向后检查一批候选，满额账号的任务延后再试，不无限扫描。

验证命令（模拟供应商与隔离 schema，不调用真实生成接口）：

```powershell
cd D:\laputta\higgsfield
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/workers.test.ps1
cd ruoyi-fastapi-backend
.\.venv\Scripts\python.exe -m unittest tests.test_worker_scheduling.SchedulingTests tests.test_generation_pipeline_latency.DispatchTests -v
$env:HF_RUN_DB_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest tests.test_worker_scheduling.FairSchedulingTests tests.test_higgsfield_generation_worker -v
Remove-Item Env:HF_RUN_DB_TESTS
```

数据库测试需数据库账户具备创建测试 schema 的权限，测试结束清理其独立 schema，不操作原有项目素材。启动脚本测试只使用临时工程与模拟进程。正式供应商限制、真实负载 P95 和 NAS 吞吐仍需另行验证。

本节为本地开发启动说明；正式部署应使用服务管理工具管理启动和重启，不从本地命令推断正式部署方式。

产品概述于2026-11-03按源码基线fdf3f612同步，本地启动说明于2026-11-05按当前脚本补充。文档和代码检查不代表已完成正式供应商、NAS与全部浏览器验收。历史逐次开发记录见[旧README](docs/历史版本/2026-11-03同步前/README.md)。
