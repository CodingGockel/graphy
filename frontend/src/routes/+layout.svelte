<script lang="ts">
    import { onMount } from 'svelte';
    import './layout.css';
    import favicon from '$lib/assets/favicon.svg';
    import phenobsLogo from '$lib/assets/phenobs-logo.png';
    import { loadSettings } from '$lib/settings';

    // SvelteKit übergibt hier die aktuell geöffnete Unterseite.
    let { children } = $props();

    onMount(() => {
        // Das Theme wird nach dem Laden aus den lokalen Einstellungen übernommen.
        document.documentElement.dataset.theme = loadSettings().theme;
    });

    // Exportiert nur die Session-ID. Die eigentlichen Nachrichten bleiben im Backend.
    async function exportChat() {
        const sessionId = localStorage.getItem('sessionId');

        if (!sessionId) {
            window.alert('There is no chat session to export yet.');
            return;
        }

        try {
            await navigator.clipboard.writeText(sessionId);
            window.alert('The session ID was copied to your clipboard.');
        } catch {
            window.prompt('Copy this session ID:', sessionId);
        }
    }

    // Mit einer vorhandenen Session-ID kann ein gespeicherter Chat wieder geladen werden.
    function importChat() {
        const sessionId = window.prompt('Enter the session ID to import:')?.trim();

        if (!sessionId) return;

        localStorage.setItem('sessionId', sessionId);
        window.location.href = '/';
    }
</script>

<svelte:head>
    <link rel="icon" href={favicon} />
</svelte:head>

<div class="app">
    <!-- Seitennavigation der Anwendung -->
    <aside class="sidebar">
        <a href="/" class="logo">
            <img src={phenobsLogo} alt="PhenObs Logo" />
        </a>

        <nav>
            <a href="/">AI Chat</a>
            <a href="/result-table">Result Table</a>
            <a href="/map">Map</a>
            <a href="/settings">Settings</a>
            <a href="/help">Help</a>
        </nav>

        <div class="session-actions">
            <button onclick={importChat}>Import Chat</button>
            <button onclick={exportChat}>Export Chat</button>
        </div>
    </aside>

    <!-- Hauptbereich für die aktuelle Route -->
    <main class="content">
        {@render children()}
    </main>
</div>
