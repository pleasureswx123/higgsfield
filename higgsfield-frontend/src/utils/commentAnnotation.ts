import type { Annotation } from '@/api/comments'
export interface AnnotationPoint {
  x: number
  y: number
}
export function imagePoint(
  x: number,
  y: number,
  rect: { left: number; top: number; width: number; height: number },
): AnnotationPoint | undefined {
  if (
    ![x, y, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) ||
    rect.width <= 0 ||
    rect.height <= 0
  )
    return
  const clamp = (value: number) => Math.max(0, Math.min(1, value))
  return { x: clamp((x - rect.left) / rect.width), y: clamp((y - rect.top) / rect.height) }
}
export function buildAnnotation(
  shape: Annotation['shape'],
  points: AnnotationPoint[],
  color: string,
  width: number,
  height: number,
): Annotation | undefined {
  if (
    !points.length ||
    points.length > 256 ||
    !Number.isInteger(width) ||
    !Number.isInteger(height) ||
    width < 1 ||
    height < 1 ||
    width > 100000 ||
    height > 100000 ||
    !/^#[0-9a-f]{6}$/i.test(color)
  )
    return
  if (
    points.some(
      (p) =>
        !Number.isFinite(p.x) || !Number.isFinite(p.y) || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1,
    )
  )
    return
  const first = points[0]!,
    last = points.at(-1)!
  let geometry: Record<string, unknown>
  if (shape === 'point') geometry = { ...last }
  else if (shape === 'rect') {
    const x = Math.min(first.x, last.x),
      y = Math.min(first.y, last.y)
    const w = Math.max(first.x, last.x) - x,
      h = Math.max(first.y, last.y) - y
    if (!w || !h) return
    geometry = { x, y, width: w, height: h }
  } else {
    if (points.length < 2) return
    geometry = { points: points.map((p) => ({ ...p })) }
  }
  return { shape, geometry, color: color.toLowerCase(), sourceWidth: width, sourceHeight: height }
}
