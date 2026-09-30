<script setup lang="ts">
import { onMounted, ref, useId, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import { useI18n } from '../i18n'

// Thin wrapper around the native <dialog>: modal, focus trap and Esc come for free.
const props = defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const dialog = ref<HTMLDialogElement | null>(null)
const titleId = useId()

function sync(): void {
  const el = dialog.value
  if (!el) return
  if (props.open && !el.open) el.showModal()
  else if (!props.open && el.open) el.close()
}

watch(() => props.open, sync)
onMounted(sync)
</script>

<template>
  <dialog ref="dialog" class="dialog" :aria-labelledby="titleId" @close="emit('close')">
    <header class="head">
      <h2 :id="titleId">{{ title }}</h2>
      <button type="button" class="btn btn-ghost btn-icon" :aria-label="t('dialog.close')" @click="emit('close')">
        <AppIcon name="close" />
      </button>
    </header>
    <div class="body">
      <slot />
    </div>
  </dialog>
</template>

<style scoped>
.dialog {
  width: min(28rem, calc(100vw - 2rem));
  padding: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg);
  color: var(--text);
  box-shadow: var(--shadow-lg);
}

.dialog::backdrop {
  background: var(--overlay);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 0.75rem 0.25rem 1.25rem;
}

.head h2 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.body {
  padding: 0.75rem 1.25rem 1.25rem;
}
</style>
