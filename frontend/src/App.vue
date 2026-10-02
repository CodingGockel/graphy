<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AddSessionDialog from './components/AddSessionDialog.vue'
import AppIcon from './components/AppIcon.vue'
import AppWordmark from './components/AppWordmark.vue'
import AppSidebar from './components/AppSidebar.vue'
import ChatView from './components/ChatView.vue'
import SettingsDialog from './components/SettingsDialog.vue'
import { useI18n } from './i18n'
import { openSession } from './state/chat'
import { overallStatus, startHealthPolling, statusSummaryKey } from './state/health'
import { activeId, refreshSessions } from './state/sessions'

const { t } = useI18n()

const mobileQuery = window.matchMedia('(max-width: 767px)')
const isMobile = ref(mobileQuery.matches)
const drawerOpen = ref(false)
const settingsOpen = ref(false)
const addSessionOpen = ref(false)

let stopHealthPolling: (() => void) | null = null

function onMobileChange(event: MediaQueryListEvent): void {
  isMobile.value = event.matches
  if (!event.matches) drawerOpen.value = false
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') drawerOpen.value = false
}

function openSettings(): void {
  drawerOpen.value = false
  settingsOpen.value = true
}

function openAddSession(): void {
  drawerOpen.value = false
  addSessionOpen.value = true
}

onMounted(() => {
  mobileQuery.addEventListener('change', onMobileChange)
  window.addEventListener('keydown', onKeydown)
  stopHealthPolling = startHealthPolling()
  void refreshSessions()
  // Resume the session that was open before the reload.
  if (activeId.value) void openSession(activeId.value)
})

onBeforeUnmount(() => {
  mobileQuery.removeEventListener('change', onMobileChange)
  window.removeEventListener('keydown', onKeydown)
  stopHealthPolling?.()
})
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <span class="brand">
        <AppWordmark :height="24" />
        <span
          class="dot"
          :class="overallStatus"
          role="img"
          :aria-label="t(statusSummaryKey)"
          :title="t(statusSummaryKey)"
        />
      </span>
      <button
        type="button"
        class="btn btn-ghost btn-icon"
        :aria-label="t('sidebar.openMenu')"
        :aria-expanded="drawerOpen"
        @click="drawerOpen = true"
      >
        <AppIcon name="menu" :size="20" />
      </button>
    </header>

    <div v-if="isMobile && drawerOpen" class="backdrop" @click="drawerOpen = false" />

    <AppSidebar
      :mobile="isMobile"
      :open="drawerOpen"
      @close="drawerOpen = false"
      @navigate="drawerOpen = false"
      @open-settings="openSettings"
      @add-session="openAddSession"
    />

    <main class="main">
      <ChatView />
    </main>

    <SettingsDialog :open="settingsOpen" @close="settingsOpen = false" />
    <AddSessionDialog :open="addSessionOpen" @close="addSessionOpen = false" />
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  height: 100dvh;
}

.main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.topbar {
  display: none;
}

.backdrop {
  position: fixed;
  inset: 0;
  z-index: 10;
  background: var(--overlay);
}

@media (max-width: 767px) {
  .layout {
    flex-direction: column;
  }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    height: var(--topbar-height);
    padding: 0 0.5rem 0 1rem;
    border-bottom: 1px solid var(--border);
    background: var(--bg-subtle);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }

  .main {
    min-height: 0;
  }
}
</style>
