<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from '@/api'
import { useRouter } from 'vue-router'
import type { SessionItem } from '@/types'

const router = useRouter()
const items = ref<SessionItem[]>([])
const loading = ref(true)
const title = ref('')
const eventDate = ref('')
const error = ref('')

const statusLabels: Record<string, string> = {
  generating: '만드는 중',
  in_review: '검토 중',
  approved: '승인됨',
  failed: '만들지 못함',
}

async function load() {
  items.value = (await api<{ items: SessionItem[] }>('/api/sessions')).items
  loading.value = false
}

async function create() {
  error.value = ''
  try {
    const created = await api<{ id: string }>('/api/sessions', {
      json: { title: title.value, event_date: eventDate.value || null },
    })
    await router.push({ name: 'session', params: { id: created.id } })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '서버에 연결하지 못했어요.'
  }
}

onMounted(load)
</script>

<template>
  <section class="page-body">
    <h1>내 행사</h1>

    <form class="create" @submit.prevent="create">
      <label class="field grow">
        <span>행사 이름</span>
        <input v-model="title" maxlength="200" placeholder="예: AWS 밋업 서울" required />
      </label>
      <label class="field">
        <span>날짜</span>
        <input v-model="eventDate" type="date" />
      </label>
      <button class="btn btn-primary" type="submit" :disabled="!title.trim()">새 행사</button>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <p v-if="loading" class="hint">불러오는 중…</p>
    <p v-else-if="!items.length" class="hint">아직 행사가 없어요. 위에서 첫 행사를 만들어 보세요.</p>
    <ul v-else class="list">
      <li v-for="item in items" :key="item.id">
        <router-link class="item" :to="{ name: 'session', params: { id: item.id } }">
          <strong>{{ item.title }}</strong>
          <span class="meta">
            {{ item.event_date ?? '날짜 없음' }} · 자료 {{ item.asset_count }}개
            <template v-if="item.draft_status"> · 초안 {{ statusLabels[item.draft_status] ?? item.draft_status }}</template>
          </span>
        </router-link>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.page-body { width: min(760px, 100%); padding: var(--space-6); display: grid; gap: var(--space-5); align-self: start; }
h1 { margin: 0; }
.create { display: flex; gap: var(--space-4); align-items: flex-end; flex-wrap: wrap; }
.grow { flex: 1 1 240px; }
.hint { margin: 0; color: var(--color-lavender); }
.error { margin: 0; background: var(--color-purple-dark); border: var(--border); border-color: var(--color-kiro); border-radius: var(--radius-bubble); padding: var(--space-3) var(--space-4); }
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-4); }
.item { display: grid; gap: var(--space-1); padding: var(--space-4) var(--space-5); color: var(--color-ink); background: var(--color-white); border: var(--border); border-radius: var(--radius-bubble); box-shadow: var(--shadow-btn); text-decoration: none; transition: background var(--dur-base); }
.item:hover { background: var(--color-lavender); }
.meta { font-size: var(--fs-hint); }
@media (max-width: 700px) {
  .page-body { padding: var(--space-4); }
}
</style>
