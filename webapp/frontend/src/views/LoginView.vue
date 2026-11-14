<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api'
import { login } from '@/auth'

const router = useRouter()
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await login(password.value)
    await router.replace({ name: 'sessions' })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '서버에 연결하지 못했어요.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="card" @submit.prevent="submit">
    <p class="label">OPEN ATTENDEE</p>
    <h1>필기 도구에 로그인</h1>
    <p class="hint">밋업 들으러 가는 당신을 위한 요약 도구</p>
    <!-- 브라우저 비밀번호 관리자가 계정을 알아보도록 숨긴 사용자명 칸 -->
    <input type="text" name="username" value="owner" autocomplete="username" hidden />
    <label class="field">
      <span>비밀번호</span>
      <input v-model="password" type="password" autocomplete="current-password" autofocus required />
    </label>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button class="btn btn-primary" type="submit" :disabled="busy || !password">
      {{ busy ? '확인하는 중…' : '로그인' }}
    </button>
  </form>
</template>

<style scoped>
.card { display: grid; gap: var(--space-5); width: min(420px, 100%); padding: var(--space-6); }
.label { font-family: var(--font-hand); letter-spacing: var(--ls-label); color: var(--text-muted-on-dark); margin: 0; }
h1 { margin: 0; font-size: clamp(22px, 4vw, 32px); }
.hint { margin: 0; color: var(--color-lavender); font-size: var(--fs-btn-seg); }
.error { margin: 0; color: var(--color-white); background: var(--color-purple-dark); border: var(--border); border-color: var(--color-kiro); border-radius: var(--radius-bubble); padding: var(--space-3) var(--space-4); }
</style>
