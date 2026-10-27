# 后端工程强制约束

以中文沟通，文档、代码注释和 docstring 以中文为主。遵循本目录实际框架，不另建平行后端架构。

- 技术栈：FastAPI、异步 SQLAlchemy 2.0、AsyncSession、Redis、JWT/OAuth2 Bearer；数据库已再次确认使用 PostgreSQL，不改为 MySQL。
- 分层：controller（router）→ service → dao → entity/do（ORM model），请求和响应 VO 放 entity/vo。Controller 不写 SQL，DAO 不生成 HTTP 响应，Service 管理业务事务。
- 响应、分页、异常、全局拦截复用 ResponseUtil、PageModel/PageResponseModel、PageUtil、框架异常与中间件；不自建 error 信封或列表游标协议。流与文件遵循框架流式处理。
- Authorization: Bearer 平台 token 复用现有登录链；用户及权限 Redis 缓存须有退出、停用和授权变更失效机制。菜单/按钮/数据权限、字典复用框架。
- 新业务只用异步 AsyncSession；DAO await execute/flush，Service commit/rollback；不同请求/并发任务不共享会话。外部长耗时调用不持有数据库事务。
- 表名下划线、bigint 自增主键、若依审计公共字段、del_flag 删除策略、无物理外键、表和字段中文注释；复用 Base/Mixin，迁移不得用 create_all 替代。
- 日志、导出、限流、缓存及参数配置遵循框架既有实现，秘密不得进入普通日志、字典、系统参数或前端。

细则见 [后端编码与框架对齐规范](../docs/后端编码与框架对齐规范.md)及[平台 API 契约](../docs/平台API契约.md)。源码现状与待实现能力必须区分。是否实现代码以用户当前授权为准。

PostgreSQL 专项要求：新增业务 DDL、字段类型和迁移禁止 MySQL 专属语法（反引号、AUTO_INCREMENT、ENGINE、UNSIGNED、ON DUPLICATE KEY UPDATE 等）；表及字段注释使用 COMMENT ON TABLE/COLUMN。保留框架其他数据库参考文件，但不得作为本项目迁移入口。项目统一约束见[根目录 AGENTS.md](../AGENTS.md)。
