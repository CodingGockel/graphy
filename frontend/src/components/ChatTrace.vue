<script setup lang="ts">
import { reactive } from 'vue'
import AppIcon from './AppIcon.vue'
import TraceResult from './TraceResult.vue'
import { useI18n } from '../i18n'
import type { StepItem, TraceItem } from '../state/chat'

// What the agent did before the answer: every reasoning part and every tool call as its
// own collapsible item, in the order they happened.
defineProps<{ items: TraceItem[] }>()

const { t, te } = useI18n()

/** Step kinds that store a result worth loading. */
const KINDS_WITH_RESULT = ['sparql_query', 'resolve_entity']

// Steps that have been opened once: their result is loaded then (TraceResult) and stays.
const opened = reactive(new Set<string>())

function isKnownKind(kind: string): boolean {
  return te(`trace.kind.${kind}`)
}

function kindLabel(kind: string): string {
  // A kind this frontend does not know (a new backend tool) shows up under its own name.
  return isKnownKind(kind) ? t(`trace.kind.${kind}`) : kind
}

function stateLabel(step: StepItem): string {
  switch (step.status) {
    case 'running':
      return '…'
    case 'failed':
      return t('trace.failed')
    case 'cancelled':
      return t('trace.cancelled')
    default: {
      if (step.count === null) return ''
      const unit = step.kind === 'resolve_entity' ? 'candidates' : 'rows'
      return t(`trace.${unit}_${step.count === 1 ? 'one' : 'other'}`, { count: step.count })
    }
  }
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value)
}

/** A step with nothing to show inside is a plain line instead of a collapsible item. */
function hasBody(step: StepItem): boolean {
  return Boolean(step.error) || (step.kind !== 'papers' && step.kind !== 'clarification')
}

function showsResult(step: StepItem): boolean {
  return step.status === 'ok' && KINDS_WITH_RESULT.includes(step.kind) && opened.has(step.id)
}

function onToggle(event: Event, step: StepItem): void {
  if ((event.target as HTMLDetailsElement).open) opened.add(step.id)
}
</script>

<template>
  <div class="trace">
    <template v-for="(item, index) in items" :key="item.type === 'step' ? item.id : index">
      <details v-if="item.type === 'thinking'" class="item">
        <summary>
          <AppIcon name="chevron" :size="14" class="chevron" />
          {{ t('chat.reasoning') }}
        </summary>
        <p class="body reasoning">{{ item.text }}</p>
      </details>

      <p v-else-if="!hasBody(item)" class="item line">
        {{ kindLabel(item.kind) }}
        <span v-if="stateLabel(item)" class="state">· {{ stateLabel(item) }}</span>
      </p>

      <details v-else class="item" @toggle="onToggle($event, item)">
        <summary>
          <AppIcon name="chevron" :size="14" class="chevron" />
          {{ kindLabel(item.kind) }}
          <span v-if="stateLabel(item)" class="state">· {{ stateLabel(item) }}</span>
        </summary>
        <div class="body">
          <template v-if="item.kind === 'sparql_query'">
            <p class="label">{{ t('trace.query') }}</p>
            <pre>{{ text(item.args.query) }}</pre>
          </template>
          <dl v-else-if="item.kind === 'resolve_entity'" class="facts">
            <dt>{{ t('trace.term') }}</dt>
            <dd>{{ text(item.args.term) }}</dd>
            <template v-if="item.args.type">
              <dt>{{ t('trace.type') }}</dt>
              <dd>{{ text(item.args.type) }}</dd>
            </template>
          </dl>
          <p v-else-if="item.kind === 'previous_results'">
            {{ t('trace.turn', { turn: text(item.args.reference_turn) }) }}
          </p>
          <pre v-else-if="!isKnownKind(item.kind)">{{ JSON.stringify(item.args, null, 2) }}</pre>

          <p v-if="item.error" class="failure">{{ item.error }}</p>

          <template v-if="showsResult(item)">
            <p class="label">{{ t('trace.result') }}</p>
            <TraceResult :step-id="item.id" />
          </template>
        </div>
      </details>
    </template>
  </div>
</template>

<style scoped>
.trace {
  margin: -0.15rem 0 0.6rem;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.item + .item {
  margin-top: 0.1rem;
}

summary,
.line {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.1rem 0.4rem 0.1rem 0.2rem;
  margin: 0 0 0 -0.2rem;
  border-radius: var(--radius-sm);
}

/* Not collapsible: aligned with the labels next to a chevron. */
.line {
  display: flex;
  padding-left: calc(0.2rem + 14px + 0.3rem);
}

summary {
  cursor: pointer;
  list-style: none;
  user-select: none;
  transition:
    background-color 0.12s,
    color 0.12s;
}

summary::-webkit-details-marker {
  display: none;
}

summary:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.chevron {
  transform: rotate(-90deg);
  transition: transform 0.12s;
}

.item[open] > summary .chevron {
  transform: none;
}

.body {
  max-height: 20rem;
  margin: 0.4rem 0 0.5rem;
  padding: 0.1rem 0 0.1rem 0.75rem;
  overflow-y: auto;
  border-left: 2px solid var(--border-strong);
  font-size: 0.875rem;
}

.reasoning {
  white-space: pre-wrap;
}

.body p,
.body pre,
.body dl,
.body ul {
  margin: 0 0 0.5rem;
}

.body > :last-child {
  margin-bottom: 0;
}

.body pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--text);
}

.label {
  font-weight: 600;
}

.failure {
  color: var(--text);
  white-space: pre-wrap;
}

.facts {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.15rem 0.75rem;
}

.facts dd {
  margin: 0;
  color: var(--text);
}
</style>
