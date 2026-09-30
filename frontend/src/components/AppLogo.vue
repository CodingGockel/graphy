<script setup lang="ts">
// The Graphy mark: a small triangle graph, same as public/favicon.svg.
withDefaults(defineProps<{ size?: number }>(), { size: 22 })
</script>

<template>
  <svg class="logo" :width="size" :height="size" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <rect class="tile" width="32" height="32" rx="8" />
    <path class="edges" d="M9 22 16 9 23 22Z" />
    <circle class="node" cx="9" cy="22" r="3" />
    <circle class="node" cx="16" cy="9" r="3" />
    <circle class="node" cx="23" cy="22" r="3" />
  </svg>
</template>

<style scoped>
.logo {
  display: block;
  flex-shrink: 0;
}

/* CSS variables only work via CSS, not in SVG presentation attributes. */
.tile {
  fill: var(--accent);
}

.edges {
  fill: none;
  stroke: var(--accent-text);
  stroke-width: 2;
  stroke-linejoin: round;
}

.node {
  fill: var(--accent-text);
}
</style>
