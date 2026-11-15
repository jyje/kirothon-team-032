<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorkspaceSidebar from '@/components/WorkspaceSidebar.vue'

const route = useRoute()
const showSidebar = computed(() => route.name === 'sessions' || route.name === 'session')
const menuExpanded = ref(false)
const main = ref<HTMLElement>()

watch(() => route.fullPath, (_, previous) => {
  menuExpanded.value = false
  if (previous !== '/') main.value?.focus({ preventScroll: true })
}, { flush: 'post' })
</script>

<template>
  <div class="page">
    <div class="frame" :class="{ workspace: showSidebar }">
      <WorkspaceSidebar
        v-if="showSidebar"
        :expanded="menuExpanded"
        @toggle="menuExpanded = !menuExpanded"
        @close="menuExpanded = false"
      />
      <main ref="main" class="main" tabindex="-1">
        <router-view v-slot="{ Component }">
          <component :is="Component" :key="route.path" />
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.main { display: grid; place-items: center; width: 100%; min-width: 0; }
.main:focus { outline: none; }
.workspace {
  grid-template-columns: minmax(12rem, 15rem) minmax(0, 1fr);
  align-items: start;
  justify-items: stretch;
  padding: var(--space-5);
}

@media (max-width: 700px) {
  .workspace {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto 1fr;
    gap: var(--space-4);
    padding: var(--space-3);
  }
}
</style>
