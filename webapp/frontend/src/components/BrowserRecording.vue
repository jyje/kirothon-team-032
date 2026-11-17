<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { api, ApiError } from '@/api'
import type { Asset, ConsentRecord } from '@/types'

const props = defineProps<{
  sessionId: string
  records: ConsentRecord[]
  active: boolean
  maxBytes: number
}>()
const emit = defineEmits<{ recorded: [asset: Asset] }>()
const selectedId = ref('')
const validRecords = computed(() => props.records.filter(record => !record.revoked_at))
const status = ref<'idle' | 'requesting' | 'recording' | 'stopping' | 'saving'>('idle')
const error = ref('')
const notice = ref('')
const pending = shallowRef<{ file: File; consentId: string; uploadId: string } | null>(null)

type Capture = { recorder: MediaRecorder; consentId: string }
let capture: Capture | null = null
let startRequest = 0
let disposed = false

function release(stream: MediaStream) {
  for (const track of stream.getTracks()) track.stop()
}

function stop() {
  if (capture?.recorder.state !== 'recording') return
  status.value = 'stopping'
  capture.recorder.stop()
  release(capture.recorder.stream)
}

function discard() {
  pending.value = null
  error.value = ''
  notice.value = ''
}

async function start() {
  const consentId = selectedId.value
  if (!props.active || status.value !== 'idle' || pending.value ||
      !validRecords.value.some(record => record.id === consentId)) return
  error.value = ''
  notice.value = ''
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    error.value = '마이크 녹음은 지원되는 브라우저의 HTTPS 또는 localhost에서 사용할 수 있어요.'
    return
  }

  const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
    .find(type => MediaRecorder.isTypeSupported(type))
  if (!mime) {
    error.value = '이 브라우저에서 저장할 수 있는 녹음 형식을 찾지 못했어요.'
    return
  }

  const request = ++startRequest
  let stream: MediaStream | undefined
  status.value = 'requesting'
  try {
    const { items } = await api<{ items: ConsentRecord[] }>(`/api/sessions/${props.sessionId}/consents`)
    if (request !== startRequest) return
    if (!items.some(record => record.id === consentId && !record.revoked_at)) {
      error.value = '유효한 녹음 동의를 다시 선택해 주세요.'
      status.value = 'idle'
      return
    }
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    if (request !== startRequest) {
      release(stream)
      return
    }

    const recorder = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 64_000 })
    const current: Capture = { recorder, consentId }
    const chunks: Blob[] = []
    let size = 0
    let interrupted = false
    for (const track of stream.getAudioTracks()) {
      track.addEventListener('ended', () => {
        if (capture !== current || status.value !== 'recording') return
        interrupted = true
        stop()
      }, { once: true })
    }
    recorder.ondataavailable = ({ data }) => {
      if (capture !== current || data.size === 0) return
      size += data.size
      if (size > props.maxBytes) {
        error.value = '녹음 파일이 서버의 업로드 한도를 넘었어요.'
        capture = null
        if (recorder.state !== 'inactive') recorder.stop()
        release(recorder.stream)
        status.value = 'idle'
        return
      }
      chunks.push(data)
      if (size >= 0.99 * props.maxBytes) stop()
    }
    recorder.onerror = () => {
      if (capture !== current) return
      interrupted = true
      release(recorder.stream)
    }
    recorder.onstop = () => {
      release(recorder.stream)
      if (capture !== current) return
      // 트랙 종료 이벤트보다 녹음기의 종료 콜백이 먼저 도착할 수도 있다.
      interrupted ||= status.value === 'recording'
      capture = null
      status.value = 'idle'
      if (!size) {
        error.value = interrupted
          ? '녹음이 중단됐어요. 마이크를 확인하고 다시 녹음해 주세요.'
          : '저장할 녹음이 없어요. 다시 녹음해 주세요.'
        return
      }
      const extension = mime === 'audio/mp4' ? 'm4a' : 'webm'
      const filename = `녹음-${new Date().toISOString().replaceAll(':', '-')}.${extension}`
      pending.value = {
        file: new File(chunks, filename, { type: recorder.mimeType || mime }),
        consentId,
        uploadId: crypto.randomUUID(),
      }
      if (interrupted) {
        error.value = '녹음이 중단됐어요. 중단 전까지 기록한 부분을 저장할 수 있어요.'
      }
    }

    recorder.start(1000)
    capture = current
    status.value = 'recording'
  } catch (cause) {
    if (stream) release(stream)
    if (request !== startRequest) return
    status.value = 'idle'
    error.value = cause instanceof ApiError ? cause.message
      : cause instanceof DOMException && cause.name === 'NotAllowedError'
        ? '마이크 권한이 거부됐어요. 브라우저에서 권한을 확인해 주세요.'
        : '마이크를 시작하지 못했어요.'
  }
}

async function save() {
  if (!pending.value || status.value !== 'idle') return
  const { file, consentId, uploadId } = pending.value
  const form = new FormData()
  form.append('kind', 'recording')
  form.append('consent_id', consentId)
  form.append('recording_upload_id', uploadId)
  form.append('file', file)
  status.value = 'saving'
  error.value = ''
  try {
    const asset = await api<Asset>(`/api/sessions/${props.sessionId}/assets`, { body: form })
    if (disposed) return
    discard()
    notice.value = '녹음을 저장했어요.'
    emit('recorded', asset)
  } catch (cause) {
    if (disposed) return
    if (cause instanceof ApiError && cause.status === 403) {
      pending.value = null
      selectedId.value = ''
    }
    error.value = cause instanceof ApiError && cause.status === 413
      ? '배포의 업로드 한도를 넘었어요. 녹음 길이 또는 인그레스 설정을 확인해 주세요.'
      : cause instanceof ApiError ? cause.message : '녹음을 저장하지 못했어요. 다시 시도해 주세요.'
  } finally {
    status.value = 'idle'
  }
}

watch(() => props.active, active => {
  if (active) return
  if (status.value === 'requesting') {
    startRequest++
    status.value = 'idle'
  }
  stop()
})

watch(validRecords, records => {
  if (!selectedId.value || records.some(record => record.id === selectedId.value)) return
  selectedId.value = ''
  if (status.value === 'requesting') {
    startRequest++
    status.value = 'idle'
  }
  if (capture) {
    const recorder = capture.recorder
    capture = null
    if (recorder.state !== 'inactive') recorder.stop()
    release(recorder.stream)
    status.value = 'idle'
  }
  discard()
})

const hasUnsavedRecording = computed(() => status.value === 'recording'
  || status.value === 'stopping' || pending.value !== null)

function warnBeforeUnload(event: BeforeUnloadEvent) {
  event.preventDefault()
  event.returnValue = true
}

function confirmLeave() {
  return !hasUnsavedRecording.value || window.confirm('저장하지 않은 녹음이 있어요. 이 행사를 떠날까요?')
}

watch(hasUnsavedRecording, unsaved => {
  if (unsaved) window.addEventListener('beforeunload', warnBeforeUnload)
  else window.removeEventListener('beforeunload', warnBeforeUnload)
})
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to, from) => to.path === from.path || confirmLeave())

onBeforeUnmount(() => {
  disposed = true
  window.removeEventListener('beforeunload', warnBeforeUnload)
  startRequest++
  if (capture) {
    stop()
    release(capture.recorder.stream)
    capture = null
  }
})
</script>

<template>
  <section class="capture" aria-label="행사 녹음">
    <h2>행사 녹음</h2>
    <p v-if="!validRecords.length">위에서 녹음 동의를 먼저 기록해 주세요.</p>
    <label v-else class="field">
      사용할 녹음 동의
      <select v-model="selectedId" :disabled="status !== 'idle' || pending !== null">
        <option value="">동의를 선택해 주세요</option>
        <option v-for="record in validRecords" :key="record.id" :value="record.id">
          {{ record.obtained_on }} {{ record.method }}
        </option>
      </select>
    </label>
    <div class="actions">
      <template v-if="pending">
        <button class="btn btn-primary" type="button" :disabled="status === 'saving'" @click="save">녹음 저장</button>
        <button class="btn" type="button" :disabled="status === 'saving'" @click="discard">녹음 버리기</button>
      </template>
      <button v-else-if="status === 'recording'" class="btn btn-primary" type="button" @click="stop">녹음 중지</button>
      <button v-else class="btn btn-primary" type="button" :disabled="!selectedId || status !== 'idle'" @click="start">녹음 시작</button>
    </div>
    <p v-if="status === 'requesting'" role="status">마이크 권한을 확인하는 중이에요.</p>
    <p v-else-if="status === 'recording'" role="status">녹음 중</p>
    <p v-else-if="status === 'stopping'" role="status">녹음을 마무리하는 중이에요.</p>
    <p v-else-if="status === 'saving'" role="status">녹음 파일을 저장하는 중이에요.</p>
    <p v-else-if="notice" role="status">{{ notice }}</p>
    <p v-else-if="pending && !error" role="status">녹음이 끝났어요. 이 행사를 떠나기 전에 저장해 주세요.</p>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.capture { display: grid; gap: var(--space-3); min-inline-size: 0; }
h2, p { margin: 0; }
h2 { font-family: var(--font-hand); font-weight: 400; color: var(--text-muted-on-dark); }
select {
  width: 100%;
  font: 500 var(--fs-btn) var(--font-body);
  color: var(--color-ink);
  background: var(--color-white);
  border: var(--border);
  border-radius: var(--radius-pill);
  padding: var(--space-3) var(--space-5);
}
.actions { display: flex; flex-wrap: wrap; gap: var(--space-3); }
</style>
