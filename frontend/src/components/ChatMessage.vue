<script setup lang="ts">
import { computed } from 'vue'
import AppLogo from './AppLogo.vue'
import { useI18n } from '../i18n'
import { renderMarkdown } from '../lib/markdown'
import type { ChatEntry } from '../state/chat'

const props = defineProps<{ message: ChatEntry }>()

const { t } = useI18n()
const html = computed(() => (props.message.role === 'assistant' ? renderMarkdown(props.message.content) : ''))
</script>

<template>
  <article v-if="message.role === 'user'" class="message user">
    <span class="visually-hidden">{{ t('chat.you') }}:</span>
    <p class="bubble text">{{ message.content }}</p>
  </article>
  <article v-else class="message assistant">
    <AppLogo :size="26" class="avatar" />
    <span class="visually-hidden">Graphy:</span>
    <!-- Sanitized with DOMPurify in renderMarkdown. -->
    <div class="bubble markdown" v-html="html" />
  </article>
</template>

<style scoped>
.message {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  margin: 0 0 1.25rem;
}

.user {
  justify-content: flex-end;
}

.bubble {
  min-width: 0;
  margin: 0;
  padding: 0.65rem 0.95rem;
  border-radius: var(--radius-lg);
  overflow-wrap: anywhere;
}

/* The flattened corner points at the speaker, like a speech bubble tail. */
.user .bubble {
  max-width: 85%;
  background: var(--accent-subtle);
  border-top-right-radius: 4px;
  white-space: pre-wrap;
}

.assistant .bubble {
  max-width: calc(100% - 26px - 0.65rem);
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-top-left-radius: 4px;
}

.avatar {
  margin-top: 0.3rem;
}

.markdown > :deep(:first-child) {
  margin-top: 0;
}

.markdown > :deep(:last-child) {
  margin-bottom: 0;
}

.markdown :deep(p),
.markdown :deep(ul),
.markdown :deep(ol),
.markdown :deep(pre),
.markdown :deep(table),
.markdown :deep(blockquote) {
  margin: 0 0 0.85rem;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  margin: 1.1rem 0 0.5rem;
  font-size: 1rem;
  font-weight: 600;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  padding-left: 1.4rem;
}

.markdown :deep(li + li) {
  margin-top: 0.2rem;
}

.markdown :deep(code) {
  padding: 0.1rem 0.3rem;
  border-radius: 4px;
  background: var(--bg-muted);
}

.markdown :deep(pre) {
  padding: 0.75rem;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
}

.markdown :deep(pre code) {
  padding: 0;
  background: none;
}

.markdown :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.markdown :deep(th),
.markdown :deep(td) {
  padding: 0.35rem 0.6rem;
  border: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.markdown :deep(th) {
  background: var(--bg-muted);
  font-weight: 600;
}

.markdown :deep(blockquote) {
  padding-left: 0.75rem;
  border-left: 3px solid var(--border-strong);
  color: var(--text-muted);
}

.markdown :deep(hr) {
  border: 0;
  border-top: 1px solid var(--border);
}

@media (max-width: 767px) {
  .avatar {
    display: none;
  }

  .assistant .bubble {
    max-width: 100%;
  }
}
</style>
