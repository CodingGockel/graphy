<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import { useI18n } from '../i18n'

const props = defineProps<{ pending: boolean; disabled: boolean }>()
const emit = defineEmits<{ send: [text: string]; stop: [] }>()

const MAX_HEIGHT = 200

const { t } = useI18n()
const text = ref('')
const textarea = ref<HTMLTextAreaElement | null>(null)

const canSend = computed(() => !props.pending && !props.disabled && text.value.trim().length > 0)

function resize(): void {
  const el = textarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
}

function submit(): void {
  if (!canSend.value) return
  emit('send', text.value)
  text.value = ''
}

// Enter sends, Shift+Enter inserts a newline; never send mid IME composition.
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    submit()
  }
}

watch(text, () => nextTick(resize))

onMounted(() => {
  // Don't pop up the on-screen keyboard on touch devices.
  if (window.matchMedia('(pointer: fine)').matches) textarea.value?.focus()
})
</script>

<template>
  <form class="composer" @submit.prevent="submit">
    <textarea
      ref="textarea"
      v-model="text"
      class="field"
      rows="1"
      :placeholder="t('chat.placeholder')"
      :aria-label="t('chat.inputLabel')"
      :disabled="disabled"
      @keydown="onKeydown"
    />
    <button
      v-if="pending"
      type="button"
      class="btn btn-icon action"
      :aria-label="t('chat.stop')"
      :title="t('chat.stop')"
      @click="emit('stop')"
    >
      <AppIcon name="stop" />
    </button>
    <button
      v-else
      type="submit"
      class="btn btn-primary btn-icon action"
      :aria-label="t('chat.send')"
      :title="t('chat.send')"
      :disabled="!canSend"
    >
      <AppIcon name="send" />
    </button>
  </form>
</template>

<style scoped>
.composer {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  padding: 0.5rem 0.5rem 0.5rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg);
  box-shadow: var(--shadow-sm);
  transition:
    border-color 0.12s,
    box-shadow 0.12s;
}

.composer:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

.field {
  flex: 1;
  min-width: 0;
  max-height: 200px;
  padding: 0.35rem 0.25rem;
  border: 0;
  background: transparent;
  resize: none;
  line-height: 1.5;
}

.field:focus-visible {
  outline: none;
}

.action {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: var(--radius);
}
</style>
