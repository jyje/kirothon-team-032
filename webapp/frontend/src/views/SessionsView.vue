<script setup lang="ts">
import { useRouter } from 'vue-router'
import { logout } from '@/auth'

const router = useRouter()

async function signOut() {
  await logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <section class="home">
    <p class="label">OPEN ATTENDEE</p>
    <h1>로그인했어요</h1>
    <p class="hint">세션 목록은 다음 단계에서 붙여요.</p>
    <button class="btn" type="button" @click="signOut">로그아웃</button>
  </section>
</template>

<style scoped>
.home { display: grid; gap: var(--space-5); justify-items: center; padding: var(--space-6); text-align: center; }
.label { font-family: var(--font-hand); letter-spacing: var(--ls-label); color: var(--text-muted-on-dark); margin: 0; }
h1 { margin: 0; }
.hint { margin: 0; color: var(--color-lavender); }
</style>
