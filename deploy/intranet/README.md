# 内网正式环境

制作端使用服务器的 80 端口，管理端使用 8080 端口。Nginx 提供两个前端，并将 API 请求转交给同一后端。PostgreSQL、Redis、API 和九个工作器都运行在 Docker 内。服务器通过 systemd 管理 NAS 挂载、开机启动与数据库定时备份。

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
