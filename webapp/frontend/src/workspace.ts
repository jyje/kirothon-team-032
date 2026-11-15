import { computed } from 'vue'
import { useRoute } from 'vue-router'

export const workspaceSections = [
  { id: 'notes', label: '필기' },
  { id: 'assets', label: '자료' },
  { id: 'summary', label: 'AI 요약' },
  { id: 'draft', label: '초안' },
] as const

export function useWorkspaceSection() {
  const route = useRoute()
  return computed(() =>
    workspaceSections.find(({ id }) => route.hash === `#${id}`) ?? workspaceSections[0],
  )
}
