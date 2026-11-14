<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, ApiError } from '@/api'
import AssetsPanel from '@/components/AssetsPanel.vue'
import type { Block, SessionDetail } from '@/types'

type Row = Block & { state: 'saved' | 'dirty' | 'saving' | 'error'; message: string }

const route = useRoute()
const router = useRouter()
const id = route.params.id as string

const title = ref('')
const eventDate = ref('')
const rows = ref<Row[]>([])
const loading = ref(true)
const notice = ref('')
const timers = new Map<string, number>()
const assetsPanel = ref<InstanceType<typeof AssetsPanel> | null>(null)

function toRow(b: Block): Row {
  return { ...b, state: 'saved', message: `저장됨 · 수정 ${b.revision}번째` }
}

async function load() {
  const data = await api<SessionDetail>(`/api/sessions/${id}`)
  title.value = data.title
  eventDate.value = data.event_date ?? ''
  rows.value = data.blocks.map(toRow)
  if (!rows.value.length) addBlock()
  loading.value = false
}

function addBlock() {
  rows.value.push({
    id: crypto.randomUUID(),
    position: rows.value.length,
    text: '',
    revision: 0,
    state: 'saved',
    message: '',
  })
}

function onInput(row: Row) {
  row.state = 'dirty'
  row.message = '입력 중…'
  window.clearTimeout(timers.get(row.id))
  timers.set(row.id, window.setTimeout(() => save(row), 800))
}

async function save(row: Row) {
  if (!row.text.trim() && row.revision === 0) {
    row.state = 'saved'
    row.message = ''
    return
  }
  row.state = 'saving'
  row.message = '저장하는 중…'
  try {
    const saved = await api<Block>(`/api/sessions/${id}/blocks/${row.id}`, {
      method: 'PUT',
      json: { text: row.text, position: rows.value.indexOf(row) },
    })
    row.revision = saved.revision
    void assetsPanel.value?.reload()
    row.state = 'saved'
    row.message = `저장됨 · 수정 ${saved.revision}번째`
  } catch (e) {
    row.state = 'error'
    row.message = e instanceof ApiError ? e.message : '저장하지 못했어요.'
  }
}

async function removeBlock(row: Row) {
  window.clearTimeout(timers.get(row.id))
  if (row.revision > 0) await api(`/api/sessions/${id}/blocks/${row.id}`, { method: 'DELETE' })
  rows.value = rows.value.filter((r) => r.id !== row.id)
  if (!rows.value.length) addBlock()
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
onBeforeUnmount(() => timers.forEach((t) => window.clearTimeout(t)))
</script>

<template>
  <section class="page-body">
    <header class="top">
      <router-link class="back" :to="{ name: 'sessions' }">← 내 행사</router-link>
      <button class="btn btn-small" type="button" @click="removeSession">행사 삭제</button>
    </header>

    <p v-if="loading" class="hint">불러오는 중…</p>
    <template v-else>
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
      <button class="btn btn-primary" type="button" @click="addBlock">+ 메모 추가</button>

      <AssetsPanel ref="assetsPanel" :session-id="id" :blocks="rows" />
    </template>
  </section>
</template>

<style scoped>
.page-body { width: min(760px, 100%); padding: var(--space-6); display: grid; gap: var(--space-5); align-self: start; }
.top { display: flex; justify-content: space-between; align-items: center; }
.back { color: var(--color-lavender); text-decoration: none; }
.back:hover { text-decoration: underline; }
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
</style>
