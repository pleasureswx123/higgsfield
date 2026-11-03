/** 目录提示只说明已知阻断项，不替代完整生成预检。 */
export function modelAvailabilityMessage(reason?: string): string {
  const messages: Record<string, string> = {
    PROJECT_READ_ONLY: '当前项目只读，不能提交生成。',
    GENERATION_POLICY_UNAVAILABLE: '生成运行配置尚未就绪，请联系管理员。',
    GENERATION_ESTIMATE_UNAVAILABLE: '此模型的旧估价配置已停用，请刷新模型配置。',
    GENERATION_PREFLIGHT_REQUIRED:
      '填写描述后点击生成，系统会自动校验参数、引用和模型接入配置。',
  }
  return messages[reason || ''] || '点击生成时会自动检查模型是否可用。'
}
