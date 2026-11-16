<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '@/api'

import type { Asset, ConsentRecord } from '@/types'
import BrowserRecording from './BrowserRecording.vue'

const props = defineProps<{ sessionId: string; active: boolean; maxRecordingBytes: number | null }>()
const emit = defineEmits<{ recorded: [asset: Asset] }>()
const base = `/api/sessions/${props.sessionId}/consents`
const records = ref<ConsentRecord[]>([])
const busy = ref(false)
const error = ref('')
const notice = ref('')

async function change(action: () => Promise<void>, fallback: string) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await action()
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : fallback
  } finally {
    busy.value = false
  }
}

function load() {
  return change(async () => {
    records.value = (await api<{items: ConsentRecord[]}>(base)).items
  }, '동의 기록을 불러오지 못했어요.')
}

function save(event: SubmitEvent) {
  const form = event.currentTarget as HTMLFormElement
  const body = new FormData(form)
  return change(async () => {
    const record = await api<ConsentRecord>(base, { body })
    records.value.unshift(record)
    form.reset()
    notice.value = '동의 기록을 저장했어요.'
  }, '동의 기록을 저장하지 못했어요.')
}

function revoke(record: ConsentRecord) {
  if (!window.confirm('이 동의를 철회할까요? 이 기록으로 새 녹음 자료를 올릴 수 없어요.')) return
  return change(async () => {
    const revoked = await api<ConsentRecord>(`/api/consents/${record.id}/revoke`, { method: 'POST' })
    records.value = records.value.map(item => item.id === revoked.id ? revoked : item)
    notice.value = '동의를 철회했어요.'
  }, '동의를 철회하지 못했어요.')
}

onMounted(load)
</script>

<template>
  <details class="consent">
    <summary>녹음 동의</summary>
    <form @submit.prevent="save">
      <fieldset :disabled="busy">
        <legend>새 동의 기록</legend>
        <label class="field">
          동의 날짜
          <input name="obtained_on" type="date" required />
        </label>
        <label class="field">
          동의 방법
          <input name="method" type="text" maxlength="500" required />
        </label>
        <label class="check">
          <input name="informed_all" type="checkbox" required />
          녹음 대상 모두에게 알리고 동의를 받았어요.
        </label>
        <label class="check">
          <input name="can_document" type="checkbox" required />
          동의 날짜와 방법을 기록할 수 있어요.
        </label>
        <label class="check">
          <input name="no_outside_disclosure" type="checkbox" required />
          녹음을 동의 범위 밖에서 공개하지 않아요.
        </label>
        <button class="btn btn-small" type="submit">동의 기록 저장</button>
      </fieldset>
    </form>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <ul v-if="records.length" aria-label="녹음 동의 기록">
      <li v-for="record in records" :key="record.id">
        <time :datetime="record.obtained_on">{{ record.obtained_on }}</time>
        <span class="method">{{ record.method }}</span>
        <span v-if="record.revoked_at">철회됨</span>
        <template v-else>
          <span>유효</span>
          <button
            class="btn btn-small"
            type="button"
            :aria-label="`${record.obtained_on} ${record.method} 동의 철회`"
            :disabled="busy"
            @click="revoke(record)"
          >
            동의 철회
          </button>
        </template>
      </li>
    </ul>
  </details>
  <BrowserRecording
    v-if="maxRecordingBytes !== null"
    :session-id="sessionId"
    :records="records"
    :active="active"
    :max-bytes="maxRecordingBytes"
    @recorded="emit('recorded', $event)"
  />
</template>

<style scoped>
summary { cursor: pointer; font-weight: 700; }
form, ul { margin-block-start: var(--space-4); }
fieldset {
  display: grid;
  gap: var(--space-3);
  min-inline-size: 0;
  margin: 0;
  padding: var(--space-3);
  border: var(--border);
  border-radius: var(--radius-bubble);
}
input { min-inline-size: 0; }
.check { display: flex; align-items: baseline; gap: var(--space-2); }
fieldset button { justify-self: start; }
ul { display: grid; gap: var(--space-3); list-style: none; padding: 0; }
li { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-3); }
.method { overflow-wrap: anywhere; }
</style>
