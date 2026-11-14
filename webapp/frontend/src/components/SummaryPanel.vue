<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '@/api'
import type { SummaryResponse } from '@/types'

const props = defineProps<{ sessionId: string }>()
const path = computed(() => `/api/sessions/${props.sessionId}/summary`)

const data = ref<SummaryResponse | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const kindLabel: Record<string, string> = {
  memo: '메모',
  doc: '발표자료',
  reference: '참고자료',
  photo: '사진',
  transcript: '녹음',
}

async function load() {
  data.value = await api<SummaryResponse>(path.value)
}

async function create() {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const res = await api<SummaryResponse>(path.value, { method: 'POST' })
    data.value = res
    if (res.dropped_bullets) notice.value = `출처를 확인할 수 없는 항목 ${res.dropped_bullets}개는 뺐어요.`
    if (res.truncated) notice.value += ' 기록이 길어서 앞부분만 사용했어요.'
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '서버에 연결하지 못했어요.'
  } finally {
    busy.value = false
  }
}

onMounted(load)
defineExpose({ reload: load })
</script>

<template>
  <section class="panel" aria-label="AI 요약">
    <h2>AI 요약</h2>
    <div class="actions">
      <button class="btn btn-primary" type="button" :disabled="busy || data?.llm_configured === false" @click="create">
        {{ busy ? '요약하는 중…' : data?.summary ? '다시 요약하기' : '요약 만들기' }}
      </button>
      <span v-if="data?.llm_configured === false" class="hint">AI 제공자가 설정되지 않았어요(API 키 필요).</span>
      <span v-else class="hint">메모, 자료, 사진 설명을 근거로 요약해요. 모든 항목에 출처가 붙어요.</span>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="hint" role="status">{{ notice }}</p>

    <ol v-if="data?.summary" class="bullets">
      <li v-for="(b, i) in data.summary.bullets" :key="i" class="bullet">
        <p>{{ b.text }}</p>
        <ul class="chips" aria-label="출처">
          <li v-for="s in b.sources" :key="s.target_id" class="chip">
            <span v-if="!s.locator.startsWith(kindLabel[s.kind] ?? s.kind)" class="chip-kind">{{ kindLabel[s.kind] ?? s.kind }}</span>{{ s.locator }}
          </li>
        </ul>
      </li>
    </ol>
    <p v-if="data?.summary" class="hint">AI가 만든 요약이에요. 출처를 확인하며 읽어 주세요.</p>
  </section>
</template>

<style scoped>
.panel { display: grid; gap: var(--space-4); }
h2 { margin: 0; font-family: var(--font-hand); font-weight: 400; letter-spacing: var(--ls-label); color: var(--text-muted-on-dark); }
.actions { display: flex; flex-wrap: wrap; gap: var(--space-4); align-items: center; }
.hint { margin: 0; color: var(--color-lavender); font-size: var(--fs-hint); }
.error { margin: 0; background: var(--color-purple-dark); border: var(--border); border-color: var(--color-kiro); border-radius: var(--radius-bubble); padding: var(--space-3) var(--space-4); }
.bullets { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-4); }
.bullet { background: var(--color-white); color: var(--color-ink); border: var(--border); border-radius: var(--radius-bubble); padding: var(--space-4) var(--space-5); display: grid; gap: var(--space-3); }
.bullet p { margin: 0; line-height: 1.5; }
.chips { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-2); }
.chip { font-size: var(--fs-hint); background: var(--color-lavender); border: 2px solid var(--color-ink); border-radius: var(--radius-pill); padding: 2px var(--space-3); }
.chip-kind { font-weight: 700; margin-right: var(--space-2); color: var(--color-purple); }
</style>
