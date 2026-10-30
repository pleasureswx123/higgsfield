export interface CropRect { x: number; y: number; width: number; height: number }
export type CropHandle = 'move' | 'n' | 's' | 'e' | 'w' | 'nw' | 'ne' | 'sw' | 'se'
const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value))

/** 在图片归一化坐标内移动或缩放，不允许翻转或越界。 */
export function changeCrop(rect: CropRect, handle: CropHandle, dx: number, dy: number): CropRect {
  if (handle === 'move') return { ...rect, x: clamp(rect.x + dx, 0, 1 - rect.width), y: clamp(rect.y + dy, 0, 1 - rect.height) }
  let left = rect.x, top = rect.y, right = rect.x + rect.width, bottom = rect.y + rect.height
  if (handle.includes('w')) left = clamp(left + dx, 0, right - 0.02)
  if (handle.includes('e')) right = clamp(right + dx, left + 0.02, 1)
  if (handle.includes('n')) top = clamp(top + dy, 0, bottom - 0.02)
  if (handle.includes('s')) bottom = clamp(bottom + dy, top + 0.02, 1)
  return { x: left, y: top, width: right - left, height: bottom - top }
}

/** 按原图像素取整，防止边缘舍入产生空白像素。 */
export function cropPixels(rect: CropRect, width: number, height: number): CropRect {
  const x = clamp(Math.round(rect.x * width), 0, width - 1)
  const y = clamp(Math.round(rect.y * height), 0, height - 1)
  return { x, y, width: clamp(Math.round(rect.width * width), 1, width - x), height: clamp(Math.round(rect.height * height), 1, height - y) }
}
