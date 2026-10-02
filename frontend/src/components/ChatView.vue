<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import AppLogo from './AppLogo.vue'
import AppWordmark from './AppWordmark.vue'
import ChatInput from './ChatInput.vue'
import GraphLoader from './GraphLoader.vue'
import ChatMessage from './ChatMessage.vue'
import { useI18n } from '../i18n'
import { errorHeadline } from '../lib/errors'
import { aborted, chatError, loadingHistory, messages, newSession, pending, send, stop } from '../state/chat'

const { t } = useI18n()
const scroller = ref<HTMLElement | null>(null)

const isEmpty = computed(
  () => messages.value.length === 0 && !loadingHistory.value && !pending.value && !chatError.value,
)

function scrollToEnd(): void {
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}

// A new message, the loader or an error: bring it into view.
watch(
  () => [messages.value, messages.value.length, pending.value, aborted.value, chatError.value],
  async () => {
    await nextTick()
    scrollToEnd()
  },
)

// What grows while a turn is streamed: the answer text, the trace and its last item.
function streamProgress(): unknown[] {
  const last = messages.value[messages.value.length - 1]
  const item = last?.trace[last.trace.length - 1]
  return [last?.content.length, last?.trace.length, item?.type === 'thinking' ? item.text.length : item?.status]
}

// Follow it, unless the user has scrolled up to read something.
watch(streamProgress, async () => {
  const el = scroller.value
  // Measured before the DOM grows.
  const atEnd = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 80
  await nextTick()
  if (atEnd) scrollToEnd()
})
</script>

<template>
  <div class="chat">
    <div ref="scroller" class="scroll">
      <div class="column">
        <div v-if="isEmpty" class="empty">
          <h1>
            <AppWordmark :height="52" />
          </h1>
          <p>{{ t('chat.emptyText') }}</p>
        </div>

        <ChatMessage v-for="message in messages" :key="message.id" :message="message" />

        <p v-if="loadingHistory" class="status">{{ t('chat.loadingHistory') }}</p>
        <div v-if="pending" class="thinking" role="status">
          <AppLogo :size="28" class="avatar" />
          <div class="bubble">
            <GraphLoader />
            <span class="visually-hidden">{{ t('chat.thinking') }}</span>
          </div>
        </div>
        <p v-if="aborted" class="status">{{ t('chat.aborted') }}</p>

        <div v-if="chatError" class="error" role="alert">
          <p class="headline">{{ chatError.retry ? errorHeadline(chatError.error) : t('chat.sessionGone') }}</p>
          <details v-if="chatError.error.status !== 0" class="details">
            <summary>{{ t('chat.details') }}</summary>
            <p>
              <template v-if="chatError.error.status > 0">{{ chatError.error.status }} · </template>
              {{ chatError.error.message }}
            </p>
            <pre v-if="chatError.error.detail">{{ chatError.error.detail }}</pre>
          </details>
          <button v-if="chatError.retry" type="button" class="btn" @click="chatError.retry?.()">
            {{ t('chat.retry') }}
          </button>
          <button v-else type="button" class="btn" @click="newSession()">{{ t('sidebar.newSession') }}</button>
        </div>
      </div>
    </div>

    <div class="bottom">
      <div class="column">
        <ChatInput :pending :disabled="loadingHistory" @send="send" @stop="stop" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.scroll {
  /* Containing block for absolutely positioned children (e.g. .visually-hidden labels),
     otherwise they extend the page height and the whole page scrolls. */
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.column {
  width: 100%;
  max-width: var(--content-width);
  margin: 0 auto;
  padding: 0 1rem;
}

.scroll .column {
  padding-top: 1.5rem;
  padding-bottom: 1rem;
}

.bottom {
  padding-bottom: max(1rem, env(safe-area-inset-bottom));
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18vh 0 2rem;
  text-align: center;
}

.empty h1 {
  margin: 0 0 1rem;
  color: var(--text);
}

.empty p {
  margin: 0;
  color: var(--text-muted);
}

.status {
  margin: 0 0 1.25rem;
  color: var(--text-muted);
  font-size: 0.9rem;
  text-align: center;
}

/* Mirrors the assistant bubble in ChatMessage.vue. */
.thinking {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  margin: 0 0 1.25rem;
}

.thinking .avatar {
  margin-top: 0.3rem;
}

.thinking .bubble {
  position: relative;
  padding: 0.7rem 0.95rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  border-top-left-radius: 4px;
  background: var(--bg-subtle);
}

@media (max-width: 767px) {
  .thinking .avatar {
    display: none;
  }
}

.error {
  margin: 0 0 1.25rem;
  padding: 0.8rem 1rem;
  border: 1px solid var(--danger);
  border-radius: var(--radius);
  background: var(--danger-subtle);
}

.headline {
  margin: 0 0 0.5rem;
  color: var(--danger);
  font-weight: 600;
}

.details {
  margin-bottom: 0.75rem;
  font-size: 0.9rem;
}

.details summary {
  cursor: pointer;
  color: var(--text-muted);
}

.details p {
  margin: 0.5rem 0 0;
}

.details pre {
  margin: 0.5rem 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
