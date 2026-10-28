export function validRoutingId(value) {
  return (
    typeof value === 'string' &&
    /^[1-9]\d{0,18}$/.test(value) &&
    BigInt(value) <= 9223372036854775807n
  )
}

export function routingPayload(revision, routes) {
  if (!validRoutingId(revision)) throw new Error('路由版本号无效，请重新读取')
  if (!Array.isArray(routes) || routes.length > 200) throw new Error('最多配置200条路由')
  const identities = new Set()
  const integer = (value, min) => Number.isInteger(value) && value >= min && value <= 2147483647
  return {
    revision,
    routes: routes.map((route) => {
      if (!validRoutingId(route.modelId) || !validRoutingId(route.accountId))
        throw new Error('请输入有效的模型和账号ID')
      const identity = `${route.modelId}:${route.accountId}`
      if (identities.has(identity)) throw new Error('模型和账号组合不能重复')
      identities.add(identity)
      if (!integer(route.priority, 0) || typeof route.enabled !== 'boolean')
        throw new Error('路由优先级或启用状态无效')
      if (
        !Array.isArray(route.credentials) ||
        route.credentials.length > 100 ||
        (route.enabled && !route.credentials.length)
      )
        throw new Error('启用路由需要候选凭据，每条最多100个')
      const ids = new Set()
      const credentials = route.credentials.map((candidate) => {
        if (!validRoutingId(candidate.credentialId) || ids.has(candidate.credentialId))
          throw new Error('凭据ID无效或重复')
        ids.add(candidate.credentialId)
        if (!integer(candidate.priority, 0) || !integer(candidate.maxConcurrency, 1))
          throw new Error('凭据优先级或并发上限无效')
        return {
          credentialId: candidate.credentialId,
          priority: candidate.priority,
          maxConcurrency: candidate.maxConcurrency,
        }
      })
      return {
        modelId: route.modelId,
        accountId: route.accountId,
        priority: route.priority,
        enabled: route.enabled,
        credentials,
      }
    }),
  }
}
