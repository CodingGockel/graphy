<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

// "Working" indicator: a breadth-first traversal of a small graph. Each step draws the
// tree edges to the next level, then lights up the nodes it reached. Cross edges the
// traversal does not use stay grey, so the search tree becomes visible.
//
// Steps are driven by a timer rather than CSS keyframes, so the traversal still shows
// (just without the soft transitions) when the OS asks for reduced motion.

interface GraphNode {
  id: string
  x: number
  y: number
  /** Traversal step at which the node is reached. */
  step: number
}

interface GraphEdge {
  from: string
  to: string
  /** Step at which the traversal walks this edge; null for edges outside the search tree. */
  step: number | null
}

const NODES: GraphNode[] = [
  { id: 'a', x: 6, y: 16, step: 0 },
  { id: 'b', x: 24, y: 7, step: 1 },
  { id: 'c', x: 24, y: 25, step: 1 },
  { id: 'd', x: 44, y: 8, step: 2 },
  { id: 'e', x: 46, y: 25, step: 2 },
  { id: 'f', x: 66, y: 16, step: 3 },
]

const EDGES: GraphEdge[] = [
  { from: 'a', to: 'b', step: 1 },
  { from: 'a', to: 'c', step: 1 },
  { from: 'b', to: 'c', step: null },
  { from: 'b', to: 'd', step: 2 },
  { from: 'c', to: 'e', step: 2 },
  { from: 'd', to: 'e', step: null },
  { from: 'd', to: 'f', step: 3 },
  { from: 'e', to: 'f', step: null },
]

const LAST_STEP = 3
const HOLD_STEPS = 2
const STEP_MS = 420

const byId = Object.fromEntries(NODES.map((node) => [node.id, node]))

const edges = EDGES.map((edge) => {
  const a = byId[edge.from]
  const b = byId[edge.to]
  return { ...edge, d: `M${a.x} ${a.y}L${b.x} ${b.y}`, length: Math.hypot(b.x - a.x, b.y - a.y) }
})
const treeEdges = edges.filter((edge) => edge.step !== null)

/** Current traversal step; -1 is the short reset phase where everything fades out. */
const step = ref(0)
let timer = 0

onMounted(() => {
  timer = window.setInterval(() => {
    step.value = step.value >= LAST_STEP + HOLD_STEPS ? -1 : step.value + 1
  }, STEP_MS)
})

onBeforeUnmount(() => window.clearInterval(timer))

const reached = (at: number | null) => at !== null && step.value >= at
</script>

<template>
  <svg class="loader" width="72" height="32" viewBox="0 0 72 32" aria-hidden="true" focusable="false">
    <path v-for="edge in edges" :key="`base-${edge.from}${edge.to}`" class="edge" :d="edge.d" />
    <path
      v-for="edge in treeEdges"
      :key="`trail-${edge.from}${edge.to}`"
      class="trail"
      :d="edge.d"
      :style="{ strokeDasharray: edge.length, strokeDashoffset: reached(edge.step) ? 0 : edge.length }"
    />
    <g v-for="node in NODES" :key="node.id">
      <circle class="ring" :class="{ on: step === node.step }" :cx="node.x" :cy="node.y" r="6" />
      <circle
        class="node"
        :class="{ on: reached(node.step), late: node.step > 0 }"
        :cx="node.x"
        :cy="node.y"
        r="3.5"
      />
    </g>
  </svg>
</template>

<style scoped>
.loader {
  display: block;
  overflow: visible;
}

.edge,
.trail {
  fill: none;
  stroke-width: 1.75;
  stroke-linecap: round;
}

.edge {
  stroke: var(--border-strong);
}

.trail {
  stroke: var(--brand);
  transition: stroke-dashoffset 0.25s ease-out;
}

.node {
  fill: var(--border-strong);
  transition: fill 0.15s;
}

.node.on {
  fill: var(--brand);
}

/* A node lights up once the edge leading to it has been drawn. */
.node.on.late {
  transition-delay: 0.2s;
}

/* Soft ring around the nodes reached in the current step (the BFS frontier). */
.ring {
  fill: none;
  stroke: var(--brand);
  stroke-width: 1.5;
  opacity: 0;
  transition: opacity 0.2s;
}

.ring.on {
  opacity: 0.35;
  transition-delay: 0.2s;
}
</style>
