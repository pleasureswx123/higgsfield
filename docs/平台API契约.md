# 平台 API 契约 · 当前路由索引

更新：2026-11-03。本清单从当前 Controller 声明提取，不表示每个历史接口都属于首期用户入口或已完成HTTP验收。字段、约束和响应以对应VO、Service及运行实例OpenAPI为准。

## 公共契约

复用RuoYi Bearer鉴权、统一响应、分页与异常；项目操作在Service检查有效成员及对象范围。写入按相应接口的幂等键和revision约定处理，不使用通用重试创建新的付费请求。密钥与完整临时签名不进入普通用户响应。

## 当前生产主链

POST /api/v1/generations/validate只验证受理条件；POST /api/v1/generations创建并持久化任务；GET列表/详情/input读取授权数据；retry-archive只重试已有输出保存。当前actual_usage路径不支持取消，尽管Controller仍保留历史cancel声明；预算相关路由也不属于当前必经流程。不能仅根据接口summary里的历史文字重启预算或取消功能。

## 源码路由目录

| 方法 | 声明路径 | 源码摘要（可能含历史模块） | Controller |
|---|---|---|---|
| GET | `/api/v1/projects/{project_id}/library` | 分页读取当前目录素材 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| POST | `/api/v1/projects/{project_id}/library/move` | 移动素材目录归属 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| POST | `/api/v1/projects/{project_id}/library/copy` | 复制素材到目标目录 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| PATCH | `/api/v1/assets/{asset_id}/status` | 修改素材工作状态 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| GET | `/api/v1/asset-versions/{version_id}/document-text` | 授权文档纯文本预览 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| GET | `/api/v1/asset-versions/{version_id}/thumbnail` | 授权读取素材图片缩略图 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| HEAD | `/api/v1/asset-versions/{version_id}/thumbnail` | 授权读取素材缩略图元数据 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| GET | `/api/v1/asset-versions/{version_id}/preview` | 授权媒体预览 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| HEAD | `/api/v1/asset-versions/{version_id}/preview` | 授权预览元数据 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| GET | `/api/v1/asset-versions/{version_id}/download` | 授权媒体下载 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| HEAD | `/api/v1/asset-versions/{version_id}/download` | 授权下载元数据 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| POST | `/api/v1/uploads` | 创建本人上传会话 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| GET | `/api/v1/uploads/{upload_id}` | 查询本人上传进度 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| PUT | `/api/v1/uploads/{upload_id}/parts/{part_no}` | 上传并验证不可覆盖分片 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| POST | `/api/v1/uploads/{upload_id}/complete` | 校验完整媒体并归档 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| DELETE | `/api/v1/uploads/{upload_id}` | 取消未绑定上传 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| POST | `/api/v1/assets` | 将上传原子绑定为素材 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| POST | `/api/v1/assets/{asset_id}/versions` | 追加素材不可变版本 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| GET | `/api/v1/asset-versions/{version_id}` | 读取授权素材固定版本详情 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| GET | `/api/v1/assets/{asset_id}` | 读取授权素材详情 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| PATCH | `/api/v1/assets/{asset_id}` | 重命名素材身份 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| DELETE | `/api/v1/assets/{asset_id}` | 逻辑删除素材并保留历史文件 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| POST | `/api/v1/assets/{asset_id}/restore` | 恢复素材身份及原目录归属 | [asset_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/asset_controller.py) |
| GET | `/api/admin/v1/audit-logs` | 分页读取管理范围内的业务审计 | [audit_read_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/audit_read_controller.py) |
| GET | `/api/admin/v1/usage/summary` | 按管理范围汇总项目费用与采用用量 | [billing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/billing_controller.py) |
| GET | `/api/admin/v1/billing-events` | 按管理范围分页筛选项目费用 | [billing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/billing_controller.py) |
| GET | `/api/admin/v1/billing-events/{event_id}` | 按费用管理范围读取计价明细与调整历史 | [billing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/billing_controller.py) |
| POST | `/api/admin/v1/billing-events/{event_id}/adjustments` | 追加费用调整并同步原预算账本 | [billing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/billing_controller.py) |
| GET | `/api/admin/v1/billing-subjects/{subject_id}` | 读取尚未计价的非项目消耗 | [billing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/billing_controller.py) |
| GET | `/api/admin/v1/budgets` | 按管理范围分页读取预算定义 | [budget_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/budget_controller.py) |
| POST | `/api/admin/v1/budgets` | 创建明确口径的预算定义 | [budget_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/budget_controller.py) |
| PUT | `/api/admin/v1/budgets/{budget_id}` | 启停预算，不释放已有预占 | [budget_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/budget_controller.py) |
| GET | `/api/admin/v1/budgets/{budget_id}/periods` | 分页读取预算周期余额 | [budget_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/budget_controller.py) |
| POST | `/api/admin/v1/budgets/{budget_id}/periods` | 初始化预算周期及额度账本 | [budget_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/budget_controller.py) |
| POST | `/api/admin/v1/budget-periods/{period_id}/adjust-limit` | 追加额度变动，不修改已用金额 | [budget_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/budget_controller.py) |
| GET | `/api/admin/v1/budget-periods/{period_id}/ledger` | 分页读取预算不可变账本 | [budget_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/budget_controller.py) |
| POST | `/api/v1/comment-threads` | 创建固定版本评论主题 | [comment_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/comment_controller.py) |
| GET | `/api/v1/comment-threads` | 分页读取授权目标评论主题 | [comment_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/comment_controller.py) |
| GET | `/api/v1/comment-threads/{identity}/comments` | 读取主题内评论与回复 | [comment_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/comment_controller.py) |
| POST | `/api/v1/comment-threads/{identity}/comments` | 发表评论或同主题回复 | [comment_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/comment_controller.py) |
| PATCH | `/api/v1/comments/{identity}` | 作者或治理人员原子更新评论与标注 | [comment_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/comment_controller.py) |
| DELETE | `/api/v1/comments/{identity}` | 作者或治理人员逻辑删除评论并保留回复 | [comment_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/comment_controller.py) |
| PATCH | `/api/v1/comment-threads/{identity}` | 解决、重开或逻辑删除讨论 | [comment_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/comment_controller.py) |
| PATCH | `/api/v1/comments/{identity}/reaction` | 设置当前用户的表情回应 | [comment_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/comment_controller.py) |
| GET | `/api/admin/v1/cost-centers` | 读取可用管理成本中心 | [cost_center_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/cost_center_controller.py) |
| GET | `/api/admin/v1/credentials` | 分页查询凭据身份 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| GET | `/api/admin/v1/credentials/{credential_id}` | 读取凭据非秘密元数据 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| GET | `/api/admin/v1/credentials/{credential_id}/versions` | 分页读取脱敏凭据版本 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| POST | `/api/admin/v1/credentials` | 登记凭据与首个加密草稿版本 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| POST | `/api/admin/v1/credentials/{credential_id}/versions` | 创建凭据轮换草稿，保留旧版本 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| POST | `/api/admin/v1/credential-versions/{version_id}/drain` | 排空凭据版本，保留在途依赖 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| POST | `/api/admin/v1/credential-versions/{version_id}/disable` | 无在途任务后停用凭据版本 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| POST | `/api/admin/v1/credential-versions/{version_id}/revoke` | 本地紧急撤销凭据版本，不认定上游已停止 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| POST | `/api/admin/v1/credential-versions/{version_id}/activate` | 依据当前配置的成功测试启用草稿凭据 | [credential_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_controller.py) |
| GET | `/api/admin/v1/credential-test-runtime` | 读取测试后台服务就绪状态 | [credential_test_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_test_controller.py) |
| GET | `/api/admin/v1/credential-tests/{test_id}/details` | 只读查看脱敏请求和保存的响应 | [credential_test_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_test_controller.py) |
| GET | `/api/admin/v1/credential-versions/{version_id}/test-preview` | 只读预览测试请求，不调用供应商 | [credential_test_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_test_controller.py) |
| GET | `/api/admin/v1/credential-tests/{test_id}/video` | 授权读取已归档的测试视频 | [credential_test_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_test_controller.py) |
| POST | `/api/admin/v1/credential-versions/{version_id}/tests` | 受理凭据测试，不代表测试通过 | [credential_test_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_test_controller.py) |
| GET | `/api/admin/v1/credential-tests/{test_id}` | 读取凭据测试状态 | [credential_test_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_test_controller.py) |
| GET | `/api/admin/v1/credential-versions/{version_id}/tests` | 分页读取当前凭据版本的测试历史 | [credential_test_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_test_controller.py) |
| GET | `/api/admin/v1/credential-versions/{version_id}/test-models` | 分页读取同连接区域的图片测试候选 | [credential_test_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/credential_test_controller.py) |
| POST | `/api/admin/v1/document-uploads` | 创建本人上传会话 | [document_upload_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/document_upload_controller.py) |
| GET | `/api/admin/v1/document-uploads/{upload_id}` | 查询本人上传进度 | [document_upload_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/document_upload_controller.py) |
| PUT | `/api/admin/v1/document-uploads/{upload_id}/parts/{part_no}` | 上传并验证不可覆盖分片 | [document_upload_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/document_upload_controller.py) |
| POST | `/api/admin/v1/document-uploads/{upload_id}/complete` | 校验管理文档并归档 | [document_upload_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/document_upload_controller.py) |
| GET | `/api/v1/drafts` | 分页读取当前项目下本人私有草稿摘要 | [draft_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/draft_controller.py) |
| POST | `/api/v1/drafts` | 创建本人私有生成草稿 | [draft_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/draft_controller.py) |
| GET | `/api/v1/drafts/{draft_id}` | 读取本人私有生成草稿 | [draft_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/draft_controller.py) |
| PUT | `/api/v1/drafts/{draft_id}` | 按并发版本保存本人草稿 | [draft_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/draft_controller.py) |
| POST | `/api/v1/elements/{element_id}/copy` | 双向授权复制元素固定修订 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| DELETE | `/api/v1/elements/{element_id}` | 逻辑删除元素并记录恢复期限 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| POST | `/api/v1/elements/{element_id}/restore` | 恢复元素原身份与固定修订 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| PATCH | `/api/v1/element-revisions/{revision_id}/label` | 修改修订展示标签 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| GET | `/api/v1/elements` | 分页读取有权访问的元素 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| POST | `/api/v1/elements` | 原子创建元素身份与首个修订 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| GET | `/api/v1/elements/{element_id}` | 读取元素与当前固定修订 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| PATCH | `/api/v1/elements/{element_id}` | 修改元素身份字段 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| POST | `/api/v1/elements/{element_id}/save` | 原子保存元素身份与内容 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| POST | `/api/v1/elements/{element_id}/move` | 移动元素目录归属 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| POST | `/api/v1/elements/{element_id}/revisions` | 保存元素固定资料修订 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| GET | `/api/v1/elements/{element_id}/revisions` | 分页读取元素历史修订 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| GET | `/api/v1/projects/{project_id}/property-definitions` | 读取项目最新属性定义 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| POST | `/api/v1/projects/{project_id}/property-definitions` | 创建项目属性定义 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| POST | `/api/v1/property-definitions/{definition_id}/versions` | 追加属性定义不可变版本 | [element_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_controller.py) |
| POST | `/api/v1/imports/elements` | 受理元素文档导入 | [element_import_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_import_controller.py) |
| POST | `/api/v1/imports/elements/{identity}/confirm` | 原子确认选中候选为正式元素 | [element_import_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_import_controller.py) |
| GET | `/api/v1/imports/elements/{identity}` | 查看已授权导入批次摘要 | [element_import_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_import_controller.py) |
| GET | `/api/v1/imports/elements/{identity}/rows` | 分页读取已授权导入候选 | [element_import_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_import_controller.py) |
| PATCH | `/api/v1/imports/elements/{identity}/rows/{row_no}` | 复核候选字段和选中状态 | [element_import_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/element_import_controller.py) |
| POST | `/api/v1/favorites` | 收藏当前可读对象 | [favorite_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/favorite_controller.py) |
| GET | `/api/v1/favorites` | 分页读取本人的收藏并重新核验来源 | [favorite_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/favorite_controller.py) |
| DELETE | `/api/v1/favorites/{identity}` | 取消本人的收藏 | [favorite_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/favorite_controller.py) |
| GET | `/api/v1/folders/{folder_id}` | 读取目录及授权面包屑 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| GET | `/api/v1/projects/{project_id}/folders` | 分页查询目录及搜索 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| POST | `/api/v1/projects/{project_id}/folders` | 创建目录 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| PATCH | `/api/v1/folders/{folder_id}` | 编辑目录 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| POST | `/api/v1/folders/{folder_id}/move` | 移动目录 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| POST | `/api/v1/folders/{folder_id}/copy` | 复制目录树 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| DELETE | `/api/v1/folders/{folder_id}` | 将内容移到父级并回收目录 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| POST | `/api/v1/folders/{folder_id}/restore` | 恢复原目录身份 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| GET | `/api/v1/projects/{project_id}/trash` | 项目内容回收站 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| GET | `/api/v1/projects/{project_id}/folder-asset-counts` | 读取未删除素材总数及目录直接素材数 | [folder_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/folder_controller.py) |
| POST | `/api/v1/generations/validate` | 检查生成可受理性，不预占或发起消费 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| POST | `/api/v1/generations` | 原子受理任务，实际用量事后计费 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| POST | `/api/v1/generations/{job_id}/cancel` | 取消明确未提交的任务并释放原预占 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| POST | `/api/v1/generations/{job_id}/retry-archive` | 仅重试已有失败输出的归档 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| GET | `/api/v1/generations` | 分页读取当前授权范围内的生成任务 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| GET | `/api/v1/generations/activity` | 合并读取个人任务状态与授权项目进行中数量 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| GET | `/api/v1/projects/{project_id}/generation-events` | 订阅当前授权项目的状态变化，重连补查快照 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| GET | `/api/v1/generations/{job_id}/input` | 读取已授权生成任务的固定输入 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| GET | `/api/v1/generations/{job_id}` | 读取任务聚合状态与已授权输出快照 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| GET | `/api/v1/generations/{job_id}/events` | 订阅任务持久事件与重放 | [generation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/generation_controller.py) |
| GET | `/api/admin/v1/generation-incidents` | 分页读取管理范围内的异常任务 | [incident_read_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/incident_read_controller.py) |
| GET | `/api/admin/v1/generation-incidents/{job_id}` | 读取异常任务状态与脱敏证据定位 | [incident_read_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/incident_read_controller.py) |
| POST | `/api/admin/v1/generation-incidents/{job_id}/actions` | 重新调度状态核查或归档，不重新生成 | [incident_read_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/incident_read_controller.py) |
| GET | `/api/admin/v1/model-profiles` | 分页读取后台模型身份 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| POST | `/api/admin/v1/model-profiles` | 登记模型身份 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| GET | `/api/admin/v1/model-profiles/{model_id}/versions` | 读取能力版本列表 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| POST | `/api/admin/v1/model-profiles/{model_id}/versions` | 新增草稿能力版本 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| GET | `/api/admin/v1/model-profile-versions/{version_id}` | 读取后台能力版本详情 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| GET | `/api/admin/v1/model-profile-versions/{version_id}/variants` | 读取精确计价规格 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| POST | `/api/admin/v1/model-profile-versions/{version_id}/variants` | 登记完整精确规格 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| PATCH | `/api/admin/v1/model-profile-versions/{version_id}` | 编辑草稿能力版本 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| POST | `/api/admin/v1/model-profile-versions/{version_id}/verify` | 登记已审阅的模型联调证据 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| POST | `/api/admin/v1/model-profile-versions/{version_id}/publish` | 发布已验证模型能力 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| POST | `/api/admin/v1/model-profile-versions/{version_id}/disable` | 停用模型能力版本 | [model_admin_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_admin_controller.py) |
| GET | `/api/v1/model-profiles` | 分页读取项目已授权发布的模型能力 | [model_catalog_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/model_catalog_controller.py) |
| POST | `/api/v1/outputs/{output_id}/to-asset` | 将已归档作品转为独立素材并保留来源 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| GET | `/api/v1/outputs/{output_id}` | 读取已授权生成输出 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| POST | `/api/v1/outputs/{output_id}/work-status` | 修改已归档作品工作状态并保留历史 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| GET | `/api/v1/outputs/{output_id}/thumbnail` | 授权读取作品图片缩略图 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| HEAD | `/api/v1/outputs/{output_id}/thumbnail` | 授权读取作品缩略图元数据 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| GET | `/api/v1/outputs/{output_id}/preview` | 授权预览已归档输出 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| HEAD | `/api/v1/outputs/{output_id}/preview` | 读取已归档输出预览元数据 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| GET | `/api/v1/outputs/{output_id}/download` | 授权下载已归档输出 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| HEAD | `/api/v1/outputs/{output_id}/download` | 读取已归档输出下载元数据 | [output_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/output_controller.py) |
| POST | `/api/admin/v1/model-prices/publish` | 原子发布模型采购与平台同价 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/exchange-rate-versions` | 分页读取汇率版本 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| POST | `/api/admin/v1/exchange-rate-versions` | 登记有来源的汇率草稿 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| POST | `/api/admin/v1/exchange-rate-versions/{rate_id}/publish` | 校验币对区间后发布汇率 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/price-books` | 分页读取价格簿 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| POST | `/api/admin/v1/price-books` | 登记明确用途的价格簿 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| POST | `/api/admin/v1/price-sources` | 登记不可变价格来源 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/price-sources` | 分页读取已登记价格来源 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/price-sources/{source_id}` | 读取价格来源证据 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/price-sources/{source_id}/attachment/download` | 授权下载价格证据附件 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| HEAD | `/api/admin/v1/price-sources/{source_id}/attachment/download` | 授权读取价格证据附件元数据 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/price-sources/{source_id}/attachment` | 读取价格证据附件（契约入口） | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| HEAD | `/api/admin/v1/price-sources/{source_id}/attachment` | 读取价格证据附件元数据（契约入口） | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/price-versions` | 分页读取价格版本与校验问题 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/price-versions/{version_id}` | 读取价格版本及来源 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| POST | `/api/admin/v1/price-versions` | 新增价格草稿版本 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| PATCH | `/api/admin/v1/price-versions/{version_id}` | 编辑价格草稿并校验并发版本 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| POST | `/api/admin/v1/price-versions/{version_id}/simulate` | 按精确规格离线试算价格，不写账本 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| POST | `/api/admin/v1/price-versions/{version_id}/publish` | 原子发布价格及生效区间 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| POST | `/api/admin/v1/price-activations/{activation_id}/end` | 结束价格生效区间并保留历史 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/admin/v1/price-versions/{version_id}/history` | 读取价格发布及生效区间历史 | [price_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/price_controller.py) |
| GET | `/api/v1/projects` | 我的项目列表 | [project_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_controller.py) |
| POST | `/api/v1/projects` | 新建项目 | [project_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_controller.py) |
| GET | `/api/v1/projects/{project_id}` | 项目详情 | [project_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_controller.py) |
| POST | `/api/v1/projects/{project_id}/archive` | 归档项目 | [project_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_controller.py) |
| POST | `/api/v1/projects/{project_id}/restore` | 恢复归档项目 | [project_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_controller.py) |
| PATCH | `/api/v1/projects/{project_id}` | 编辑项目基本信息 | [project_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_controller.py) |
| POST | `/api/v1/projects/{project_id}/pause` | 暂停项目 | [project_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_controller.py) |
| POST | `/api/v1/projects/{project_id}/resume` | 恢复项目运行 | [project_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_controller.py) |
| GET | `/api/admin/v1/projects` | 分页读取治理范围内的项目元数据 | [project_governance_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_governance_controller.py) |
| POST | `/api/admin/v1/projects/{project_id}/governance` | 治理范围内暂停、恢复及归档项目 | [project_governance_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_governance_controller.py) |
| GET | `/api/admin/v1/projects/{project_id}/join-requests` | 分页读取授权项目的加入申请 | [project_join_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_join_controller.py) |
| POST | `/api/admin/v1/join-requests/{identity}/review` | 审批加入申请并原子授予成员身份 | [project_join_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_join_controller.py) |
| GET | `/api/v1/project-collections` | 本人项目集合 | [project_preference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_preference_controller.py) |
| POST | `/api/v1/project-collections` | 创建个人集合 | [project_preference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_preference_controller.py) |
| PATCH | `/api/v1/project-collections/{identity}` | 修改个人集合 | [project_preference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_preference_controller.py) |
| DELETE | `/api/v1/project-collections/{identity}` | 解除个人集合分组 | [project_preference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_preference_controller.py) |
| GET | `/api/v1/projects/{project_id}/preferences` | 读取本人项目偏好 | [project_preference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_preference_controller.py) |
| PUT | `/api/v1/projects/{project_id}/preferences` | 保存本人项目偏好 | [project_preference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_preference_controller.py) |
| GET | `/api/v1/projects/{project_id}/brief` | 读取项目简报 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| PUT | `/api/v1/projects/{project_id}/brief` | 保存项目简报 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| GET | `/api/v1/projects/{project_id}/members` | 项目成员列表 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| GET | `/api/v1/projects/{project_id}/roles` | 项目角色与可授予范围 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| GET | `/api/v1/projects/{project_id}/member-candidates` | 精确账号查找可添加成员 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| POST | `/api/v1/projects/{project_id}/members` | 添加或恢复项目成员 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| PATCH | `/api/v1/projects/{project_id}/members/{user_id}` | 调整项目成员角色 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | 移除项目成员并保留身份记录 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| GET | `/api/v1/projects/{project_id}/role-permissions` | 读取项目角色权限矩阵 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| PUT | `/api/v1/projects/{project_id}/role-permissions` | 保存当前项目角色权限 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| PUT | `/api/v1/projects/{project_id}/ownership` | 转让项目所有权 | [project_workspace_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/project_workspace_controller.py) |
| GET | `/api/admin/v1/provider-calls` | 分页读取管理范围内的调用事实 | [provider_call_read_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/provider_call_read_controller.py) |
| GET | `/api/admin/v1/provider-calls/{call_id}` | 读取脱敏调用证据 | [provider_call_read_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/provider_call_read_controller.py) |
| GET | `/api/admin/v1/provider-connections` | 分页读取供应商连接 | [provider_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/provider_controller.py) |
| GET | `/api/admin/v1/provider-connections/{connection_id}` | 读取供应商连接非秘密配置 | [provider_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/provider_controller.py) |
| POST | `/api/admin/v1/provider-connections` | 登记草稿连接与首个配置版本 | [provider_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/provider_controller.py) |
| PATCH | `/api/admin/v1/provider-connections/{connection_id}` | 创建连接新配置并保留历史版本 | [provider_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/provider_controller.py) |
| GET | `/api/admin/v1/provider-accounts` | 分页读取供应商账号作用域 | [provider_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/provider_controller.py) |
| POST | `/api/admin/v1/provider-accounts` | 登记供应商账号及上游项目 | [provider_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/provider_controller.py) |
| POST | `/api/admin/v1/reconciliations` | 受理对账文件，尚未匹配或确认 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| GET | `/api/admin/v1/reconciliations/{batch_id}` | 读取对账批次及导入诊断 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| GET | `/api/admin/v1/reconciliations/{batch_id}/attachment/download` | 授权下载原始账单证据 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| HEAD | `/api/admin/v1/reconciliations/{batch_id}/attachment/download` | 授权读取原始账单文件元数据 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| GET | `/api/admin/v1/reconciliations` | 筛选并分页读取对账批次 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| GET | `/api/admin/v1/reconciliations/{batch_id}/lines` | 分页读取账单项及本次文件观察证据 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| POST | `/api/admin/v1/reconciliation-lines/{line_id}/match` | 人工匹配同账号计费对象 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| POST | `/api/admin/v1/reconciliation-lines/{line_id}/confirm` | 确认已匹配账单项，不自动调整估值 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| POST | `/api/admin/v1/reconciliation-lines/{line_id}/resolve` | 选择导入证据解决差异，仍需人工确认 | [reconciliation_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reconciliation_controller.py) |
| GET | `/api/v1/references/search` | 检索当前项目授权引用候选 | [reference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reference_controller.py) |
| POST | `/api/v1/references/updates` | 检查固定元素引用是否存在可用的新修订，不修改草稿 | [reference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/reference_controller.py) |
| GET | `/api/admin/v1/platform-provider-configs` | 读取全平台默认模型配置 | [routing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/routing_controller.py) |
| PUT | `/api/admin/v1/platform-provider-configs` | 保存全平台默认模型配置 | [routing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/routing_controller.py) |
| GET | `/api/admin/v1/project-provider-configs/{project_id}` | 读取治理范围内项目的整组模型路由 | [routing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/routing_controller.py) |
| PUT | `/api/admin/v1/project-provider-configs/{project_id}` | 原子替换项目模型路由整组配置 | [routing_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/routing_controller.py) |
| GET | `/api/v1/projects/{project_id}/budget-status` | 读取当前预算阻断状态及获准平台额度 | [usage_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/usage_controller.py) |
| GET | `/api/v1/view-preferences/{view_key}` | 读取本人视图偏好 | [view_preference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/view_preference_controller.py) |
| PUT | `/api/v1/view-preferences/{view_key}` | 保存本人视图偏好 | [view_preference_controller](../ruoyi-fastapi-backend/module_higgsfield/controller/view_preference_controller.py) |

多人制作补充（2026-11-05）：

- `POST /api/v1/generations` 在持久化前检查三级待处理上限，满额返回业务错误 `GENERATION_QUEUE_FULL`；已受理请求使用原幂等键仍可取得原回执。
- `POST /api/admin/v1/generation-incidents/{job_id}/actions` 的 `close_tracking` 必须同时提供原因、`evidenceRef` 和 `acknowledgeSupplierStopped: true`，表示管理员已核实供应商任务停止或未运行；提交后释放本地名额，保留上游与费用事实。
- `POST /api/admin/v1/credential-tests/{test_id}/release-capacity` 需要 `credential:test` 权限及 `Idempotency-Key`。请求字段为 `reason`、`evidenceRef`、`acknowledgeSupplierStopped: true`；只允许已结束但受理未知的测试，返回 `testId` 与 `capacityReleased`。此接口不调用供应商。
- 测试详情增加 `capacityReviewRequired`；媒体输出增加 `archivePaused` 和 `archiveNextRetryAt`，用于解释暂停与延后保存。异常任务筛选增加 `tracking_paused`。

传输字段见[VO目录](../ruoyi-fastapi-backend/module_higgsfield/entity/vo)，逻辑见[Service目录](../ruoyi-fastapi-backend/module_higgsfield/service)。历史请求草案见[历史快照](历史版本/2026-11-03同步前/平台API契约.md)。


### 工作区合并状态读取（2026-11-06）

`GET /api/v1/generations/activity` 接收 `projectId`、`pageNum`（默认 1）及 `trackedIds`（逗号分隔，每批最多 100 个编号）。返回框架 `data` 中的 `projectActiveCount`、`rows`、`hasNext`。个人进行中任务每页 100 条；`trackedIds` 补充当前用户在本项目中的指定任务终态，不能读取其他人的任务或绕过成员权限。`hasNext` 仅表示个人进行中任务还有下一页，不表示生成完成。

工作区共用一次状态刷新，同时驱动数量、个人进度和完成通知；不读取账单、媒体预览及供应商请求正文。查询失败保留最后成功状态并提示延迟；明确撤权清空旧状态。工作区优先订阅项目 SSE，收到变化后读取合并快照；心跳不触发任务查询。连接异常时降级为合并轮询：等待发送时约 1 秒、处理中约 5 秒、空闲约 30 秒，并加入少量随机延迟；查询失败退避、后台标签暂停、返回前台补查。单任务详情的持久事件协议保持不变。

归档完成只刷新素材数量及受影响的当前素材列表；“包含子目录素材”开启时保守刷新当前素材页，不重新加载目录树。本次无数据库迁移；API 和工作器均需加载新代码，制作端需刷新页面。工作器的阶段与归档事件、供应商交换证据现在会在同一事务中发布通知；旧工作器尚未重启时仍由周期快照补查发现变化，不会补发生成请求。


### 项目 SSE 协议与恢复边界（2026-11-06）

- 入口：`GET /api/v1/projects/{project_id}/generation-events`，沿用 Bearer 登录鉴权和当前项目 `generation:read` 权限。每个工作区仅一条连接，多个任务共享；不会为每个任务建立连接。
- `activity.sync`：初次连接、重连、权限范围变化及约 30 秒兜底同步，客户端重新读取授权合并快照；`activity.changed`：有相关状态变化，合并刷新；`activity.heartbeat`：保持连接及验证在线，不查询任务列表；`activity.degraded`：服务暂不可用，客户端降级轮询并退避重连；`access.revoked`：清空状态并停止自动订阅/查询，等待登录、授权变化或用户手动重试。
- 正常通知数据仅含当前 `projectId`，不广播任务编号、提示词、文件地址、凭据或其他人的任务正文。个人范围只接受本人的变化；项目范围可接收数量变化。请求传输阶段只唤醒任务本人，避免全团队为无关进度读取快照。
- 每个 API 进程使用一个 PostgreSQL LISTEN 连接。通知与状态写入同事务提交，回滚不投递；各 API 进程独立监听同一 schema 的频道。每个订阅只有一个脏标记，密集变化合并，慢客户端不积累无限事件队列。没有订阅时释放监听连接，API 关闭时也清理。
- 推送前及空闲时约每 5 秒重新验证登录和项目权限，事件合并等待约 1 秒；权限变化可能在这个检查窗口内反映，不承诺瞬时撤权。任务详情始终通过独立授权接口读取。服务端发送前释放业务数据库会话。
- 客户端 45 秒未收到有效事件会关闭半开连接，重连间隔从约 2 秒退避到 30 秒并加入随机延迟；后台标签或卸载立即关闭。代理需允许 SSE 长连接且不缓冲响应，服务端返回 `Cache-Control: no-store` 和 `X-Accel-Buffering: no`。
- 项目流采用“变化通知 + 当前快照”，不以 `Last-Event-ID` 重放每个历史中间状态，也不承诺每个通知恰好送达一次。断线、API 重启、监听重连及漏通知均通过重新读取当前快照恢复；已跟踪任务编号随快照请求补查终态，避免任务退出进行中列表后漏掉最终结果。需要完整历史仍读取任务事件/详情。
- 验证使用隔离 PostgreSQL schema、模拟账号/任务和本地模拟 HTTP SSE；覆盖两项目 20 名制作人并发、撤权与范围缩小、事务回滚、监听失败、断线/半开恢复及停止订阅清理。未调用真实付费供应商；正式反向代理和生产规模负载尚需部署环境验收。
