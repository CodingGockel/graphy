<script setup lang="ts">
import { nextTick, ref, useId, watch } from 'vue'
import BaseDialog from './BaseDialog.vue'
import { useI18n } from '../i18n'
import { ApiError, toApiError } from '../api/client'
import { errorHeadline } from '../lib/errors'
import { importSession } from '../state/chat'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const { t } = useI18n()
const inputId = useId()
const hintId = useId()
const input = ref<HTMLInputElement | null>(null)
const value = ref('')
const error = ref('')
const busy = ref(false)

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    value.value = ''
    error.value = ''
    busy.value = false
    await nextTick()
    input.value?.focus()
  },
)

async function submit(): Promise<void> {
  const id = value.value.trim().toLowerCase()
  if (!UUID_PATTERN.test(id)) {
    error.value = t('addSession.invalid')
    return
  }
  busy.value = true
  error.value = ''
  try {
    await importSession(id)
    emit('close')
  } catch (err) {
    error.value =
      err instanceof ApiError && err.status === 404 ? t('addSession.notFound') : errorHeadline(toApiError(err))
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseDialog :open :title="t('addSession.title')" @close="emit('close')">
    <form @submit.prevent="submit">
      <p :id="hintId" class="hint">{{ t('addSession.description') }}</p>
      <label :for="inputId" class="label">{{ t('addSession.label') }}</label>
      <input
        :id="inputId"
        ref="input"
        v-model="value"
        class="input id"
        autocomplete="off"
        spellcheck="false"
        placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        :aria-describedby="hintId"
        :aria-invalid="error ? 'true' : undefined"
      />
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="actions">
        <button type="button" class="btn" @click="emit('close')">{{ t('addSession.cancel') }}</button>
        <button type="submit" class="btn btn-primary" :disabled="busy || !value.trim()">
          {{ busy ? t('addSession.checking') : t('addSession.submit') }}
        </button>
      </div>
    </form>
  </BaseDialog>
</template>

<style scoped>
.hint {
  margin: 0 0 1rem;
  color: var(--text-muted);
}

.label {
  display: block;
  margin-bottom: 0.35rem;
  font-weight: 600;
}

.id {
  font-family: var(--font-mono);
  font-size: 0.9em;
}

.error {
  margin: 0.5rem 0 0;
  color: var(--danger);
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1.25rem;
}
</style>
