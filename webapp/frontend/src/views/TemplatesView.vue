<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '@/api'
import type { TemplateDetail, TemplateInfo } from '@/types'

const route = useRoute()
const router = useRouter()
const templates = ref<TemplateInfo[]>([])
const current = ref<TemplateDetail>()
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const selectedId = computed(() => {
  const requested = route.query.template
  return typeof requested === 'string' && templates.value.some(item => item.id === requested)
    ? requested
    : templates.value[0]?.id
})

async function refreshList() {
  templates.value = (await api<{ templates: TemplateInfo[] }>('/api/templates')).templates
}

function fail(cause: unknown, fallback: string) {
  error.value = cause instanceof ApiError && cause.status !== 422 ? cause.message : fallback
}

function select(id: string) {
  return router.replace({ name: 'templates', query: { template: id } })
}

function listItem(template: TemplateDetail): TemplateInfo {
  return { id: template.id, name: template.name, sections: template.sections.map(section => section.title) }
}

watch(selectedId, async (id, _, onCleanup) => {
  if (!id || current.value?.id === id) return
  let active = true
  onCleanup(() => { active = false })
  current.value = undefined
  error.value = ''
  notice.value = ''
  loading.value = true
  try {
    const template = await api<TemplateDetail>(`/api/templates/${id}`)
    if (active) current.value = template
  } catch (cause) {
    if (active) fail(cause, '템플릿을 불러오지 못했어요.')
  } finally {
    if (active) loading.value = false
  }
})

onMounted(async () => {
  try {
    await refreshList()
  } catch (cause) {
    loading.value = false
    fail(cause, '템플릿 목록을 불러오지 못했어요.')
  }
})

async function clone() {
  if (!current.value) return
  const id = current.value.id
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const copy = await api<TemplateDetail>(`/api/templates/${id}:clone`, { method: 'POST' })
    templates.value.push(listItem(copy))
    current.value = copy
    await select(copy.id)
  } catch (cause) {
    fail(cause, '템플릿을 복제하지 못했어요.')
  } finally {
    busy.value = false
  }
}

async function save() {
  if (!current.value || current.value.built_in) return
  const { id, name, tone, sections } = current.value
  error.value = ''
  notice.value = ''
  busy.value = true
  try {
    const saved = await api<TemplateDetail>(`/api/templates/${id}`, {
      method: 'PUT', json: { name, tone, sections },
    })
    current.value = saved
    templates.value = templates.value.map(template => template.id === id ? listItem(saved) : template)
    notice.value = '템플릿을 저장했어요.'
  } catch (cause) {
    fail(cause, '템플릿 이름, 섹션 제목·지시와 문장 수를 확인해 주세요.')
  } finally {
    busy.value = false
  }
}

function addSection() {
  current.value?.sections.push({
    id: crypto.randomUUID(), title: '', instruction: '', max_sentences: 3, insight_slot: false,
  })
}

function moveSection(index: number, offset: number) {
  const sections = current.value?.sections
  if (!sections) return
  const [section] = sections.splice(index, 1)
  if (section) sections.splice(index + offset, 0, section)
}
</script>

<template>
  <section class="page-body">
    <h1>템플릿</h1>
    <div v-if="templates.length" class="toolbar">
      <label class="field picker">
        <span id="editor-template-label">편집할 템플릿</span>
        <select
          :value="selectedId"
          :disabled="busy"
          aria-labelledby="editor-template-label"
          @change="select(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="template in templates" :key="template.id" :value="template.id">
            {{ template.name }}
          </option>
        </select>
      </label>
      <button class="btn" type="button" :disabled="loading || busy || !current" @click="clone">
        복제
      </button>
    </div>
    <p v-if="loading" class="hint" role="status">템플릿을 불러오는 중…</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <template v-if="current">
      <div v-if="current.built_in" class="preview">
        <h2>{{ current.name }}</h2>
        <p class="hint">내장 템플릿을 편집하려면 복제해 주세요.</p>
        <p v-if="current.tone" class="hint">문체 {{ current.tone }}</p>
        <ol>
          <li v-for="section in current.sections" :key="section.id">
            <h3>{{ section.title }}</h3>
            <p>{{ section.instruction }}</p>
            <span class="hint">최대 {{ section.max_sentences }}문장</span>
          </li>
        </ol>
      </div>
      <form v-else class="editor" @submit.prevent="save">
        <fieldset class="editor-fields" :disabled="busy">
          <div class="identity">
            <label class="field">
              <span>템플릿 이름</span>
              <input v-model="current.name" maxlength="120" required />
            </label>
            <label class="field">
              <span>문체</span>
              <input v-model="current.tone" maxlength="2000" />
            </label>
          </div>
          <fieldset v-for="(section, index) in current.sections" :key="section.id" class="part">
            <legend>섹션 {{ index + 1 }}</legend>
            <label class="field">
              <span>섹션 제목</span>
              <input v-model="section.title" maxlength="120" required />
            </label>
            <label class="field">
              <span>작성 지시</span>
              <textarea v-model="section.instruction" rows="3" maxlength="2000" required />
            </label>
            <div class="section-settings">
              <label class="field sentences">
                <span>최대 문장 수</span>
                <input v-model.number="section.max_sentences" type="number" min="1" max="30" required />
              </label>
              <label class="insight">
                <input v-model="section.insight_slot" type="checkbox" />
                인사이트 추가란 표시
              </label>
            </div>
            <div class="toolbar">
              <button class="btn btn-small" type="button" :disabled="index === 0" @click="moveSection(index, -1)">위로</button>
              <button class="btn btn-small" type="button" :disabled="index === current.sections.length - 1" @click="moveSection(index, 1)">아래로</button>
              <button class="btn btn-small" type="button" :disabled="current.sections.length === 1" @click="current.sections.splice(index, 1)">섹션 삭제</button>
            </div>
          </fieldset>
          <div class="toolbar">
            <button class="btn" type="button" :disabled="current.sections.length === 20" @click="addSection">
              섹션 추가
            </button>
            <button class="btn btn-primary" type="submit">템플릿 저장</button>
            <p v-if="notice" class="hint" role="status">{{ notice }}</p>
          </div>
        </fieldset>
      </form>
    </template>
  </section>
</template>

<style scoped>
.page-body {
  width: min(760px, 100%);
  padding: var(--space-6);
  display: grid;
  gap: var(--space-5);
  align-self: start;
}
h1, h2, h3, p { margin: 0; }
h2, h3 { overflow-wrap: anywhere; }
.toolbar, .section-settings { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-3); }
.toolbar:has(.picker) { align-items: flex-end; }
.picker { flex: 1 1 12rem; min-width: 0; }
.picker select {
  width: 100%;
  min-height: 44px;
  padding: var(--space-2) var(--space-5);
  font: 500 var(--fs-btn) var(--font-body);
  color: var(--color-ink);
  background: var(--color-white);
  border: var(--border);
  border-radius: var(--radius-pill);
}
.editor-fields { display: grid; gap: var(--space-5); min-width: 0; margin: 0; padding: 0; border: 0; }
.identity { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 13rem), 1fr)); gap: var(--space-4); }
.identity input, .part input:not([type='checkbox']), .part textarea { width: 100%; min-width: 0; }
.part, .preview li {
  min-width: 0;
  display: grid;
  gap: var(--space-4);
  margin: 0;
  padding: var(--space-4) var(--space-5);
  border: var(--border);
  border-radius: var(--radius-bubble);
  background: var(--color-track);
}
.part legend { color: var(--color-lavender); padding: 0 var(--space-2); }
.part textarea { border-radius: var(--radius-bubble); resize: vertical; }
.sentences { width: 8rem; }
.insight { display: flex; align-items: center; gap: var(--space-2); color: var(--color-lavender); }
.insight input { accent-color: var(--color-kiro); }
.preview { display: grid; gap: var(--space-3); }
.preview ol { display: grid; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.preview p { overflow-wrap: anywhere; }
.hint { color: var(--color-lavender); font-size: var(--fs-btn-sm); }
.error { padding: var(--space-4); border-radius: var(--radius-bubble); background: var(--color-purple-dark); }

@media (max-width: 700px) {
  .page-body { padding: var(--space-4); }
}
</style>
