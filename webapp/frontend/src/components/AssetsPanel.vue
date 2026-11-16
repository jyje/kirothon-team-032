<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '@/api'
import type { Asset, AssetList, Block, SessionDetail } from '@/types'
import AudioTranscript from './AudioTranscript.vue'
import PhotoFaceReview from './PhotoFaceReview.vue'
import RecordingConsent from './RecordingConsent.vue'

const props = defineProps<{ sessionId: string; blocks: Block[]; active: boolean }>()
const emit = defineEmits<{ changed: []; consentRevoked: [] }>()
const retainAudio = defineModel<boolean>('retainAudio', { required: true })
const savingRetention = ref(false)
const retentionNotice = ref('')

const assets = ref<Asset[]>([])
const limits = ref<Record<string, number>>({})
const error = ref('')
const busy = ref(false)
const photoVersions = ref<Record<string, number>>({})
const transcriptionEnabled = ref(false)
const maxRecordingBytes = ref<number | null>(null)

const photos = computed(() => assets.value.filter((a) => a.kind === 'photo'))
const recordings = computed(() => assets.value.filter((a) => a.kind === 'recording' || a.kind === 'voice_memo'))
const docs = computed(() => assets.value.filter((a) => a.kind === 'slides' || a.kind === 'reference'))
const base = computed(() => `/api/sessions/${props.sessionId}/assets`)

function blockLabel(b: Block, i: number): string {
  const text = b.text.trim().slice(0, 24)
  return `메모 ${i + 1}: ${text || '(빈 메모)'}`
}

async function load() {
  const data = await api<AssetList>(base.value)
  assets.value = data.items.map((a) => ({ ...a, caption: a.caption ?? '' }))
  limits.value = data.limits
  transcriptionEnabled.value = data.transcription_enabled
  maxRecordingBytes.value = data.recording_enabled && data.recording_max_bytes > 0
    ? data.recording_max_bytes : null
}

async function saveRetention(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  savingRetention.value = true
  retentionNotice.value = ''
  error.value = ''
  try {
    const result = await api<SessionDetail>(`/api/sessions/${props.sessionId}`, {
      method: 'PATCH', json: { retain_audio: input.checked },
    })
    retainAudio.value = result.retain_audio
    retentionNotice.value = '원본 보관 설정을 저장했어요.'
  } catch (cause) {
    input.checked = retainAudio.value
    error.value = cause instanceof ApiError ? cause.message : '원본 보관 설정을 저장하지 못했어요.'
  } finally {
    savingRetention.value = false
  }
}

function updateReviewedPhoto(photo: Asset) {
  const current = assets.value.find(asset => asset.id === photo.id)
  if (!current) return
  Object.assign(current, { faces_blurred: photo.faces_blurred, face_check_confirmed: photo.face_check_confirmed })
  photoVersions.value[photo.id] = (photoVersions.value[photo.id] ?? 0) + 1
}

function applyRevocation() {
  emit('consentRevoked')
  void load().catch(() => { error.value = '녹음 자료 상태를 다시 확인하지 못했어요.' })
}

function addRecording(asset: Asset) {
  assets.value.push(asset)
  emit('changed')
}

async function upload(kind: 'photo' | 'slides' | 'reference', files: FileList | null) {
  if (!files?.length) return
  error.value = ''
  busy.value = true
  try {
    for (const file of Array.from(files)) {
      const form = new FormData()
      form.append('kind', kind)
      form.append('file', file)
      await api(base.value, { body: form })
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '서버에 연결하지 못했어요.'
  } finally {
    busy.value = false
    await load()
    emit('changed')
  }
}

function onPick(kind: 'photo' | 'slides' | 'reference', ev: Event) {
  const input = ev.target as HTMLInputElement
  void upload(kind, input.files)
  input.value = ''
}

async function remove(a: Asset) {
  if (!window.confirm(`'${a.display_name}'을(를) 지울까요?`)) return
  await api(`${base.value}/${a.id}`, { method: 'DELETE' })
  await load()
}

async function saveCaption(a: Asset) {
  error.value = ''
  try {
    const form = new URLSearchParams({ caption: a.caption })
    await api(`${base.value}/${a.id}/caption`, { method: 'PUT', body: form })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '설명을 저장하지 못했어요.'
  }
}

async function saveLink(a: Asset, blockId: string) {
  const form = new URLSearchParams({ block_id: blockId })
  const saved = await api<Asset>(`${base.value}/${a.id}/link`, { method: 'PUT', body: form })
  a.linked_block_id = saved.linked_block_id
  a.link_manual = saved.link_manual
}

function onLink(a: Asset, ev: Event) {
  void saveLink(a, (ev.target as HTMLSelectElement).value)
}

onMounted(load)
defineExpose({ reload: load })
</script>

<template>
  <section class="panel" aria-label="자료">
    <h2>사진</h2>
    <div class="actions">
      <label class="btn btn-primary pick">
        사진 올리기
        <input type="file" accept="image/jpeg,image/png,image/heic" multiple :disabled="busy" @change="onPick('photo', $event)" />
      </label>
      <label class="btn pick">
        바로 찍기
        <input type="file" accept="image/*" capture="environment" :disabled="busy" @change="onPick('photo', $event)" />
      </label>
      <span class="hint">{{ photos.length }} / {{ limits.photo ?? 200 }}장</span>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <ul v-if="photos.length" class="photos">
      <li v-for="p in photos" :key="p.id" class="photo">
        <img :src="`${base}/${p.id}/thumbnail?v=${photoVersions[p.id] ?? 0}`" :alt="p.caption || p.display_name" loading="lazy" />
        <PhotoFaceReview :path="`${base}/${p.id}`" :photo="p" @saved="updateReviewedPhoto" />
        <input v-model="p.caption" class="caption" maxlength="2000" placeholder="설명 (선택)" @change="saveCaption(p)" />
        <select class="link" :value="p.linked_block_id ?? ''" @change="onLink(p, $event)">
          <option value="">연결 안 함</option>
          <option v-for="(b, i) in blocks.filter((x) => x.revision > 0)" :key="b.id" :value="b.id">
            {{ blockLabel(b, i) }}
          </option>
        </select>
        <div class="foot">
          <span class="hint">{{ p.linked_block_id ? (p.link_manual ? '직접 연결' : '자동 연결') : '연결 없음' }}</span>
          <button class="btn btn-small" type="button" @click="remove(p)">지우기</button>
        </div>
      </li>
    </ul>

    <h2>발표자료와 참고자료</h2>
    <div class="actions">
      <label class="btn pick">
        발표자료(PDF, PPTX, 30MB까지)
        <input type="file" accept="application/pdf,.pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation" multiple :disabled="busy" @change="onPick('slides', $event)" />
      </label>
      <label class="btn pick">
        참고자료(PDF, TXT, MD)
        <input type="file" accept="application/pdf,.txt,.md,text/plain,text/markdown" multiple :disabled="busy" @change="onPick('reference', $event)" />
      </label>
    </div>
    <ul v-if="docs.length" class="docs">
      <li v-for="d in docs" :key="d.id">
        <span class="name">{{ d.display_name }}</span>
        <span class="hint">
          {{ d.kind === 'slides' ? '발표자료' : '참고자료' }} ·
          <template v-if="d.kind === 'slides' && d.page_count !== null">
            {{ d.page_count }}페이지 ·
          </template>
          {{ d.chunk_count ? `텍스트 ${d.chunk_count}조각` : '텍스트 없음' }}
        </span>
        <a class="btn btn-small" :href="`${base}/${d.id}/file`" :aria-label="`${d.display_name} 내려받기`" download>
          내려받기
        </a>
        <button class="btn btn-small" type="button" @click="remove(d)">지우기</button>
      </li>
    </ul>
    <RecordingConsent
      :session-id="sessionId"
      :active="active"
      :max-recording-bytes="maxRecordingBytes"
      @recorded="addRecording"
      @revoked="applyRevocation"
    />
    <div class="retention">
      <label class="retain-control">
        <input type="checkbox" :checked="retainAudio" :disabled="savingRetention" @change="saveRetention" />
        전사 후 음성 원본 보관
      </label>
      <p class="hint">전사 결과가 저장될 때의 설정을 적용해요. 삭제는 저장소에서 다시 시도될 수 있어요.</p>
      <p v-if="retentionNotice" class="hint" role="status">{{ retentionNotice }}</p>
    </div>
    <ul v-if="recordings.length" class="docs" aria-label="저장된 행사 녹음">
      <li v-for="recording in recordings" :key="recording.id">
        <span class="name">{{ recording.display_name }}</span>
        <span v-if="recording.consent_blocked" class="hint">녹음 동의가 철회됐어요</span>
        <span v-else-if="recording.status === 'original_deleted'" class="hint">원본 삭제됨</span>
        <span v-else-if="recording.status === 'original_delete_pending'" class="hint" role="status">원본 삭제 대기 중</span>
        <a v-else class="btn btn-small" :href="`${base}/${recording.id}/file`" download>녹음 내려받기</a>
        <button class="btn btn-small" type="button" @click="remove(recording)">지우기</button>
        <AudioTranscript
          v-if="!recording.consent_blocked && (transcriptionEnabled || ['ready', 'original_deleted', 'original_delete_pending'].includes(recording.status))"
          class="transcript"
          :session-id="sessionId"
          :asset="recording"
          :enabled="transcriptionEnabled"
          @asset-status="recording.status = $event"
        />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.panel { display: grid; gap: var(--space-4); }
h2 { margin: 0; font-family: var(--font-hand); font-weight: 400; letter-spacing: var(--ls-label); color: var(--text-muted-on-dark); }
.actions { display: flex; flex-wrap: wrap; gap: var(--space-4); align-items: center; }
.pick { display: inline-block; position: relative; }
.pick input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: inherit;
}
.pick:focus-within { outline: 3px solid var(--focus-ring); outline-offset: 2px; }
.pick:has(input:disabled) { opacity: 0.6; cursor: not-allowed; }
.hint { color: var(--color-lavender); font-size: var(--fs-hint); }
.error { margin: 0; background: var(--color-purple-dark); border: var(--border); border-color: var(--color-kiro); border-radius: var(--radius-bubble); padding: var(--space-3) var(--space-4); }
.photos { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-4); grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
.photo { display: grid; gap: var(--space-2); padding: var(--space-3); background: var(--color-white); color: var(--color-ink); border: var(--border); border-radius: var(--radius-bubble); }
.photo:has(details[open]) { grid-column: 1 / -1; }
.photo img { width: 100%; aspect-ratio: 4 / 3; object-fit: cover; border-radius: calc(var(--radius-bubble) - 6px); background: var(--color-lavender); }
.caption, .link { font: 500 var(--fs-btn-seg) var(--font-body); padding: var(--space-2) var(--space-3); border: var(--border); border-radius: var(--radius-pill); background: var(--color-white); color: var(--color-ink); min-width: 0; }
.foot { display: flex; justify-content: space-between; align-items: center; }
.foot .hint { color: var(--color-ink); }
.docs { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
.docs li { display: flex; gap: var(--space-4); align-items: center; flex-wrap: wrap; }
.retention { display: grid; gap: var(--space-2); }
.retention p { margin: 0; }
.retain-control { display: flex; align-items: center; gap: var(--space-2); }
.transcript { flex-basis: 100%; min-inline-size: 0; }
.name { font-weight: 700; word-break: break-all; }
</style>
