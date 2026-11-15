<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { logout } from '@/auth'
import { useWorkspaceSection, workspaceSections } from '@/workspace'

defineProps<{ expanded: boolean }>()
const emit = defineEmits<{ toggle: []; close: [] }>()
const route = useRoute()
const router = useRouter()
const currentSection = useWorkspaceSection()
const menuButton = ref<HTMLButtonElement>()
const signOutError = ref('')
const signingOut = ref(false)

function closeMenu() {
  emit('close')
  menuButton.value?.focus()
}

async function signOut() {
  signOutError.value = ''
  signingOut.value = true
  try {
    await logout()
    await router.replace({ name: 'login' })
  } catch {
    signOutError.value = '로그아웃하지 못했어요. 다시 시도해 주세요.'
  } finally {
    signingOut.value = false
  }
}
</script>

<template>
  <aside class="sidebar" :data-expanded="expanded" @keydown.esc="expanded && closeMenu()">
    <div class="masthead">
      <span class="wordmark">Open Attendee</span>
      <button
        ref="menuButton"
        class="btn btn-small toggle"
        type="button"
        aria-controls="workspace-menu"
        :aria-expanded="expanded"
        @click="emit('toggle')"
      >
        {{ expanded ? '메뉴 닫기' : '메뉴 열기' }}
      </button>
    </div>

    <div id="workspace-menu" class="menu">
      <nav aria-label="작업 공간">
        <router-link
          class="nav-link"
          :class="{ selected: route.name === 'sessions' }"
          :to="{ name: 'sessions' }"
        >내 행사</router-link>
        <ul v-if="route.name === 'session'" class="section-links">
          <li v-for="section in workspaceSections" :key="section.id">
            <router-link
              v-slot="{ href, navigate }"
              :to="{ name: 'session', params: { id: route.params.id }, hash: `#${section.id}` }"
              custom
            >
              <a
                class="nav-link"
                :class="{ selected: currentSection.id === section.id }"
                :aria-current="currentSection.id === section.id ? 'location' : undefined"
                :href="href"
                @click="navigate"
              >{{ section.label }}</a>
            </router-link>
          </li>
        </ul>
      </nav>
      <div class="account">
        <button class="btn btn-small" type="button" :disabled="signingOut" @click="signOut">
          로그아웃
        </button>
        <p v-if="signOutError" class="sign-out-error" role="alert">{{ signOutError }}</p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  display: grid;
  align-content: start;
  gap: var(--space-5);
  position: sticky;
  top: var(--inset);
  align-self: start;
  min-width: 0;
  padding: var(--space-5);
  background: var(--color-track);
  border: var(--border);
  border-radius: var(--radius-frame-sm);
  box-shadow: var(--shadow-btn);
}
.masthead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.wordmark {
  font-family: var(--font-hand);
  font-size: clamp(1rem, 2.2vw, 1.3rem);
  color: var(--color-lavender);
}
.menu { display: grid; gap: var(--space-6); }
.toggle { display: none; }
.nav-link {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: var(--space-2) var(--space-4);
  color: var(--color-white);
  border: var(--border);
  border-color: transparent;
  border-radius: var(--radius-pill);
  text-decoration: none;
}
.nav-link:hover { background: var(--color-purple-dark); }
.nav-link.selected {
  background: var(--color-lavender);
  color: var(--color-ink);
  border-color: var(--color-ink);
  box-shadow: var(--shadow-btn);
  font-weight: 700;
}
.section-links {
  display: grid;
  gap: var(--space-1);
  list-style: none;
  margin: var(--space-2) 0 0 var(--space-3);
  padding: 0 0 0 var(--space-3);
  border-inline-start: var(--border-w) solid var(--color-purple);
}
.account { display: grid; justify-items: start; gap: var(--space-2); }
.sign-out-error { margin: 0; font-size: var(--fs-btn-sm); color: var(--color-lavender); }

@media (max-width: 700px) {
  .sidebar { position: static; gap: var(--space-4); padding: var(--space-3) var(--space-4); }
  .toggle { display: inline-block; min-height: 44px; }
  .sidebar[data-expanded='false'] .menu { display: none; }
}
</style>
