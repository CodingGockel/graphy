<script setup lang="ts">
import { useId } from 'vue'
import BaseDialog from './BaseDialog.vue'
import { LOCALES, LOCALE_NAMES, isLocale, useI18n } from '../i18n'
import { THEMES, setLocale, setTheme, settings } from '../state/settings'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const languageId = useId()

function onLanguageChange(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  if (isLocale(value)) void setLocale(value)
}
</script>

<template>
  <BaseDialog :open :title="t('settings.title')" @close="emit('close')">
    <div class="field">
      <label :for="languageId">{{ t('settings.language') }}</label>
      <select :id="languageId" class="input" :value="settings.locale" @change="onLanguageChange">
        <option v-for="locale in LOCALES" :key="locale" :value="locale">{{ LOCALE_NAMES[locale] }}</option>
      </select>
    </div>

    <fieldset class="field">
      <legend>{{ t('settings.theme') }}</legend>
      <label v-for="theme in THEMES" :key="theme" class="option">
        <input
          type="radio"
          name="theme"
          :value="theme"
          :checked="settings.theme === theme"
          @change="setTheme(theme)"
        />
        {{ t(`settings.theme_${theme}`) }}
      </label>
    </fieldset>
  </BaseDialog>
</template>

<style scoped>
.field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin: 0 0 1.25rem;
  padding: 0;
  border: 0;
}

.field:last-child {
  margin-bottom: 0;
}

label,
legend {
  font-weight: 600;
}

legend {
  padding: 0;
  margin-bottom: 0.35rem;
}

.option {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: normal;
  cursor: pointer;
}

.option input {
  margin: 0;
  accent-color: var(--accent);
}
</style>
