<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import { useI18n } from '../i18n'

// The result of one step of the trace. Results are neither part of the chat stream nor of
// the history: it is loaded when the step is opened for the first time (ChatTrace mounts
// this component then) and kept from there on.
const props = defineProps<{ stepId: string }>()

const { t } = useI18n()

/** Rows of a query result that are rendered; the note below the table names the total. */
const MAX_ROWS = 50

interface Table {
  columns: string[]
  rows: string[][]
  total: number
}

type ResultView =
  | { type: 'empty' }
  | { type: 'table'; table: Table }
  | { type: 'candidates'; candidates: { label: string; uri: string }[] }
  | { type: 'text'; text: string }

type ResultState = { status: 'loading' } | { status: 'error' } | { status: 'loaded'; view: ResultView }

const state = ref<ResultState>({ status: 'loading' })

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value)
}

/** SPARQL JSON (`head.vars` / `results.bindings`, or `boolean` for ASK) as plain cell values. */
function toTable(result: Record<string, unknown>): Table | null {
  if (typeof result.boolean === 'boolean') {
    return { columns: [], rows: [[String(result.boolean)]], total: 1 }
  }
  const bindings = isRecord(result.results) ? result.results.bindings : null
  if (!Array.isArray(bindings)) return null
  const columns = isRecord(result.head) && Array.isArray(result.head.vars) ? result.head.vars.map(text) : []
  const rows = bindings.slice(0, MAX_ROWS).map((binding) =>
    columns.map((name) => {
      const cell = isRecord(binding) ? binding[name] : null
      return isRecord(cell) ? text(cell.value) : ''
    }),
  )
  return { columns, rows, total: bindings.length }
}

function toView(kind: string, result: unknown): ResultView {
  if (result == null) return { type: 'empty' }
  if (kind === 'resolve_entity' && Array.isArray(result)) {
    const candidates = result.filter(isRecord).map((c) => ({ label: text(c.label), uri: text(c.uri) }))
    return candidates.length ? { type: 'candidates', candidates } : { type: 'empty' }
  }
  const table = isRecord(result) ? toTable(result) : null
  if (table) return table.rows.length ? { type: 'table', table } : { type: 'empty' }
  // An unknown shape (a new backend tool) is shown as it is.
  return { type: 'text', text: typeof result === 'string' ? result : JSON.stringify(result, null, 2) }
}

onMounted(async () => {
  try {
    const { kind, result } = await api.getStepResult(props.stepId)
    state.value = { status: 'loaded', view: toView(kind, result) }
  } catch {
    state.value = { status: 'error' }
  }
})
</script>

<template>
  <p v-if="state.status === 'loading'">{{ t('trace.loading') }}</p>
  <p v-else-if="state.status === 'error'">{{ t('trace.loadFailed') }}</p>
  <p v-else-if="state.view.type === 'empty'">{{ t('trace.empty') }}</p>
  <template v-else-if="state.view.type === 'table'">
    <div class="table-wrap">
      <table>
        <thead v-if="state.view.table.columns.length">
          <tr>
            <th v-for="column in state.view.table.columns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, rowIndex) in state.view.table.rows" :key="rowIndex">
            <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="state.view.table.total > state.view.table.rows.length" class="note">
      {{ t('trace.rowsShown', { shown: state.view.table.rows.length, total: state.view.table.total }) }}
    </p>
  </template>
  <ul v-else-if="state.view.type === 'candidates'" class="candidates">
    <li v-for="candidate in state.view.candidates" :key="candidate.uri">
      {{ candidate.label }}
      <span class="uri">{{ candidate.uri }}</span>
    </li>
  </ul>
  <pre v-else>{{ state.view.text }}</pre>
</template>

<style scoped>
p,
pre,
ul,
.table-wrap {
  margin: 0 0 0.5rem;
}

pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--text);
}

.table-wrap {
  max-width: 100%;
  overflow-x: auto;
}

table {
  border-collapse: collapse;
  color: var(--text);
}

th,
td {
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

th {
  background: var(--bg-muted);
  font-weight: 600;
}

.candidates {
  padding-left: 1.1rem;
  color: var(--text);
}

.uri {
  display: block;
  color: var(--text-muted);
  font-size: 0.8rem;
  overflow-wrap: anywhere;
}
</style>
