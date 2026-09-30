<script setup lang="ts">
import { ref, useId } from 'vue'
import AppIcon from './AppIcon.vue'
import { useI18n } from '../i18n'
import { errorHeadline } from '../lib/errors'
import {
  backendStatus,
  checkedAt,
  checking,
  health,
  healthError,
  overallStatus,
  refreshHealth,
  statusSummaryKey,
} from '../state/health'

const { t, te, locale } = useI18n()
const expanded = ref(false)
const detailsId = useId()

// Known service keys get a friendly name; unknown ones are shown as the backend sends them.
function serviceName(key: string): string {
  return te(`status.services.${key}`) ? t(`status.services.${key}`) : key
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="status">
    <button
      type="button"
      class="summary"
      :aria-expanded="expanded"
      :aria-controls="detailsId"
      :title="t('status.title')"
      @click="expanded = !expanded"
    >
      <span class="dot" :class="overallStatus" />
      <span class="label">{{ t(statusSummaryKey) }}</span>
      <AppIcon name="chevron" :size="16" class="chevron" :class="{ open: expanded }" />
    </button>

    <div v-if="expanded" :id="detailsId" class="details">
      <ul class="services">
        <li class="service">
          <div class="line">
            <span class="dot" :class="backendStatus" />
            <span class="name">{{ t('status.backend') }}</span>
            <span class="state">{{ t(`status.state_${backendStatus}`) }}</span>
          </div>
          <p v-if="healthError" class="error">{{ errorHeadline(healthError) }}</p>
        </li>
        <li v-for="(service, key) in health?.services ?? {}" :key="key" class="service">
          <div class="line">
            <span class="dot" :class="service.status" />
            <span class="name">{{ serviceName(String(key)) }}</span>
            <span class="state">{{ t(`status.state_${service.status}`) }}</span>
          </div>
          <p v-if="service.error" class="error">{{ service.error }}</p>
        </li>
      </ul>
      <div class="meta">
        <span>{{ checkedAt ? t('status.lastChecked', { time: formatTime(checkedAt) }) : '' }}</span>
        <button
          type="button"
          class="btn btn-ghost btn-icon refresh"
          :disabled="checking"
          :aria-label="t('status.refresh')"
          :title="t('status.refresh')"
          @click="refreshHealth"
        >
          <AppIcon name="refresh" :size="14" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.summary {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
  padding: 0.45rem 0.6rem;
  border: 0;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--text-muted);
  font-size: 0.875rem;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.12s,
    color 0.12s;
}

.summary:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chevron {
  transition: transform 0.12s;
}

.chevron.open {
  transform: rotate(180deg);
}

.details {
  margin: 0.25rem 0 0.5rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  font-size: 0.85rem;
}

.services {
  margin: 0;
  padding: 0;
  list-style: none;
}

.service + .service {
  margin-top: 0.4rem;
}

.line {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.name {
  flex: 1;
  min-width: 0;
}

.state {
  color: var(--text-muted);
}

.error {
  margin: 0.2rem 0 0 1.1rem;
  color: var(--text-muted);
  font-size: 0.8rem;
  overflow-wrap: anywhere;
}

.meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding-top: 0.4rem;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 0.8rem;
}

.refresh {
  padding: 0.25rem;
}
</style>
