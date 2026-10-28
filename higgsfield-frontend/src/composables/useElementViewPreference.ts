import { getElementViewPreference, saveElementViewPreference, type ElementViewSettings } from '@/api/viewPreferences'
import { useViewPreference } from './useProjectViewPreference'

export function useElementViewPreference(projectId: string | undefined, current: () => ElementViewSettings, apply: (value: ElementViewSettings) => void) {
  return useViewPreference(current, apply,
    signal => getElementViewPreference(projectId, signal),
    (settings, revision, key, signal) => saveElementViewPreference(projectId, settings, revision, key, signal),
  )
}
