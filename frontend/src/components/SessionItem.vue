<script setup lang="ts">
import { nextTick, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { useI18n } from '../i18n'
import { toApiError } from '../api/client'
import { errorHeadline } from '../lib/errors'
import { renameSession, type SessionEntry } from '../state/sessions'
import { deleteSession } from '../state/chat'

const props = defineProps<{ session: SessionEntry; active: boolean }>()
const emit = defineEmits<{ select: [] }>()

const { t } = useI18n()
const actionsOpen = ref(false)
const editing = ref(false)
const draft = ref('')
const copied = ref(false)
const input = ref<HTMLInputElement | null>(null)

async function copyId(): Promise<void> {
  actionsOpen.value = false
  try {
    await navigator.clipboard.writeText(props.session.id)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    // Clipboard API is unavailable outside secure contexts: let the user copy by hand.
    window.prompt(t('session.copyFallback'), props.session.id)
  }
}

async function startRename(): Promise<void> {
  actionsOpen.value = false
  draft.value = props.session.title
  editing.value = true
  await nextTick()
  input.value?.select()
}

function commitRename(): void {
  if (!editing.value) return
  editing.value = false
  const title = draft.value.trim()
  if (title) renameSession(props.session.id, title)
}

function cancelRename(): void {
  editing.value = false
}

async function remove(): Promise<void> {
  actionsOpen.value = false
  if (!window.confirm(t('session.confirmDelete', { title: props.session.title }))) return
  try {
    await deleteSession(props.session.id)
  } catch (err) {
    window.alert(t('session.deleteFailed', { error: errorHeadline(toApiError(err)) }))
  }
}
</script>

<template>
  <li class="item" :class="{ active }">
    <div class="row">
      <input
        v-if="editing"
        ref="input"
        v-model="draft"
        class="input rename"
        :aria-label="t('session.titleLabel')"
        @keydown.enter.prevent="commitRename"
        @keydown.esc.prevent.stop="cancelRename"
        @blur="commitRename"
      />
      <template v-else>
        <button
          type="button"
          class="title"
          :title="session.title"
          :aria-current="active ? 'true' : undefined"
          @click="emit('select')"
        >
          <span class="text">{{ session.title }}</span>
          <span v-if="copied" class="copied">{{ t('session.copied') }}</span>
        </button>
        <button
          type="button"
          class="btn btn-ghost btn-icon more"
          :class="{ shown: actionsOpen }"
          :aria-label="t('session.actions')"
          :aria-expanded="actionsOpen"
          @click="actionsOpen = !actionsOpen"
        >
          <AppIcon name="dots" :size="16" />
        </button>
      </template>
    </div>
    <div v-if="actionsOpen" class="actions">
      <button type="button" class="action" @click="copyId">{{ t('session.copyId') }}</button>
      <button type="button" class="action" @click="startRename">{{ t('session.rename') }}</button>
      <button type="button" class="action danger" @click="remove">{{ t('session.delete') }}</button>
    </div>
  </li>
</template>

<style scoped>
.item {
  margin: 1px 0.75rem;
  list-style: none;
  border-radius: var(--radius-sm);
}

.row {
  display: flex;
  align-items: center;
  min-height: 2.25rem;
  border-radius: var(--radius-sm);
  transition: background-color 0.12s;
}

.item:hover .row {
  background: var(--bg-hover);
}

.item.active .row {
  background: var(--accent-subtle);
}

.item.active .text {
  color: var(--accent);
  font-weight: 500;
}

.title {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.25rem 0.4rem 0.6rem;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  text-align: left;
  font-size: 0.9rem;
  cursor: pointer;
}

.text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.copied {
  flex-shrink: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.more {
  padding: 0.3rem;
  margin-right: 0.2rem;
  color: var(--text-muted);
  visibility: hidden;
}

.more:hover:not(:disabled) {
  background: var(--bg-muted);
  color: var(--text);
}

.item:hover .more,
.item.active .more,
.more.shown,
.more:focus-visible {
  visibility: visible;
}

@media (hover: none) {
  .more {
    visibility: visible;
  }
}

.rename {
  margin: 0.15rem 0;
  padding: 0.3rem 0.5rem;
  font-size: 0.9rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  padding: 0.35rem 0.6rem 0.5rem;
}

.action {
  padding: 0.1rem 0;
  border: 0;
  background: none;
  color: var(--text-muted);
  font-size: 0.85rem;
  cursor: pointer;
}

.action:hover {
  color: var(--text);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.action.danger:hover {
  color: var(--danger);
}
</style>
