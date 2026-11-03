/** 只重新组织后端已经授权的菜单，不增加授权或改动真实页面地址。 */
const titles = {
  'provider-connections': '供应商与模型', routing: '项目专用配置', 'billing-events': '用量与费用',
  'provider-credentials': '供应商密钥', models: '模型版本与能力', prices: '价格与来源',
  governance: '项目状态管理', calls: '调用记录', incidents: '异常任务',
}
const internal = new Set(['provider-credentials', 'models', 'prices', 'routing', 'governance'])
export function labelStudioRoutes(routes) {
  return routes.map(route => {
    const copy = { ...route, meta: { ...route.meta } }
    if (route.path === '/studio' || route.path === 'studio') {
      copy.meta.title = '平台管理'
      copy.children = (route.children || []).map(child => ({ ...child,
        hidden: child.hidden || internal.has(child.path.split('/').pop()),
        meta: { ...child.meta, ...(internal.has(child.path.split('/').pop()) ? { activeMenu: '/studio/provider-connections' } : {}), title: titles[child.path.split('/').pop()] || child.meta?.title } }))
    } else if (route.children) copy.children = labelStudioRoutes(route.children)
    return copy
  })
}
export function studioNavigation(routes) {
  return labelStudioRoutes(routes).map(route => {
    if (!['/studio', 'studio'].includes(route.path)) return route
    const primary = [], runtime = []
    for (const child of route.children || []) {
      const key = child.path.split('/').pop()
      if (['provider-connections', 'billing-events'].includes(key)) primary.push(child)
      else if (['calls', 'incidents'].includes(key)) runtime.push({ ...child, path: `/studio/${key}` })
    }
    const order = ['provider-connections', 'billing-events']
    primary.sort((a, b) => order.indexOf(a.path.split('/').pop()) - order.indexOf(b.path.split('/').pop()))
    if (runtime.some(row => !row.hidden)) primary.push({ path: '/studio/runtime-menu', redirect: 'noRedirect', alwaysShow: true,
      meta: { title: '运行记录', icon: 'list' }, children: runtime })
    return { ...route, alwaysShow: true, children: primary }
  })
}

export function menuDestination(base, path, query) {
  const target = (path.startsWith('/') ? path : `${base}/${path}`.replace(/\/+/g, '/')).replace(/\/$/, '') || '/'
  return query ? { path: target, query: JSON.parse(query) } : target
}
