<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '@/api'
import AssetsPanel from '@/components/AssetsPanel.vue'
import DraftPanel from '@/components/DraftPanel.vue'
import SummaryPanel from '@/components/SummaryPanel.vue'
import type { Block, SessionDetail } from '@/types'
import { useWorkspaceSection } from '@/workspace'

type Row = Block & { savedText: string; state: 'saved' | 'dirty' | 'saving' | 'error'; message: string }

const route = useRoute()
const router = useRouter()
const id = route.params.id as string
const section = useWorkspaceSection()

const title = ref('')
const eventDate = ref('')
const retainAudio = ref(false)
const rows = ref<Row[]>([])
const loading = ref(true)
const notice = ref('')
const timers = new Map<string, number>()
const pending = new Map<string, Promise<void>>()
const removing = new Set<string>()
let unmounted = false
const assetsPanel = ref<InstanceType<typeof AssetsPanel> | null>(null)

function toRow(b: Block): Row {
  return { ...b, savedText: b.text, state: 'saved', message: `저장됨 · 수정 ${b.revision}번째` }
}

async function load() {
  const data = await api<SessionDetail>(`/api/sessions/${id}`)
  title.value = data.title
  eventDate.value = data.event_date ?? ''
  retainAudio.value = data.retain_audio
  rows.value = data.blocks.map(toRow)
  if (!rows.value.length) addBlock()
  loading.value = false
}

function addBlock() {
  rows.value.push({
    id: crypto.randomUUID(),
    position: rows.value.length,
    text: '',
    savedText: '',
    revision: 0,
    state: 'saved',
    message: '',
  })
}

function clearSaveTimer(id: string) {
  window.clearTimeout(timers.get(id))
  timers.delete(id)
}

function onInput(row: Row) {
  row.state = 'dirty'
  row.message = '입력 중…'
  clearSaveTimer(row.id)
  timers.set(row.id, window.setTimeout(() => void save(row), 800))
}

function markSaved(row: Row) {
  row.state = 'saved'
  row.message = row.revision ? `저장됨 · 수정 ${row.revision}번째` : ''
}

async function save(row: Row) {
  clearSaveTimer(row.id)
  let previous: Promise<void> | undefined
  while ((previous = pending.get(row.id))) await previous
  if (unmounted || removing.has(row.id) || !rows.value.includes(row)) return
  if (row.text === row.savedText || (!row.text.trim() && row.revision === 0)) {
    markSaved(row)
    return
  }

  const request = persist(row, row.text).finally(() => pending.delete(row.id))
  pending.set(row.id, request)
  await request
}

async function persist(row: Row, text: string) {
  row.state = 'saving'
  row.message = '저장하는 중…'
  try {
    const saved = await api<Block>(`/api/sessions/${id}/blocks/${row.id}`, {
      method: 'PUT',
      json: { text, position: rows.value.indexOf(row) },
    })
    row.revision = saved.revision
    row.savedText = saved.text
    void assetsPanel.value?.reload()
    if (row.text === text) markSaved(row)
  } catch (e) {
    row.state = 'error'
    row.message = e instanceof ApiError ? e.message : '저장하지 못했어요.'
  }
}

async function removeBlock(row: Row) {
  if (removing.has(row.id)) return
  removing.add(row.id)
  clearSaveTimer(row.id)
  try {
    await pending.get(row.id)
    if (row.revision > 0) await api(`/api/sessions/${id}/blocks/${row.id}`, { method: 'DELETE' })
    rows.value = rows.value.filter((r) => r.id !== row.id)
    if (!rows.value.length) addBlock()
  } catch (e) {
    row.state = 'error'
    row.message = e instanceof ApiError ? e.message : '메모를 지우지 못했어요.'
  } finally {
    removing.delete(row.id)
  }
}

async function saveMeta() {
  notice.value = ''
  try {
    await api(`/api/sessions/${id}`, {
      method: 'PATCH',
      json: { title: title.value, event_date: eventDate.value || null },
    })
    notice.value = '저장했어요'
  } catch (e) {
    notice.value = e instanceof ApiError ? e.message : '저장하지 못했어요.'
  }
}

async function removeSession() {
  if (!window.confirm('이 행사와 모든 자료를 지울까요? 되돌릴 수 없어요.')) return
  await api(`/api/sessions/${id}`, { method: 'DELETE' })
  await router.replace({ name: 'sessions' })
}

onMounted(load)
onBeforeUnmount(() => {
  unmounted = true
  timers.forEach(timer => window.clearTimeout(timer))
})
</script>

<template>
  <section class="page-body">
    <p v-if="loading" class="hint">불러오는 중…</p>
    <template v-else>
      <header class="top">
        <h1>{{ title }}</h1>
        <button class="btn btn-small" type="button" @click="removeSession">행사 삭제</button>
      </header>

      <div v-show="section.id === 'notes'" class="notes">
        <form class="meta" @submit.prevent="saveMeta">
          <label class="field grow">
            <span>행사 이름</span>
            <input v-model="title" maxlength="200" required />
          </label>
          <label class="field">
            <span>날짜</span>
            <input v-model="eventDate" type="date" />
          </label>
          <button class="btn btn-small" type="submit">저장</button>
          <span v-if="notice" class="hint" role="status">{{ notice }}</span>
        </form>

        <h2>필기</h2>
        <ol class="blocks">
          <li v-for="row in rows" :key="row.id" class="block" :data-state="row.state">
            <textarea
              v-model="row.text"
              rows="3"
              maxlength="10000"
              placeholder="들으면서 적어 보세요"
              @input="onInput(row)"
              @blur="save(row)"
            />
            <div class="block-foot">
              <span class="hint" role="status">{{ row.message }}</span>
              <button class="btn btn-small" type="button" @click="removeBlock(row)">지우기</button>
            </div>
          </li>
        </ol>
        <div class="dock">
          <button class="btn btn-primary" type="button" @click="addBlock">+ 메모 추가</button>
        </div>
      </div>

      <SummaryPanel v-show="section.id === 'summary'" :session-id="id" />

      <DraftPanel v-show="section.id === 'draft'" :session-id="id" />

      <AssetsPanel
        v-show="section.id === 'assets'"
        v-model:retain-audio="retainAudio"
        ref="assetsPanel"
        :session-id="id"
        :blocks="rows"
        :active="section.id === 'assets'"
      />
    </template>
  </section>
</template>

<style scoped>
.page-body { width: min(760px, 100%); padding: var(--space-6); display: grid; gap: var(--space-5); align-self: start; }
.top { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--space-4); }
h1 { margin: 0; overflow-wrap: anywhere; }
.notes { display: grid; gap: var(--space-5); }
h2 { margin: 0; font-family: var(--font-hand); font-weight: 400; letter-spacing: var(--ls-label); color: var(--text-muted-on-dark); }
.hint { margin: 0; color: var(--color-lavender); font-size: var(--fs-hint); }
.meta { display: flex; gap: var(--space-4); align-items: flex-end; flex-wrap: wrap; }
.grow { flex: 1 1 240px; }
.blocks { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-4); }
.block { display: grid; gap: var(--space-2); }
.block textarea { font: 500 var(--fs-btn) var(--font-body); color: var(--color-ink); background: var(--color-white); border: var(--border); border-radius: var(--radius-bubble); padding: var(--space-4) var(--space-5); resize: vertical; min-height: 4.5em; }
.block[data-state='dirty'] textarea, .block[data-state='saving'] textarea { border-color: var(--color-kiro); }
.block[data-state='error'] textarea { border-color: var(--color-kiro); box-shadow: 0 0 0 3px var(--color-purple-dark); }
.block-foot { display: flex; justify-content: space-between; align-items: center; }
.dock { display: grid; }
/* 모바일에서는 메모 추가 버튼을 엄지가 닿는 화면 아래에 붙여 둔다(요구사항 2.6). */
@media (max-width: 700px) {
  .dock { position: sticky; bottom: var(--space-4); z-index: 2; }
  .page-body { padding: var(--space-4); }
}
</style>
