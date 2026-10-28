import { getLibraryViewPreference, saveLibraryViewPreference, type LibraryViewSettings } from '@/api/viewPreferences'
import { useViewPreference } from './useProjectViewPreference'
export function useLibraryViewPreference(projectId: string, current: () => LibraryViewSettings, apply: (value: LibraryViewSettings) => void) {
  return useViewPreference(current, value => {
    apply(value)
  },
    signal => getLibraryViewPreference(projectId, signal),
    (settings, revision, key, signal) => saveLibraryViewPreference(projectId, settings, revision, key, signal),
  )
}
