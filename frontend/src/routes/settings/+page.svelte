<script lang="ts">
    import { onMount } from 'svelte';
    import {
        defaultSettings,
        loadSettings,
        saveSettings,
        type AppSettings,
        type CsvSeparator,
        type Language,
        type PreviewHeight,
        type Theme
    } from '$lib/settings';

    // Lokaler Formularzustand für die einzelnen Einstellungsfelder.
    let fastMode = $state(defaultSettings.fastMode);
    let csvSeparator = $state<CsvSeparator>(defaultSettings.csvSeparator);
    let showQueryDefault = $state(defaultSettings.showQueryDefault);
    let previewHeight = $state<PreviewHeight>(defaultSettings.previewHeight);
    let language = $state<Language>(defaultSettings.language);
    let theme = $state<Theme>(defaultSettings.theme);

    onMount(() => {
        // Beim Öffnen werden zuvor gespeicherte Werte in das Formular übernommen.
        applySettings(loadSettings());
    });

    // Baut aus dem aktuellen Formularzustand ein Settings-Objekt.
    function currentSettings(): AppSettings {
        return {
            fastMode,
            csvSeparator,
            showQueryDefault,
            previewHeight,
            language,
            theme
        };
    }

    // Übernimmt ein komplettes Settings-Objekt und setzt direkt das Farbschema.
    function applySettings(settings: AppSettings): void {
        fastMode = settings.fastMode;
        csvSeparator = settings.csvSeparator;
        showQueryDefault = settings.showQueryDefault;
        previewHeight = settings.previewHeight;
        language = settings.language;
        theme = settings.theme;
        applyTheme(theme);
    }

    // Speichert Änderungen sofort im Browser, damit sie nach einem Reload erhalten bleiben.
    function persistSettings(): void {
        saveSettings(currentSettings());
        applyTheme(theme);
    }

    // Setzt alle Einstellungen zurück auf die zentral definierten Default-Werte.
    function resetSettings(): void {
        applySettings(defaultSettings);
        persistSettings();
    }

    // Das Theme wird über ein data-Attribut am HTML-Element gesteuert.
    function applyTheme(nextTheme: Theme): void {
        document.documentElement.dataset.theme = nextTheme;
    }
</script>

<h1 class="datahub-title">Settings</h1>
<p class="subtitle">These preferences are stored locally in your browser.</p>

<div class="settings-layout">
    <aside class="settings-nav">
        <a href="#display">Display</a>
        <a href="#chat">Chat</a>
        <a href="#results">Results</a>
        <a href="#language">Language</a>
    </aside>

    <section class="settings-content">
        <section id="display" class="settings-section">
            <h2>Display</h2>
            <p class="section-description">Choose how the frontend is displayed.</p>

            <div class="setting-item">
                <div>
                    <h3>Theme</h3>
                    <p>Switch between the light and dark color scheme.</p>
                </div>

                <div class="settings-toggle">
                    <button
                        class:active={theme === 'light'}
                        onclick={() => {
                            theme = 'light';
                            persistSettings();
                        }}
                    >
                        Light
                    </button>
                    <button
                        class:active={theme === 'dark'}
                        onclick={() => {
                            theme = 'dark';
                            persistSettings();
                        }}
                    >
                        Dark
                    </button>
                    <div class="settings-slider" class:right={theme === 'dark'}></div>
                </div>
            </div>
        </section>

        <section id="chat" class="settings-section">
            <h2>Chat</h2>
            <p class="section-description">Set the default behavior for new chat requests.</p>

            <label class="setting-item">
                <div>
                    <h3>Fast mode</h3>
                    <p>Prefer faster responses when sending a chat request.</p>
                </div>
                <input type="checkbox" bind:checked={fastMode} onchange={persistSettings} />
            </label>

            <label class="setting-item">
                <div>
                    <h3>Show query by default</h3>
                    <p>Open the generated SPARQL query preview automatically.</p>
                </div>
                <input type="checkbox" bind:checked={showQueryDefault} onchange={persistSettings} />
            </label>
        </section>

        <section id="results" class="settings-section">
            <h2>Results</h2>
            <p class="section-description">Configure previews and CSV exports.</p>

            <label class="setting-item">
                <div>
                    <h3>Query preview height</h3>
                    <p>Set the default height of the query result preview.</p>
                </div>
                <select bind:value={previewHeight} onchange={persistSettings}>
                    <option value="small">Small</option>
                    <option value="medium">Medium</option>
                    <option value="large">Large</option>
                </select>
            </label>

            <label class="setting-item">
                <div>
                    <h3>CSV separator</h3>
                    <p>Choose the separator used when exporting result tables.</p>
                </div>
                <select bind:value={csvSeparator} onchange={persistSettings}>
                    <option value="comma">Comma</option>
                    <option value="semicolon">Semicolon</option>
                </select>
            </label>
        </section>

        <section id="language" class="settings-section">
            <h2>Language</h2>
            <p class="section-description">Choose the preferred interface language.</p>

            <label class="setting-item">
                <div>
                    <h3>Preferred language</h3>
                    <p>This preference is ready for translated interface text.</p>
                </div>
                <select bind:value={language} onchange={persistSettings}>
                    <option value="en">English</option>
                    <option value="de">Deutsch</option>
                </select>
            </label>
        </section>

        <div class="settings-actions">
            <button class="segmented-action" onclick={resetSettings}>Reset local settings</button>
        </div>
    </section>
</div>

<style>
    .settings-layout {
        display: grid;
        grid-template-columns: 220px minmax(0, 1fr);
        gap: 36px;
        margin-top: 28px;
        max-width: 1100px;
    }

    .settings-content {
        display: flex;
        flex-direction: column;
        gap: 34px;
    }

    .settings-nav {
        display: flex;
        flex-direction: column;
        gap: 6px;
        border-right: 1px solid var(--border-color);
        padding-right: 20px;
    }

    .settings-nav a {
        text-decoration: none;
        color: var(--muted-color);
        padding: 10px 12px;
        border-radius: 8px;
        font-weight: 650;
    }

    .settings-nav a:hover {
        background: var(--surface-hover);
        color: var(--text-color);
    }

    .settings-section {
        border-bottom: 1px solid var(--border-color);
        padding-bottom: 28px;
    }

    .settings-section h2 {
        margin: 0 0 8px;
        font-size: 1.5rem;
        font-weight: 800;
    }

    .section-description {
        margin: 0 0 22px;
        color: var(--muted-color);
    }

    .setting-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 32px;
        padding: 18px 0;
    }

    .setting-item h3 {
        margin: 0 0 6px;
        font-size: 1rem;
        font-weight: 750;
    }

    .setting-item p {
        margin: 0;
        color: var(--muted-color);
        max-width: 520px;
    }

    .setting-item select {
        height: 42px;
        min-width: 160px;
        border-radius: 10px;
        border: 1px solid var(--border-color);
        padding: 0 12px;
        background: var(--surface-color);
        color: var(--text-color);
        font-weight: 650;
    }

    .setting-item input[type='checkbox'] {
        width: 20px;
        height: 20px;
        accent-color: #07142c;
    }

    .settings-toggle {
        position: relative;
        display: flex;
        background: #07142c;
        border-radius: 14px;
        padding: 4px;
        width: 220px;
        height: 44px;
        flex-shrink: 0;
    }

    .settings-toggle button {
        position: relative;
        z-index: 2;
        flex: 1;
        border: none;
        background: transparent;
        color: white;
        font-weight: 750;
        cursor: pointer;
        border-radius: 10px;
    }

    .settings-toggle button.active {
        color: #07142c;
    }

    .settings-slider {
        position: absolute;
        z-index: 1;
        top: 4px;
        left: 4px;
        width: calc(50% - 4px);
        height: calc(100% - 8px);
        background: white;
        border-radius: 10px;
        transition: transform 0.2s ease;
    }

    .settings-slider.right {
        transform: translateX(100%);
    }

    .settings-actions {
        display: flex;
        justify-content: flex-end;
    }

    .settings-actions button {
        height: 2.45rem;
        padding: 0 1.2rem;
        border-radius: 0.65rem;
        font-weight: 750;
        font-size: 0.95rem;
        cursor: pointer;
    }

    .segmented-action {
        background: var(--surface-color);
        color: var(--text-color);
        border: 2px solid var(--text-color);
    }

    .segmented-action:hover {
        background: var(--surface-hover);
    }

    @media (max-width: 800px) {
        .settings-layout {
            grid-template-columns: 1fr;
        }

        .settings-nav {
            flex-direction: row;
            flex-wrap: wrap;
            border-right: 0;
            border-bottom: 1px solid var(--border-color);
            padding: 0 0 16px;
        }

        .setting-item {
            align-items: flex-start;
            flex-direction: column;
        }
    }
</style>
