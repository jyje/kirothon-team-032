<script setup lang="ts">
import { ref } from 'vue'
import { useAiJob } from '@/aiJobs'
import { api, ApiError } from '@/api'
import type { Asset, Transcript } from '@/types'

const props = defineProps<{ sessionId: string; asset: Asset; enabled: boolean }>()
const result = ref<Transcript>()
const attemptedLoad = ref(false)
const loadError = ref('')
const { busy, error, status, restore, submit } = useAiJob(
  props.sessionId, 'transcribe', readResult, props.asset.id,
)

async function readResult() {
  result.value = await api<Transcript>(
    `/api/sessions/${props.sessionId}/assets/${props.asset.id}/transcript`,
  )
}

async function expand(event: Event) {
  if (!(event.currentTarget as HTMLDetailsElement).open || attemptedLoad.value) return
  attemptedLoad.value = true
  try {
    await readResult()
  } catch (cause) {
    loadError.value = cause instanceof ApiError ? cause.message : '전사 결과를 불러오지 못했어요.'
  }
  if (props.enabled && !result.value?.completed && !loadError.value) await restore()
}

function time(ms: number) {
  const seconds = Math.floor(ms / 1000)
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map(part => String(part).padStart(2, '0')).join(':')
    + '.' + String(ms % 1000).padStart(3, '0')
}
</script>

<template>
  <details @toggle="expand">
    <summary>전사</summary>
    <button
      v-if="enabled && result && !result.completed"
      class="btn btn-small"
      type="button"
      :disabled="busy"
      @click="submit()"
    >전사 시작</button>
    <p v-if="status && !result?.completed" role="status">{{ status }}</p>
    <p v-if="loadError || error" role="alert">{{ loadError || error }}</p>
    <p v-if="result?.completed && !result.segments.length">말소리를 찾지 못했어요.</p>
    <ol v-if="result?.segments.length">
      <li v-for="segment in result.segments" :key="`${segment.start_ms}-${segment.end_ms}-${segment.text}`">
        <span class="time">{{ time(segment.start_ms) }}~{{ time(segment.end_ms) }}</span>
        {{ segment.text }}
      </li>
    </ol>
  </details>
</template>

<style scoped>
summary { cursor: pointer; font-weight: 700; }
button, ol { margin-block-start: var(--space-3); }
ol { display: grid; gap: var(--space-2); padding-inline-start: var(--space-5); }
li { overflow-wrap: anywhere; }
.time { color: var(--text-muted-on-dark); font-variant-numeric: tabular-nums; }
</style>
