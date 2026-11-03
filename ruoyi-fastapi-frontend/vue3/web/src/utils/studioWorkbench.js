export const workbenchEntries = [
  { key: 'setup', title: '供应商与模型', permission: 'provider:read', path: '/studio/provider-connections',
    description: '供应商配置一次，分别新增、配置和启用旗下模型。已有配置继续使用。', action: '进入模型接入' },
  { key: 'billing', title: '用量与费用', permission: 'billing:read', path: '/studio/billing-events',
    description: '查看每次生成的真实用量和费用，不需要设置预算或预占。', action: '查看用量与费用' },
  { key: 'users', title: '用户管理', permission: 'system:user:list', path: '/system/user',
    description: '管理成员账号、分配角色，维护账号启用状态。', action: '管理用户' },
  { key: 'departments', title: '部门管理', permission: 'system:dept:list', path: '/system/dept',
    description: '维护部门结构，整理团队的组织归属。', action: '管理部门' },
  { key: 'operations', title: '运行记录', permission: 'operations:read', path: '/studio/calls',
    description: '查看供应商调用结果；生成异常时进入异常任务核查。', action: '查看调用记录' },
]

export function hasPermission(permissions, permission) {
  return permissions.includes('*:*:*') || permissions.includes(permission)
}

export function authorizedPaths(routes, parent = '') {
  return routes.flatMap(route => {
    const path = (route.path.startsWith('/') ? route.path : `${parent}/${route.path}`).replace(/\/+/g, '/')
    return [path, ...authorizedPaths(route.children || [], path)]
  })
}
export function workbenchNext(facts, entries) {
  const setup = entries.find(row => row.key === 'setup')
  if (setup) {
    if (facts.connections === 0) return { ...setup, heading: '先添加供应商，再添加模型',
      detail: '准备供应商给你的 API 地址和密钥。保存供应商后，页面会带你添加第一个模型。', action: '接入第一个模型' }
    if (facts.published === 0) return { ...setup, heading: '继续完成模型接入',
      detail: '已有供应商配置，接下来确认价格、完成测试并启用模型。之前填写的内容无需重建。', action: '继续已有接入' }
  }
  if (setup && facts.platformModels === 0 && facts.published > 0) return { ...setup,
    heading: '完成全平台启用', detail: '已有模型和配置。继续模型接入，点击启用到全平台，现有和新建项目即可自动使用。' }
  if (setup && facts.platformModels > 0) return { ...setup,
    heading: '模型已开放到全平台，可以验证生成', detail: '现有和新建项目自动可用。由有创作权限的成员生成一张图片，并检查保存结果和实际费用。', action: '查看模型接入' }
  if (entries.length === 1 && entries[0].key === 'billing') return { ...entries[0],
    heading: '查看用量与费用', detail: '查看项目创作和管理员测试的 Token 消耗、费用明细，核对供应商成本。' }
  const first = entries[0]
  return first ? { ...first, heading: '从这里开始管理', detail: '按下方职责入口操作。状态读取失败或没有查看权限时，不会将其显示为“尚未配置”。' }
    : { heading: '欢迎使用管理工作台', detail: '当前账号尚未获得模型、项目、费用或运行管理入口。请联系系统管理员配置对应角色权限。' }
}

/** 角色决定工作台职责，入口仍须同时通过权限和菜单校验。 */
export function workbenchRole(roles = [], entries = []) {
  if (roles.includes('hf_platform_finance_admin')) return 'combined'
  const finance = roles.includes('hf_finance_admin')
  const platform = roles.includes('hf_platform_admin')
  if (finance && platform) return 'combined'
  if (finance) return 'finance'
  if (platform) return 'platform'
  if (entries.length && entries.every(row => row.key === 'billing')) return 'finance'
  return 'general'
}
