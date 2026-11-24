# 内网正式环境

制作端使用服务器的 80 端口，管理端使用 8080 端口。Nginx 提供两个前端，并将 API 请求转交给同一后端。PostgreSQL、Redis、API 和九个工作器都运行在 Docker 内。服务器通过 systemd 管理 NAS 挂载、开机启动与数据库定时备份。

## Windows 日常发布与回退

在开发电脑上双击同目录的[发布.cmd](发布.cmd)，输入远端 `main` 的 Git 提交号，或输入 `main` 选择当时的最新提交。需要回到上一成功版本时双击[回退.cmd](回退.cmd)。看到“当前版本”后即可核对结果。

也可以在仓库根目录用 PowerShell 发布指定版本：

```powershell
.\deploy\intranet\发布.cmd 06b275a
```

需要回退时单独运行：

```powershell
.\deploy\intranet\回退.cmd
```

发布使用项目的 Python 3.12 虚拟环境、Git、pnpm、SSH 和 SCP。电脑需要能读取远端仓库并免密连接内网服务器。目标提交须包含正式 Dockerfile、两个前端和内网部署配置。脚本从提交对象单独构建，不会打包开发数据库、本机环境配置或工作区未提交改动。

第一次运行会保存在线应用的基线。服务器在 `/opt/higgsfield/versions` 保留可切回的页面、配置和镜像标识，在 `release-state.json` 记录当前版和上一版。请保留这些目录和对应 Docker 镜像。以后只构建发生变化的应用；发布已准备好的版本可直接复用。纯前端更新先放新资源、最后切换首页。后端更新前检查在途生成任务，切换期间网页可能短暂不可用。脚本最后核对两个入口的首页内容、API 和 Compose 健康状态。发布日志可用脚本显示的任务名查询：

```sh
journalctl -u <发布任务名> --no-pager
```

回退切换应用版本，保留正式库、NAS 文件和现场密钥。需要变更数据库结构的提交，应先在副本验证上一版也能使用升级后的结构，再在该提交的 `deploy/intranet/compatible-migrations.json` 中声明经过验证的修订号对，例如 `[["旧修订号","新修订号"]]`。脚本在迁移前备份，执行 Alembic 升级并核对结果；回退应用时不执行数据库降级。数据库、Redis 的容器配置及宿主机挂载、自启单元变更应作为独立运维变更处理。首次部署用的管理配置导入不会在日常发布中执行。

发布中断时先查看任务日志。在服务器上已开始的任务会继续执行；下次运行也会检查上次切换是否完整。若数据库停在未经验证的中间修订号，请按日志修复迁移后再恢复应用，避免覆盖发布期间产生的数据。

## 查看运行状态

```sh
cd /opt/higgsfield/current
systemctl status higgsfield.service mnt-higgsfield.mount --no-pager
docker compose ps
docker compose logs --tail 60 api
systemctl list-timers higgsfield-backup.timer
```

正式数据库和 Redis 使用服务器的独立数据盘。正式媒体使用 NAS 的 `NightmareTheatre/prod`。项目文件夹中的文件供人浏览，`.platform` 管理原始对象和目录映射。开发环境使用独立的 `dev` 目录。项目及素材增删改名请在制作端操作。

## 配置和备份

首次发布从本地管理库选择配置导入正式库，并使用正式环境密钥重新加密供应商凭据。日常配置在正式管理后台维护。`import_settings.py` 仅供首次初始化全新正式库使用。

服务器时间每天 02:15 备份正式数据库，先写入 `/mnt/data/higgsfield/backups`，再复制到 NAS 的 `prod/.platform/database-backups` 并核对内容。手动运行可用 `systemctl start higgsfield-backup.service`。媒体原件由 NAS 保存。恢复整套服务还需要对应时间的 NAS 文件、发布版本及服务器 `/etc/higgsfield` 内的密钥。恢复演练应将数据库备份还原到独立的数据库名，避免覆盖在线数据。

管理员通过服务器 root 权限读取初始登录资料。修改密码后，以后台设置的新密码为准。不要将服务器的环境文件、供应商凭据或初始登录资料复制到代码库。
