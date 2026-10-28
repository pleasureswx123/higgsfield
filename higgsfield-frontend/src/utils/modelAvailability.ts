/** 目录提示只说明已知阻断项，不替代完整生成预检。 */
export function modelAvailabilityMessage(reason?: string): string {
  const messages: Record<string, string> = {
    PROJECT_READ_ONLY: '当前项目只读，不能提交生成。',
    GENERATION_POLICY_UNAVAILABLE: '生成运行策略或估价签名尚未有效配置，请联系管理员。',
    GENERATION_ESTIMATE_UNAVAILABLE: '此模型尚未配置可靠的估价策略，请联系管理员。',
    GENERATION_PREFLIGHT_REQUIRED:
      '填写参数后进行生成预检，确认价格、预算、引用和当前路由是否可用。',
  }
  return messages[reason || ''] || '模型目录不代表当前可受理，请以生成预检结果为准。'
}
