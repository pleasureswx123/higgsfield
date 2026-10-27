# higgsfield-ai

基于 RuoYi-FastAPI 开发的 AI 制作平台，包含管理平台与制作平台两个前端。后端使用 Python FastAPI，数据库统一使用 PostgreSQL。

本地开发方式：**Docker 仅运行 PostgreSQL 和 Redis；后端、管理前端、制作前端分别在宿主机手动启动。** 本文命令使用 Windows PowerShell，项目目录为 `D:\laputta\higgsfield`。

## 项目结构与当前状态

| 目录 / 文件 | 用途与状态 |
|---|---|
| `ruoyi-fastapi-backend/` | 后端框架，FastAPI + 异步 SQLAlchemy + Redis + JWT/OAuth2 |
| `ruoyi-fastapi-frontend/vue3/web/` | Vue3 管理平台，基于现有 RuoYi 管理工程 |
| `higgsfield-frontend/` | 制作平台待初始化，目前仅有 `AGENTS.md`，尚无应用代码和 `package.json` |
| `docker-compose.local.yml` | 本地 PostgreSQL、Redis 配置 |
| `.env.local-infra.example` | 本地基础设施环境变量示例 |
| `docs/` | 已有需求、架构、开发与部署文档 |
| `AGENTS.md` | 项目技术栈、编码规范及 RuoYi 能力参考规则 |

制作端业务尚未实现；框架现有能力不等于制作平台业务已完成。其他前端版本、MySQL 配置和全栈 Compose 保留为框架参考，不作为本项目本地启动入口。

## 本地启动顺序

1. 配置环境变量，启动 PostgreSQL 与 Redis。
2. 配置并启动后端。
3. 在另一个终端启动管理平台 Web 前端。
4. 制作平台待工程初始化后再启动。

| 服务 | 本地地址 / 端口 |
|---|---|
| PostgreSQL | `127.0.0.1:35432` → 容器 `5432` |
| Redis | `127.0.0.1:36379` → 容器 `6379` |
| 后端 | `http://127.0.0.1:9099` |
| 后端接口文档 | `http://127.0.0.1:9099/docs` |
| 管理平台 | `http://127.0.0.1:5173`，按下方启动参数固定 |
| 制作平台 | 待初始化，约定开发端口 `5174` |

基础设施沿用 PostgreSQL 14、Redis 7.4。后端按 Python 3.12 准备本地虚拟环境。管理端 `package.json` 要求 Node.js `^22.22.2 || ^24.15.0`、pnpm `11.28.6`。

## 1. Docker 启动 PostgreSQL 与 Redis

### 首次配置

在项目根目录执行：

```powershell
Set-Location D:\laputta\higgsfield

# 仅首次复制，不覆盖已有配置。
if (-not (Test-Path .env.local-infra)) {
  Copy-Item .env.local-infra.example .env.local-infra
}
notepad .env.local-infra
```

填写并保存以下配置，密码使用本机独立随机密码，不保留占位文字：

```dotenv
LOCAL_PG_PASSWORD=替换为本机独立随机密码
LOCAL_PG_PORT=35432
LOCAL_REDIS_PORT=36379
```

真实环境文件已加入 Git 忽略列表。PostgreSQL 数据库为 `higgsfield_ai_dev`，用户为 `higgsfield_dev`。Redis 仅绑定本机回环，无密码，后端使用逻辑库 `2`。

### 启动、查看状态和日志

由开发者在项目根目录手动执行：

```powershell
Set-Location D:\laputta\higgsfield

docker compose --env-file .env.local-infra -f docker-compose.local.yml config --quiet
if ($LASTEXITCODE -ne 0) { throw '请先修正 Compose 配置' }

docker compose --env-file .env.local-infra -f docker-compose.local.yml up -d postgres redis
docker compose --env-file .env.local-infra -f docker-compose.local.yml ps
docker compose --env-file .env.local-infra -f docker-compose.local.yml logs --tail 80 postgres redis
```

等待两个服务显示 `healthy`。持续查看日志可执行：

```powershell
docker compose --env-file .env.local-infra -f docker-compose.local.yml logs -f --tail 80 postgres redis
```

`Ctrl+C` 仅退出日志查看。首次启动会在专属空数据卷中导入框架 PostgreSQL 初始化 SQL；该脚本含删表语句，不要手工重跑到已有数据库。框架种子初始化不替代后续业务数据库迁移，数据核验见[本地开发手册第 5 节](docs/本地开发与工程初始化手册.md#5-框架数据库初始化与验证)。

Compose 顶层项目名为 `higgsfield-ai-local`，容器、网络及数据卷自动使用该项目名称隔离。不要用 `-p` 或 `COMPOSE_PROJECT_NAME` 覆盖它。若端口冲突，调整 `.env.local-infra` 和后端对应端口，不停止其他项目服务。

### 数据持久化、停止和再次启动

| 数据 | Docker 命名卷 | 容器内目录 |
|---|---|---|
| PostgreSQL | `higgsfield-ai-local_pg_data` | `/var/lib/postgresql/data` |
| Redis（开启 AOF） | `higgsfield-ai-local_redis_data` | `/data` |

命名卷由 Docker 管理，保存在 Docker Desktop 的 Linux 数据磁盘中，不在项目源码目录内。

```powershell
# 停止服务，保留容器和数据。
docker compose --env-file .env.local-infra -f docker-compose.local.yml stop postgres redis

# 再次启动已存在的容器。
docker compose --env-file .env.local-infra -f docker-compose.local.yml start postgres redis
```

若修改了 Compose 配置，使用前面的 `up -d postgres redis` 应用变更。不要执行 `down -v` 或 `volume prune`，以免删除持久化数据。修改环境文件密码不会自动修改已有数据库角色的密码。

## 2. 后端服务启动步骤

### 安装依赖（首次或依赖变更时）

```powershell
Set-Location D:\laputta\higgsfield\ruoyi-fastapi-backend

# 查看已安装的 Python 版本。
py -0p

# 首次创建虚拟环境；已有 .venv 时跳过此行。
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-pg.txt
.\.venv\Scripts\python.exe -m pip check
```

### 配置开发环境

首次克隆后，在后端目录执行以下命令复制示例；已有配置时不会覆盖：

```powershell
if (-not (Test-Path .env.dev)) {
  Copy-Item .env.dev.example .env.dev
}
```

编辑后端目录的 `.env.dev`，替换示例密码与 JWT 密钥，保留其他已有配置，核对以下字段：

```dotenv
APP_ENV=dev
APP_HOST=127.0.0.1
APP_PORT=9099
APP_ROOT_PATH=
DB_DEFAULT_SOURCE=primary
DB_SOURCES={"primary":{"db_type":"postgresql","db_host":"127.0.0.1","db_port":35432,"db_username":"higgsfield_dev","db_password":"替换为LOCAL_PG_PASSWORD的实际值","db_database":"higgsfield_ai_dev","db_echo":false}}
REDIS_HOST=127.0.0.1
REDIS_PORT=36379
REDIS_USERNAME=
REDIS_PASSWORD=
REDIS_DATABASE=2
```

`DB_SOURCES` 必须是一行合法 JSON，密码与根目录 `.env.local-infra` 中的实际值一致；含引号或反斜线时需正确转义。后端不会自动读取基础设施环境文件，不使用旧式 `DB_HOST` 等变量代替 `DB_SOURCES`。JWT 等其他配置沿用已有框架配置方式，开发密钥使用本机独立值。

### 运行后端

确认 PostgreSQL、Redis 已启动并完成初始化核验，再执行：

```powershell
Set-Location D:\laputta\higgsfield\ruoyi-fastapi-backend
.\.venv\Scripts\ruoyi.exe app run --env=dev
```

保留终端查看日志，`Ctrl+C` 停止。接口文档地址：`http://127.0.0.1:9099/docs`。此命令会实际连接数据库和 Redis，并执行框架启动初始化；不要将 `.env.dev` 指向其他项目或生产数据库。

## 3. 管理平台 Web 前端启动步骤

在另一个 PowerShell 终端执行：

```powershell
Set-Location D:\laputta\higgsfield\ruoyi-fastapi-frontend\vue3\web

# 检查 Node.js；首次安装或版本不符时安装指定 pnpm。
node --version
npm install -g pnpm@11.28.6
pnpm --version

# 安装依赖，沿用仓库锁文件。
pnpm install --frozen-lockfile --registry=https://registry.npmmirror.com

# 启动管理平台。
pnpm run dev --host 127.0.0.1 --port 5173 --strictPort
```

访问 `http://127.0.0.1:5173`。已安装指定 pnpm 且依赖没有变更时，直接执行最后一条启动命令。

现有 `pnpm run dev` 会运行 Vite，但框架默认配置使用 `80` 端口；这里显式固定为本项目约定的 `5173`，并在占用时报错，避免自动换端口。开发代理将 `/dev-api` 请求转发到 `http://127.0.0.1:9099`。`Ctrl+C` 停止前端。

## 4. 制作平台 higgsfield-frontend

**制作平台尚未初始化。** `higgsfield-frontend/` 当前仅有开发规范文件 `AGENTS.md`，没有 `package.json`、页面或启动脚本，暂不能执行 `pnpm install` 或 `pnpm run dev`。

后续按 Vue3 + TypeScript + Vue Router + Pinia + Axios 架构实现，业务组件使用 `<script setup lang="ts">`，支持亮色与暗黑主题。具体规范见[制作端 AGENTS.md](higgsfield-frontend/AGENTS.md)。

## 开发约定与资料

- 项目约束见[AGENTS.md](AGENTS.md)。参考 RuoYi 代码生成、表单构建、系统接口、菜单权限的功能设计，实际实现及生成代码仍使用 FastAPI、Vue3 setup、PostgreSQL，不生成 Java/Spring Boot 后端。
- 更完整的环境配置、数据核验及故障定位见[本地开发手册](docs/本地开发与工程初始化手册.md)。
- 正式环境面向公司内网服务器，媒体长期保存到公司 NAS；本地 Compose 不作为正式部署方案。
- 本项目基于 RuoYi-FastAPI，保留其框架来源与[许可证](LICENSE)。

本文按仓库配置整理启动步骤，不代表服务已启动或业务联调已通过。
