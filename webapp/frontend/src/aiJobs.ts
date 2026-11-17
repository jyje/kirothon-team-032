import { computed, onUnmounted, ref } from 'vue'
import { api, ApiError } from '@/api'

type Kind = 'summary' | 'draft' | 'transcribe'
type Status = 'queued' | 'running' | 'done' | 'failed'
export type AiJob = {
  id: string
  status: Status
  attempts: number
  result_id: string | null
  dropped_bullets: number
  truncated: boolean
  error_code: string | null
}

const errors: Record<string, string> = {
  no_sources: '사용할 기록이 없어요. 메모나 자료를 추가해 주세요.',
  llm_not_configured: 'AI 제공자가 설정되지 않았어요.',
  llm_failed: 'AI 요청에 실패했어요. 다시 시도해 주세요.',
  event_not_found: '행사를 찾을 수 없어요.',
  consent_required: '유효한 녹음 동의가 필요해요.',
  audio_missing: '전사할 원본 음성 파일이 없어요.',
  transcriber_not_configured: '전사기를 사용할 수 없어요.',
  worker_interrupted: '작업을 끝내지 못했어요. 다시 시도해 주세요.',
}

export function useAiJob(
  sessionId: string, kind: Kind, onComplete: (job: AiJob, restored: boolean) => Promise<void>,
  assetId?: string,
) {
  const path = `/api/sessions/${sessionId}/jobs`
  const query = new URLSearchParams({ kind })
  if (assetId) query.set('asset_id', assetId)
  const state = ref<AiJob>()
  const error = ref('')
  const reconnecting = ref(false)
  const submitting = ref(false)
  const restoring = ref(true)
  const readingResult = ref(false)
  let stream: EventSource | undefined
  let unmounted = false

  const busy = computed(() => submitting.value || restoring.value || readingResult.value ||
    state.value?.status === 'queued' || state.value?.status === 'running')
  const status = computed(() => {
    if (reconnecting.value) return '작업 상태에 다시 연결하는 중…'
    if (state.value?.status === 'queued') {
      return state.value.attempts ? '재시도 대기 중…' : '작업 대기 중…'
    }
    if (state.value?.status === 'running') return '작업 실행 중…'
    if (readingResult.value) return '작업 결과를 불러오는 중…'
    if (state.value?.status === 'done' && !error.value) return '작업 완료'
    return ''
  })

  function closeStream() {
    stream?.close()
    stream = undefined
    reconnecting.value = false
  }

  async function receive(job: AiJob, restored = false) {
    if (unmounted) return
    state.value = job
    if (job.status === 'queued' || job.status === 'running') return
    closeStream()
    if (job.status === 'failed') {
      error.value = errors[job.error_code ?? ''] ?? '작업에 실패했어요. 다시 시도해 주세요.'
      return
    }
    if (job.result_id) {
      readingResult.value = true
      try {
        await onComplete(job, restored)
      } catch {
        error.value = '작업은 끝났지만 결과를 불러오지 못했어요. 화면을 새로고침해 주세요.'
      } finally {
        readingResult.value = false
      }
    }
  }

  async function follow(job: AiJob, restored = false) {
    closeStream()
    await receive(job, restored)
    if (unmounted || (job.status !== 'queued' && job.status !== 'running')) return
    const source = new EventSource(`/api/jobs/${job.id}/events`)
    stream = source
    function changed(event: MessageEvent<string>) {
      if (stream !== source) return
      reconnecting.value = false
      void receive(JSON.parse(event.data) as AiJob)
    }
    source.addEventListener('job.status', changed)
    source.addEventListener('job.failed', changed)
    source.onerror = () => {
      if (stream !== source) return
      if (source.readyState === EventSource.CLOSED) {
        closeStream()
        state.value = undefined
        error.value = '작업 상태를 불러오지 못했어요. 화면을 새로고침해 주세요.'
      } else {
        reconnecting.value = true
      }
    }
  }

  async function restore() {
    try {
      const { job } = await api<{ job: AiJob | null }>(`${path}?${query}`)
      if (job) await follow(job, true)
    } catch {
      error.value = '기존 작업을 확인할 수 없어요. 화면을 새로고침해 주세요.'
    } finally {
      restoring.value = false
    }
  }

  async function submit(templateId?: string) {
    if (busy.value) return
    submitting.value = true
    error.value = ''
    try {
      const job = await api<AiJob>(path, { json: { kind, template_id: templateId, asset_id: assetId } })
      await follow(job)
    } catch (cause) {
      error.value = cause instanceof ApiError ? cause.message : '작업을 등록하지 못했어요.'
    } finally {
      submitting.value = false
    }
  }

  onUnmounted(() => {
    unmounted = true
    closeStream()
  })
  return { busy, error, status, restore, submit }
}
