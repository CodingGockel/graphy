<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import SessionItem from './SessionItem.vue'
import StatusPanel from './StatusPanel.vue'
import AppWordmark from './AppWordmark.vue'
import { useI18n } from '../i18n'
import { activeId, sortedSessions } from '../state/sessions'
import { newSession, openSession } from '../state/chat'

// On mobile the sidebar is a drawer from the right (thumb reach); `open` only matters there.
defineProps<{ mobile: boolean; open: boolean }>()
const emit = defineEmits<{ close: []; navigate: []; openSettings: []; addSession: [] }>()

const { t } = useI18n()

function startNewSession(): void {
  newSession()
  emit('navigate')
}

function selectSession(id: string): void {
  if (id !== activeId.value) void openSession(id)
  emit('navigate')
}
</script>

<template>
  <aside
    class="sidebar"
    :class="{ mobile, open }"
    :aria-label="t('sidebar.label')"
    :inert="mobile && !open ? true : undefined"
  >
    <div class="head">
      <AppWordmark :height="26" class="brand" />
      <button
        v-if="mobile"
        type="button"
        class="btn btn-ghost btn-icon"
        :aria-label="t('sidebar.closeMenu')"
        @click="emit('close')"
      >
        <AppIcon name="close" />
      </button>
    </div>

    <div class="primary">
      <button type="button" class="btn" @click="startNewSession">
        <AppIcon name="plus" />
        {{ t('sidebar.newSession') }}
      </button>
      <button type="button" class="btn btn-ghost" @click="emit('addSession')">
        <AppIcon name="import" />
        {{ t('sidebar.addSession') }}
      </button>
    </div>

    <nav class="sessions" :aria-label="t('sidebar.sessions')">
      <h2 class="section-label">{{ t('sidebar.sessions') }}</h2>
      <ul v-if="sortedSessions.length" class="list">
        <SessionItem
          v-for="session in sortedSessions"
          :key="session.id"
          :session="session"
          :active="session.id === activeId"
          @select="selectSession(session.id)"
        />
      </ul>
      <p v-else class="empty">{{ t('sidebar.empty') }}</p>
    </nav>

    <div class="foot">
      <StatusPanel />
      <button type="button" class="btn btn-ghost settings" @click="emit('openSettings')">
        <AppIcon name="gear" />
        {{ t('sidebar.settings') }}
      </button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  width: var(--sidebar-width);
  flex-shrink: 0;
  height: 100%;
  background: var(--bg-subtle);
  border-right: 1px solid var(--border);
}

.sidebar.mobile {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  width: min(85vw, 320px);
  border-right: 0;
  border-left: 1px solid var(--border);
  border-radius: var(--radius-lg) 0 0 var(--radius-lg);
  box-shadow: var(--shadow-lg);
  transform: translateX(100%);
  visibility: hidden;
  transition:
    transform 0.15s ease-out,
    visibility 0.15s;
}

.sidebar.mobile.open {
  transform: none;
  visibility: visible;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: var(--topbar-height);
  padding: 0.25rem 0.5rem 0 1rem;
}

.brand {
  color: var(--text);
}

.primary {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.5rem 0.75rem 0.75rem;
}

.primary .btn {
  width: 100%;
}

.primary .btn:first-child {
  margin-bottom: 0.15rem;
  box-shadow: var(--shadow-sm);
}

.primary .btn-ghost {
  color: var(--text-muted);
}

.primary .btn-ghost:hover {
  color: var(--text);
}

.sessions {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.section-label {
  margin: 0;
  padding: 0.5rem 1.25rem 0.35rem;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.list {
  margin: 0;
  padding: 0 0 0.5rem;
}

.empty {
  margin: 0;
  padding: 0.25rem 1.25rem;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.foot {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.5rem 0.75rem 0.75rem;
  border-top: 1px solid var(--border);
}

.settings {
  width: 100%;
  padding-left: 0.6rem;
  color: var(--text-muted);
  font-size: 0.875rem;
}

.settings:hover {
  color: var(--text);
}
</style>
