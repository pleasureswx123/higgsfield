# 制作平台前端强制规范

适用范围：本目录及全部子目录。以中文沟通，文档和注释以中文为主。

1. 技术栈使用 Vue3 + Vue Router + Pinia + Axios，并使用 TypeScript；全部业务单文件组件使用 `<script setup lang="ts">`，使用组合式 API，禁止 Options API。
2. 业务逻辑抽离到 use 开头的 composables，纯工具函数放 utils。
3. 请求统一放 api/ 独立模块；组件不直接写 axios、fetch、XHR 或接口 URL。SSE 和上传也必须封装。
4. 组件遵循单一职责；页面装配、业务交互、基础展示各自清晰，props/emits 显式定义。
5. 路由管理使用 Vue Router，路由定义与守卫集中在 router/；全局状态管理使用 Pinia，不使用 Vuex；局部状态保留在组件/composable，Store 状态使用 storeToRefs 解构。
6. 命名、具名导出、ref/reactive/computed 使用遵循 Vue3 组合式约定；computed 不产生副作用，异步订阅和监听必须清理。
7. Element Plus 与 shadcn-vue 共存，按场景选最合适组件；统一主题和弹层策略，避免样式重置、焦点锁及表单校验冲突。
8. 遵守平台 API 的字符串 bigint ID、revision、幂等与任务事件协议；前端不得持有供应商 API Key。

完整规则见 [制作平台前端编码规范](../docs/制作平台前端编码规范.md)，接口见 [平台 API 契约](../docs/平台API契约.md)。不要将目录规范文档当成已经初始化的 Vue 工程。是否编写业务代码以用户当前任务授权为准。

分层必须明确：views 页面装配 → components 单一职责交互 → useXxx 组合函数/Store action 业务流程 → api 请求模块；组件不直接发请求，API 模块不反向依赖页面或组件。

9. Vue 版本基线为 3.4+；自定义组件双向绑定优先 defineModel()，命名模型对应 v-model:xxx，可声明多个模型；禁止 .sync。子组件严禁修改 props 及嵌套对象/数组；对象模型通过新对象赋值或显式事件更新。父层初始化模型值，不用双向 watch 镜像状态。

10. 统一 Axios 客户端对齐若依 code/msg/success/time；业务失败可能 HTTP 200，不以 HTTP 成功替代业务成功。分页读取顶层 rows/pageNum/pageSize/total/hasNext；SSE/下载先辨别框架 JSON 错误。详见后端规范与 P0-4。

11. UI 视觉、布局和组件排版参考截图；卡片、表格、表单、侧边栏、按钮保留截图特征。必须有亮色/暗黑两套主题和切换入口，两套配色分别适配，不能机械反色；主题状态与语义色变量统一驱动 Element Plus 和 shadcn-vue，切换不丢业务状态，弹层及全部交互状态同步适配，媒体原图保持不变。详见前端规范“UI 截图还原与亮暗双主题”。
