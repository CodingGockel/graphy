<script setup lang="ts">
import { computed } from 'vue'

// A small inline SVG icon set (24x24, stroked), so no icon library is needed.
type IconName = 'menu' | 'close' | 'plus' | 'import' | 'dots' | 'send' | 'stop' | 'gear' | 'chevron' | 'refresh'

const ICONS: Record<IconName, { d: string; width?: number }> = {
  menu: { d: 'M4 6h16M4 12h16M4 18h16' },
  close: { d: 'M6 6l12 12M18 6L6 18' },
  plus: { d: 'M12 5v14M5 12h14' },
  import: { d: 'M12 3v12M7 10l5 5 5-5M5 20h14' },
  dots: { d: 'M5 12h.01M12 12h.01M19 12h.01', width: 3 },
  send: { d: 'M12 19V5M5 12l7-7 7 7' },
  stop: { d: 'M8 7h8a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z' },
  chevron: { d: 'M6 9l6 6 6-6' },
  refresh: { d: 'M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5' },
  gear: {
    d:
      'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z' +
      'M12 5.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 1 0 0-13z' +
      'M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21' +
      'M5.64 5.64l1.76 1.76M16.6 16.6l1.76 1.76M5.64 18.36l1.76-1.76M16.6 7.4l1.76-1.76',
  },
}

const props = withDefaults(defineProps<{ name: IconName; size?: number }>(), { size: 18 })

const icon = computed(() => ICONS[props.name])
</script>

<template>
  <svg
    class="icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="icon.width ?? 1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path :d="icon.d" />
  </svg>
</template>

<style scoped>
.icon {
  flex-shrink: 0;
  display: block;
}
</style>
