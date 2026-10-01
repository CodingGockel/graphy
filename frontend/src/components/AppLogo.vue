<script setup lang="ts">
// The Graphy icon (speech bubble with a small graph), same as public/favicon.svg
// and docs/designs/graphy-icon.svg.
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>

<template>
  <svg class="logo" :width="size" :height="size" viewBox="0 0 100 100" aria-hidden="true" focusable="false">
    <path class="bubble" d="M22.6,0H77.4A22.6,22.6 0 0 1 100,22.6V59A22.6,22.6 0 0 1 77.4,81.6H44.6L23.4,98.2Q20,100.9 20,96.6V81.45A22.6,22.6 0 0 1 0,59V22.6A22.6,22.6 0 0 1 22.6,0Z" />
    <path class="edges" d="M22.5,54L50,27L77.5,54" />
    <circle class="node" cx="50" cy="27" r="8.6" />
    <circle class="node" cx="22.5" cy="54" r="8.6" />
    <circle class="node" cx="77.5" cy="54" r="8.6" />
  </svg>
</template>

<style scoped>
.logo {
  display: block;
  flex-shrink: 0;
}

/* CSS variables only work via CSS, not in SVG presentation attributes. */
.bubble {
  fill: var(--brand);
}

.edges {
  fill: none;
  stroke: #fff;
  stroke-width: 4.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.node {
  fill: #fff;
}
</style>
