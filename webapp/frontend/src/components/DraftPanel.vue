<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from '@/api'
import type { Draft, DraftResponse, DraftSentence, TemplateInfo } from '@/types'

const props = defineProps<{ sessionId: string }>()
const base = computed(() => `/api/sessions/${props.sessionId}/draft`)

const templates = ref<TemplateInfo[]>([])
const templateId = ref('builtin-blog')
const draft = ref<Draft | null>(null)
const llmConfigured = ref<boolean | null>(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const editingId = ref('')
const editText = ref('')
const insightText = ref<Record<string, string>>({})

const kindLabel: Record<string, string> = { memo: '메모', doc: '발표자료', reference: '참고자료', photo: '사진', transcript: '녹음' }
const approved = computed(() => draft.value?.status === 'approved')

function fail(e: unknown, fallback: string) {
  error.value = e instanceof ApiError ? e.message : fallback
}

async function load() {
  const res = await api<DraftResponse>(base.value)
  draft.value = res.draft
  llmConfigured.value = res.llm_configured
  templates.value = (await api<{ templates: TemplateInfo[] }>('/api/templates')).templates
}

async function create() {
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const res = await api<DraftResponse>(base.value, { json: { template_id: templateId.value } })
    draft.value = res.draft
  } catch (e) {
    fail(e, '서버에 연결하지 못했어요.')
  } finally {
    busy.value = false
  }
}

async function call(path: string, init: Parameters<typeof api>[1]) {
  error.value = ''
  try {
    draft.value = (await api<Draft>(path, init)) as Draft
  } catch (e) {
    fail(e, '요청에 실패했어요.')
  }
}

const sentenceUrl = (s: DraftSentence) => `/api/drafts/${draft.value!.id}/sentences/${s.id}`
const keepAsOpinion = (s: DraftSentence) => call(sentenceUrl(s), { method: 'PATCH', json: { action: 'keep_as_opinion' } })
const remove = (s: DraftSentence) => call(sentenceUrl(s), { method: 'DELETE' })

function startEdit(s: DraftSentence) {
  editingId.value = s.id
  editText.value = s.text
}
async function saveEdit(s: DraftSentence) {
  await call(sentenceUrl(s), { method: 'PATCH', json: { text: editText.value } })
  editingId.value = ''
}

async function addInsight(sectionId: string) {
  const text = (insightText.value[sectionId] ?? '').trim()
  if (!text) return
  await call(`/api/drafts/${draft.value!.id}/insights`, { json: { section_id: sectionId, text } })
  insightText.value[sectionId] = ''
}

async function approve() {
  if (!window.confirm('이 초안을 승인할까요? 승인하면 더 고칠 수 없고, 내보낼 수 있어요.')) return
  await call(`/api/drafts/${draft.value!.id}/approve`, { method: 'POST' })
}

async function copyMarkdown() {
  notice.value = ''
  try {
    const res = await fetch(`/api/drafts/${draft.value!.id}/export.md`, { credentials: 'same-origin' })
    await navigator.clipboard.writeText(await res.text())
    notice.value = '마크다운을 복사했어요.'
  } catch {
    notice.value = '복사하지 못했어요. 내려받기를 써 주세요.'
  }
}

onMounted(load)
</script>

<template>
  <section class="panel" aria-label="초안">
    <h2>초안</h2>
    <div class="actions">
      <label v-if="templates.length" class="picker">
        <span id="draft-template-label">템플릿</span>
        <select v-model="templateId" aria-labelledby="draft-template-label" :disabled="busy || approved">
          <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }} ({{ t.sections.join(' · ') }})</option>
        </select>
      </label>
      <button class="btn btn-primary" type="button" :disabled="busy || llmConfigured === false || approved" @click="create">
        {{ busy ? '초안을 만드는 중…' : draft ? '다시 만들기' : '초안 만들기' }}
      </button>
      <span v-if="llmConfigured === false" class="hint">AI 제공자가 설정되지 않았어요(API 키 필요).</span>
      <span v-else-if="!draft" class="hint">모든 문장에 출처가 붙고, 확인되지 않은 문장은 "미검증"으로 표시돼요.</span>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <template v-if="draft">
      <p class="hint" role="status">
        <strong>{{ approved ? '승인됨' : '검토 중' }}</strong>
        <template v-if="draft.template_name"> · 템플릿 {{ draft.template_name }}</template>
        <template v-if="!approved"> · 미검증 문장 {{ draft.unverified_count }}개</template>
        · AI가 만든 초안이에요. 출처를 확인하며 검토해 주세요.
      </p>

      <article v-for="section in draft.sections" :key="section.id" class="section">
        <h3>{{ section.title }}</h3>
        <p v-if="!section.sentences.length" class="hint">이 섹션에는 문장이 없어요.</p>
        <ul class="sentences">
          <li v-for="s in section.sentences" :key="s.id" class="sentence" :data-status="s.verify_status">
            <div class="badges">
              <span v-if="s.verify_status === 'verified'" class="badge ok">출처 확인됨 · AI 판단</span>
              <span v-else-if="s.verify_status === 'unverified'" class="badge warn">미검증</span>
              <span v-else-if="s.verify_status === 'kept_as_opinion'" class="badge">의견으로 유지 · 출처 미확인</span>
              <span v-else class="badge">내 인사이트</span>
              <span v-if="s.origin === 'ai_edited'" class="badge">수정함</span>
              <span v-if="s.verify_note && s.verify_status === 'unverified'" class="hint-dark">{{ s.verify_note }}</span>
            </div>
            <template v-if="editingId === s.id">
              <textarea v-model="editText" rows="2" maxlength="1000" />
              <div class="row">
                <button class="btn btn-small" type="button" @click="saveEdit(s)">저장</button>
                <button class="btn btn-small" type="button" @click="editingId = ''">취소</button>
              </div>
            </template>
            <template v-else>
              <p class="text">{{ s.text }}</p>
              <ul v-if="s.sources.length" class="chips" aria-label="출처">
                <li v-for="(src, i) in s.sources" :key="i" class="chip">
                  <span v-if="!src.locator.startsWith(kindLabel[src.kind] ?? src.kind)" class="chip-kind">{{ kindLabel[src.kind] ?? src.kind }}</span>{{ src.locator }}
                </li>
              </ul>
              <div v-if="!approved" class="row">
                <button class="btn btn-small" type="button" @click="startEdit(s)">수정</button>
                <button v-if="s.verify_status === 'unverified'" class="btn btn-small" type="button" @click="keepAsOpinion(s)">의견으로 유지</button>
                <button class="btn btn-small" type="button" @click="remove(s)">삭제</button>
              </div>
            </template>
          </li>
        </ul>
        <form v-if="section.insight_slot && !approved" class="insight" @submit.prevent="addInsight(section.id)">
          <label class="field">
            <span>내 인사이트 추가</span>
            <input v-model="insightText[section.id]" maxlength="1000" placeholder="내 생각을 한 문장으로" />
          </label>
          <button class="btn btn-small" type="submit">추가</button>
        </form>
      </article>

      <div class="actions">
        <button v-if="!approved" class="btn btn-primary" type="button" :disabled="draft.unverified_count > 0" @click="approve">
          승인하기{{ draft.unverified_count ? ` (미검증 ${draft.unverified_count}개 남음)` : '' }}
        </button>
        <template v-else>
          <a class="btn" :href="`/api/drafts/${draft.id}/export.md`" download="open-attendee-draft.md">마크다운 내려받기</a>
          <button class="btn" type="button" @click="copyMarkdown">복사</button>
        </template>
        <span v-if="notice" class="hint" role="status">{{ notice }}</span>
      </div>
    </template>
  </section>
</template>

<style scoped>
.panel { display: grid; gap: var(--space-4); }
h2 { margin: 0; font-family: var(--font-hand); font-weight: 400; letter-spacing: var(--ls-label); color: var(--text-muted-on-dark); }
h3 { margin: 0 0 var(--space-3); font-size: 18px; }
.actions { display: flex; flex-wrap: wrap; gap: var(--space-4); align-items: center; }
.actions a.btn { text-decoration: none; display: inline-block; }
.picker { display: grid; min-width: 0; max-width: 100%; gap: var(--space-1); font-size: var(--fs-hint); color: var(--text-muted-on-dark); }
.picker select { font: 500 var(--fs-btn-seg) var(--font-body); color: var(--color-ink); background: var(--color-white); border: var(--border); border-radius: var(--radius-pill); padding: var(--space-2) var(--space-4); min-height: 44px; min-width: 0; max-width: 100%; text-overflow: ellipsis; }
.hint { margin: 0; color: var(--color-lavender); font-size: var(--fs-hint); }
.error { margin: 0; background: var(--color-purple-dark); border: var(--border); border-color: var(--color-kiro); border-radius: var(--radius-bubble); padding: var(--space-3) var(--space-4); }
.section { display: grid; gap: var(--space-3); }
.sentences { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-3); }
.sentence { background: var(--color-white); color: var(--color-ink); border: var(--border); border-radius: var(--radius-bubble); padding: var(--space-4) var(--space-5); display: grid; gap: var(--space-2); }
.sentence[data-status='unverified'] { border-color: var(--color-kiro); box-shadow: 0 0 0 3px var(--color-kiro); }
.text { margin: 0; line-height: 1.5; }
.badges { display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center; }
.badge { font-size: var(--fs-hint); font-weight: 700; border: 2px solid var(--color-ink); border-radius: var(--radius-pill); padding: 1px var(--space-3); background: var(--color-white); }
.badge.ok { background: var(--color-lavender); }
.badge.warn { background: var(--color-kiro); color: var(--color-white); }
.hint-dark { font-size: var(--fs-hint); }
.row { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.chips { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: var(--space-2); }
.chip { font-size: var(--fs-hint); background: var(--color-lavender); border: 2px solid var(--color-ink); border-radius: var(--radius-pill); padding: 2px var(--space-3); }
.chip-kind { font-weight: 700; margin-right: var(--space-2); color: var(--color-purple); }
textarea { font: 500 var(--fs-btn) var(--font-body); border: var(--border); border-radius: var(--radius-bubble); padding: var(--space-3) var(--space-4); resize: vertical; }
.insight { display: flex; gap: var(--space-3); align-items: flex-end; flex-wrap: wrap; }
.insight .field { flex: 1 1 240px; }
</style>
