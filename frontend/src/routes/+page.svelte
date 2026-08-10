<script lang="ts">
    import { marked } from 'marked';
    import { goto } from '$app/navigation';
    import { onMount, onDestroy, tick } from 'svelte';
    import { loadSettings } from '$lib/settings';
    import { filterFullTableRows } from '$lib/fullTableFilter';
    import { API_BASE_URL } from '$lib/api';

    // Vereinfachte Form der Nachrichten, die direkt im Chat gerendert wird.
    type ChatMessage = {
        role: 'user' | 'assistant';
        content: string;
    };

    // Form der ausführlicheren Nachrichten, die vom Backend-History-Endpunkt kommt.
    type HistoryMessage = {
        role: 'user' | 'assistant';
        content: string;
        sparql_query: string | null;
        sparql_results: string | null;
        is_followup: boolean;
        created_at: string | null;
    };

    type HistoryResponse = {
        session_id: string;
        messages: HistoryMessage[];
    };

    // Gemeinsame Keys für Daten, die im Browser zwischengespeichert werden.
    // (API_BASE_URL stammt aus $lib/api.)
    const FULL_TABLE_CACHE_KEY = 'fullTableRaw';
    const FULL_TABLE_FILTER_QUERY_KEY = 'fullTableFilterQuery';

    // Reaktiver Zustand für Chat, Ergebnisse und die gefilterte Full Table.
    let messages = $state<ChatMessage[]>([]);
    let sessionId = $state<string | null>(null);
    let question = $state('');
    let generatedQuery = $state('');
    let loading = $state(false);
    let error = $state('');
    let answer = $state('');
    let results = $state<any[]>([]);
    let fullResults = $state<any[]>([]);
    let showGeneratedQuery = $state(false);
    let chatId = $state(0);
    let columns = $state<string[]>([]);
    let csvSeparator = $state<'comma' | 'semicolon'>('comma');
    let previewHeight = $state<'small' | 'medium' | 'large'>('medium');
    let chatOutputElement: HTMLElement;
    let mapPreviewElement: HTMLDivElement;
    let mapPreview: any;
    let mapPreviewMarkers: any;

    const mapPreviewColors = ['#07142c', '#2563eb', '#059669', '#dc2626', '#7c3aed', '#f59e0b'];
    const mapPreviewGardens = [
        { garden: 'Botanischer Garten Jena', city: 'Jena', lat: 50.9271, lng: 11.5892 },
        { garden: 'Botanic Garden and Botanical Museum Berlin', city: 'Berlin', lat: 52.4573, lng: 13.3053 },
        { garden: 'Alpinum Schatzalp', city: 'Davos', lat: 46.7985, lng: 9.8203 },
        { garden: 'Loki-Schmidt-Garten', city: 'Hamburg', lat: 53.5612, lng: 9.8603 },
        {
            garden: 'Botanischer Garten der Martin-Luther-Universität Halle-Wittenberg',
            city: 'Halle',
            lat: 51.4860,
            lng: 11.9618
        }
    ];

    function normalizeMapValue(value: any) {
        return String(value ?? '')
            .replace(/Ã¤/g, 'ä')
            .replace(/Ã¶/g, 'ö')
            .replace(/Ã¼/g, 'ü')
            .trim()
            .toLowerCase();
    }

    async function renderMapPreview() {
        if (!mapPreviewElement) return;

        const L = await import('leaflet');
        await import('leaflet/dist/leaflet.css');

        if (!mapPreview) {
            mapPreview = L.map(mapPreviewElement, {
                zoomControl: false,
                attributionControl: false,
                dragging: false,
                scrollWheelZoom: false,
                doubleClickZoom: false,
                boxZoom: false,
                keyboard: false
            });

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(mapPreview);
        }

        if (mapPreviewMarkers) {
            mapPreviewMarkers.remove();
        }

        mapPreviewMarkers = L.featureGroup();
        const observations = new Map<string, Map<string, number>>();

        for (const row of fullResults) {
            const garden = mapPreviewGardens.find((item) =>
                normalizeMapValue(item.garden) === normalizeMapValue(row.garden) ||
                normalizeMapValue(item.city) === normalizeMapValue(row.city)
            );

            if (!garden) continue;

            const year = String(row.year ?? '').trim() || 'Unknown';
            const counts = observations.get(garden.garden) ?? new Map<string, number>();
            counts.set(year, (counts.get(year) ?? 0) + 1);
            observations.set(garden.garden, counts);
        }

        const years = Array.from(
            new Set(Array.from(observations.values()).flatMap((counts) => Array.from(counts.keys())))
        ).sort();
        const displayedGardens = observations.size > 0
            ? mapPreviewGardens.filter((garden) => observations.has(garden.garden))
            : mapPreviewGardens;

        for (const garden of displayedGardens) {
            const counts = observations.get(garden.garden);
            let marker;

            if (counts) {
                const total = Array.from(counts.values()).reduce((sum, count) => sum + count, 0);
                const segments = Array.from(counts.entries())
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([year, count]) => {
                        const color = mapPreviewColors[years.indexOf(year) % mapPreviewColors.length];
                        return `<span style="height:${Math.max(count * 9, 7)}px;background:${color}"></span>`;
                    })
                    .join('');
                const icon = L.divIcon({
                    className: 'mini-map-marker-wrapper',
                    html: `<div class="mini-map-marker"><strong>${total}</strong><div>${segments}</div></div>`,
                    iconSize: [26, 70],
                    iconAnchor: [13, 65]
                });

                marker = L.marker([garden.lat, garden.lng], { icon });
            } else {
                marker = L.circleMarker([garden.lat, garden.lng], {
                    radius: 6,
                    color: '#ffffff',
                    weight: 2,
                    fillColor: '#2563eb',
                    fillOpacity: 1
                });
            }

            marker.addTo(mapPreviewMarkers);
        }

        mapPreviewMarkers.addTo(mapPreview);
        mapPreview.fitBounds(mapPreviewMarkers.getBounds(), { padding: [22, 22] });

        setTimeout(() => mapPreview?.invalidateSize(), 0);
    }

    // Bereinigt die Antwort des Backends für die Chat-Ausgabe
    function cleanAnswer(text: string) {
        return text
            .replace(/<think>[\s\S]*?<\/think>/g, '')
            .trim();
    }

    // Formatiert die generierte SPARQL Query lesbarer
    function formatQuery(query: string) {
        return query
            .replace(/\\n/g, '\n')
            .replace(/\s*(PREFIX)/g, '\n$1')
            .replace(/\s*(SELECT)/g, '\n\n$1')
            .replace(/\s*(WHERE)/g, '\n$1')
            .replace(/\s*(ORDER BY)/g, '\n$1')
            .replace(/\s*\{\s*/g, ' {\n  ')
            .replace(/\s+\.\s*/g, ' .\n  ')
            .replace(/\s*\}\s*/g, '\n}')
            .trim();
    }

    // Setzt den Chat und die gespeicherten Ergebnisse zurück
    function resetChat() {
        chatId++;

        messages = [];
        sessionId = null;
        question = '';
        generatedQuery = '';
        loading = false;
        error = '';
        answer = '';
        results = [];
        showGeneratedQuery = loadSettings().showQueryDefault;

        localStorage.removeItem('chatMessages');
        localStorage.removeItem('sessionId');
        localStorage.removeItem('generatedQuery');
        localStorage.removeItem('previewColumns');
        localStorage.removeItem('previewResults');
        localStorage.removeItem(FULL_TABLE_FILTER_QUERY_KEY);
        const cachedFullTable = parseFullTable(localStorage.getItem(FULL_TABLE_CACHE_KEY));
        fullResults = filterFullTableRows(cachedFullTable, '');
        localStorage.setItem('fullResults', JSON.stringify(fullResults));
        localStorage.setItem('fullTable', JSON.stringify({ rows: fullResults }));

        void renderMapPreview();
    }

    // Formatiert Spaltennamen für die Tabellenanzeige
    function formatColumnName(col: string) {
        return col
            .replace(/([A-Z])/g, ' $1')
            .replace(/^./, (char) => char.toUpperCase());
    }

    function loadCachedChat() {
        messages = JSON.parse(localStorage.getItem('chatMessages') ?? '[]');
        generatedQuery = localStorage.getItem('generatedQuery') ?? '';
        columns = JSON.parse(localStorage.getItem('previewColumns') ?? '[]');
        results = JSON.parse(localStorage.getItem('previewResults') ?? '[]');
    }

    function storeSessionId(newSessionId: string | null | undefined) {
        sessionId = newSessionId ?? null;

        if (sessionId) {
            localStorage.setItem('sessionId', sessionId);
        } else {
            localStorage.removeItem('sessionId');
        }
    }

    function parseQueryResults(rawResults: string | object | null | undefined) {
        if (!rawResults) return { columns: [], rows: [] };

        const parsed = typeof rawResults === 'string'
            ? JSON.parse(rawResults)
            : rawResults;
        const parsedColumns = parsed.head?.vars ?? [];
        const bindings = parsed.results?.bindings ?? [];
        const rows = bindings.map((binding: any) => {
            const row: Record<string, any> = {};

            for (const key of parsedColumns) {
                row[key] = binding[key]?.value ?? '';
            }

            return row;
        });
        const visibleColumns = parsedColumns.filter((column: string) =>
            rows.some((row: Record<string, any>) => {
                const value = row[column];
                return value !== null &&
                    value !== undefined &&
                    String(value).trim() !== '';
            })
        );

        return { columns: visibleColumns, rows };
    }

    function storeQueryResults(query: string | null | undefined, rawResults: string | object | null | undefined) {
        generatedQuery = formatQuery(query ?? '');
        localStorage.setItem('generatedQuery', generatedQuery);

        const parsed = parseQueryResults(rawResults);
        columns = parsed.columns;
        results = parsed.rows;
        localStorage.setItem('previewColumns', JSON.stringify(columns));
        localStorage.setItem('previewResults', JSON.stringify(results));
    }

    function clearQueryResults() {
        generatedQuery = '';
        columns = [];
        results = [];
        localStorage.removeItem('generatedQuery');
        localStorage.removeItem('previewColumns');
        localStorage.removeItem('previewResults');
    }

    function updateFullTable(rows: any[], userQuestion: string) {
        fullResults = filterFullTableRows(rows, userQuestion);
        localStorage.setItem('fullResults', JSON.stringify(fullResults));
        localStorage.setItem('fullTable', JSON.stringify({ rows: fullResults }));
    }

    async function restoreSessionHistory(storedSessionId: string) {
        const response = await fetch(`${API_BASE_URL}/session/${encodeURIComponent(storedSessionId)}/history`);

        if (response.status === 404) {
            storeSessionId(null);
            messages = [];
            clearQueryResults();
            localStorage.removeItem('chatMessages');
            return;
        }

        if (!response.ok) {
            throw new Error(`Could not load session history: ${response.status}`);
        }

        const history = await response.json() as HistoryResponse;
        storeSessionId(history.session_id);
        messages = history.messages.map((message) => ({
            role: message.role,
            content: message.role === 'assistant'
                ? marked.parse(cleanAnswer(message.content)) as string
                : message.content
        }));
        localStorage.setItem('chatMessages', JSON.stringify(messages));

        const latestResultMessage = [...history.messages]
            .reverse()
            .find((message) => message.sparql_results);

        if (latestResultMessage) {
            storeQueryResults(latestResultMessage.sparql_query, latestResultMessage.sparql_results);
        } else {
            clearQueryResults();
        }
    }

    // Lädt Einstellungen und gespeicherte Chatdaten beim Start
    onMount(async () => {
        const settings = loadSettings();

        csvSeparator = settings.csvSeparator;
        previewHeight = settings.previewHeight;
        showGeneratedQuery = settings.showQueryDefault;

        const storedSessionId = localStorage.getItem('sessionId');
        storeSessionId(storedSessionId);

        if (storedSessionId) {
            try {
                await restoreSessionHistory(storedSessionId);
            } catch (historyError) {
                console.error(historyError);
                loadCachedChat();
                error = 'The saved chat history could not be loaded from the backend.';
            }
        } else {
            loadCachedChat();
        }

        const fullTableRows = await loadFullTable(chatId);
        const filterQuery = localStorage.getItem(FULL_TABLE_FILTER_QUERY_KEY) ?? '';
        updateFullTable(fullTableRows, filterQuery);

        await scrollChatToBottom();
        await renderMapPreview();
    });

    onDestroy(() => {
        mapPreview?.remove();
    });

    // Lädt die aktuellen Query-Ergebnisse als CSV-Datei herunter
    function downloadCSV() {
        if (results.length === 0 || columns.length === 0) return;

        const separator = csvSeparator === 'semicolon' ? ';' : ',';

        const escapeCSV = (value: any) => {
            const text = String(value ?? '');
            return `"${text.replace(/"/g, '""')}"`;
        };

        const header = columns.map(escapeCSV).join(separator);

        const rows = results.map((row) =>
            columns.map((col) => escapeCSV(row[col])).join(separator)
        );

        const csv = [`sep=${separator}`, header, ...rows].join('\n');

        const blob = new Blob([csv], {
            type: 'text/csv;charset=utf-8;'
        });

        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = 'query-results.csv';
        a.click();

        URL.revokeObjectURL(url);
    }

    const resultCount = $derived(results.length);
    const fullResultCount = $derived(fullResults.length);

    // Zählt eindeutige Werte aus der Full Table
    function countFullUnique(key: string) {
        return new Set(
            fullResults
                .map((row) => row[key])
                .filter(Boolean)
        ).size;
    }

    const gardenCount = $derived(
        countFullUnique('garden')
    );

    const speciesCount = $derived(
        countFullUnique('species')
    );

    const yearCount = $derived(
        countFullUnique('year')
    );

    function numericValues(key: string) {
        return fullResults
            .map((row) => String(row[key] ?? '').trim())
            .filter((value) => value !== '')
            .map((value) => Number(value))
            .filter((value) => Number.isFinite(value));
    }

    function median(values: number[]) {
        if (values.length === 0) return null;

        const sorted = [...values].sort((a, b) => a - b);
        const middle = Math.floor(sorted.length / 2);

        return sorted.length % 2 === 0
            ? (sorted[middle - 1] + sorted[middle]) / 2
            : sorted[middle];
    }

    const yearRange = $derived.by(() => {
        const years = numericValues('year');
        if (years.length === 0) return '—';

        const first = Math.min(...years);
        const last = Math.max(...years);
        return first === last ? String(first) : `${first}–${last}`;
    });

    const earliestFlowerDay = $derived.by(() => {
        const days = numericValues('firstFlowerDay');
        return days.length > 0 ? Math.min(...days) : null;
    });

    const medianFloweringDuration = $derived(
        median(numericValues('floweringDuration'))
    );

    function groupCounts(key: string) {
        const counts = new Map<string, number>();

        for (const row of fullResults) {
            const value = String(row[key] ?? '').trim();
            if (!value) continue;
            counts.set(value, (counts.get(value) ?? 0) + 1);
        }

        return Array.from(counts.entries())
            .map(([label, count]) => ({ label, count }))
            .sort((a, b) => key === 'year'
                ? Number(a.label) - Number(b.label)
                : b.count - a.count);
    }

    const observationsByYear = $derived(groupCounts('year'));
    const observationsByGarden = $derived(groupCounts('garden').slice(0, 6));
    const previewChartData = $derived(
        observationsByYear.length > 1 ? observationsByYear : observationsByGarden
    );
    const previewChartTitle = $derived(
        observationsByYear.length > 1 ? 'Observation records by year' : 'Observation records by garden'
    );
    const previewChartDescription = $derived(
        observationsByYear.length > 1
            ? 'Shows temporal coverage and makes gaps between years immediately visible.'
            : 'Shows how the available records are distributed across botanical gardens.'
    );
    const previewChartMax = $derived(
        Math.max(...previewChartData.map((item) => item.count), 1)
    );

    // Erstellt einen kurzen Text für die Full-Table-Zusammenfassung
    const summaryText = $derived.by(() => {
        if (fullResultCount === 0) {
            return 'Tell the AI what you are looking for.';
        }

        return `${speciesCount} plant species across ${gardenCount} botanical gardens and ${yearCount} years.`;
    });

    function parseFullTable(raw: string | null | undefined) {
        if (!raw) return [];

        try {
            const parsed = JSON.parse(raw);
            const table = parsed.full_table ?? parsed;

            if (Array.isArray(table.rows)) {
                return table.rows;
            }

            const fullColumns = parsed.head?.vars ?? [];
            const bindings = parsed.results?.bindings ?? [];

            return bindings.map((binding: any) => {
                const row: Record<string, any> = {};

                for (const col of fullColumns) {
                    row[col] = binding[col]?.value ?? '';
                }

                return row;
            });
        } catch (error) {
            console.error('Could not parse full table:', error);
            return [];
        }
    }

    async function loadFullTable(currentChatId: number) {
        const cachedRows = parseFullTable(localStorage.getItem(FULL_TABLE_CACHE_KEY));

        if (cachedRows.length > 0) {
            return cachedRows;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/chat/full_table`);

            if (!response.ok) {
                throw new Error(`Full-table endpoint error: ${response.status}`);
            }

            const data = await response.json();

            if (currentChatId !== chatId) return [];

            if (!Array.isArray(data.full_table?.rows)) {
                throw new Error('Full-table endpoint returned an invalid response');
            }

            localStorage.setItem(FULL_TABLE_CACHE_KEY, JSON.stringify(data.full_table));

            return data.full_table.rows;
        } catch (fullTableError) {
            console.error('Could not load full table:', fullTableError);

            if (currentChatId === chatId) {
                localStorage.removeItem(FULL_TABLE_CACHE_KEY);
            }

            return [];
        }
    }

    // Sendet die Nutzerfrage an das Backend und verarbeitet die Antwort
    async function search() {
        if (!question.trim()) return;

        const userMessage = question.trim();
        const currentChatId = chatId;
        const requestedSessionId = sessionId;

        messages.push({
            role: 'user',
            content: userMessage
        });

        localStorage.setItem('chatMessages', JSON.stringify(messages));

        await scrollChatToBottom();

        question = '';
        loading = true;
        error = '';
        answer = '';

        // Filter the full table immediately. The LLM response continues in
        // parallel and must not delay the table, map, or data insights.
        const fullTableRowsPromise = loadFullTable(currentChatId);
        void fullTableRowsPromise.then(async (fullTableRows) => {
            if (currentChatId !== chatId) return;

            localStorage.setItem(FULL_TABLE_FILTER_QUERY_KEY, userMessage);
            updateFullTable(fullTableRows, userMessage);
            await renderMapPreview();
        });

        try {
            const response = await fetch(`${API_BASE_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: userMessage,
                    session_id: requestedSessionId
                })
            });

            if (!response.ok) {
                throw new Error(`Backend error: ${response.status}`);
            }

            const data = await response.json();

            if (currentChatId !== chatId) return;

            if (requestedSessionId && data.session_id !== requestedSessionId) {
                messages = [{
                    role: 'user',
                    content: userMessage
                }];
                localStorage.setItem('chatMessages', JSON.stringify(messages));
                clearQueryResults();
            }

            storeSessionId(data.session_id);

            const cleanedAnswer = cleanAnswer(data.answer ?? '');
            const htmlAnswer = marked.parse(cleanedAnswer) as string;

            answer = htmlAnswer;

            messages.push({
                role: 'assistant',
                content: htmlAnswer
            });

            localStorage.setItem('chatMessages', JSON.stringify(messages));

            await scrollChatToBottom();

            if (data.sparql_query_result) {
                storeQueryResults(data.llm_generated_query, data.sparql_query_result);

            } else {
                clearQueryResults();
            }
        } catch (err) {
            console.error(err);
            if (currentChatId === chatId) {
                error = 'The backend could not be reached or returned an error.';
            }
        } finally {
            if (currentChatId === chatId) {
                loading = false;
            }
        }
    }

    // Scrollt den Chatbereich automatisch nach unten
    async function scrollChatToBottom() {
        await tick();

        if (chatOutputElement) {
            chatOutputElement.scrollTop = chatOutputElement.scrollHeight;
        }
    }
</script>

<div class="main-layout">
    <section class="chat-area">
        <header class="chat-header">
            <h1 class="datahub-title">DataExplorer</h1>

            <!-- Button zum Zurücksetzen des Chats -->
            <button class="reset-chat-button" onclick={resetChat}>
                New Chat
            </button>
        </header>

        <!-- Ausgabe des AI Chats -->
        <section class="ai-chat-output" bind:this={chatOutputElement}>
            {#if messages.length === 0}
                <div class="empty-chat-state">
                    <button class="how-to-use-button" onclick={() => goto('/help')}>
                        How to use?
                    </button>
                </div>
            {/if}

            {#each messages as message}
                <div
                    class="chat-message"
                    class:message-user={message.role === 'user'}
                    class:message-ai={message.role === 'assistant'}
                >
                    {#if message.role === 'assistant'}
                        {@html message.content}
                    {:else}
                        {message.content}
                    {/if}
                </div>
            {/each}

            {#if loading}
                <div class="chat-message message-ai">Thinking...</div>
            {/if}

            {#if error}
                <div class="chat-message message-error">{error}</div>
            {/if}
        </section>

        <!-- Eingabe für den AI Chat -->
        <section class="search-box">
            <input
                bind:value={question}
                placeholder="Ask me anything..."
                onkeydown={(event) => {
                    if (event.key === 'Enter' && !loading) {
                        search();
                    }
                }}
            />

            <button onclick={search}>
                {loading ? 'Searching...' : 'Send'}
            </button>
        </section>
    </section>

    <section class="data-area">
        <div class="data-columns">
            <section class="data-column table-column">
                <!-- Aktionen für Tabelle und Export -->
                <div class="action-row">
                    <button class="action-button" onclick={() => goto('/result-table')}>
                        Show Table
                    </button>

                    <button class="action-button" onclick={() => goto('/map')}>
                        Show Map
                    </button>

                    <button class="action-button" onclick={downloadCSV}>
                        Download CSV
                    </button>
                </div>

                {#if columns.length > 0}
                    <!-- Vorschau der Query-Ergebnisse -->
                    <section class="results">
                        <h3>Search Results</h3>

                        <div
                            class="preview-wrapper"
                            class:preview-small={previewHeight === 'small'}
                            class:preview-medium={previewHeight === 'medium'}
                            class:preview-large={previewHeight === 'large'}
                        >
                            <table>
                                <thead>
                                    <tr>
                                        {#each columns as col}
                                            <th>{formatColumnName(col)}</th>
                                        {/each}
                                    </tr>
                                </thead>

                                <tbody>
                                    {#if results.length > 0}
                                        {#each results as row}
                                            <tr>
                                                {#each columns as col}
                                                    <td>{row[col]}</td>
                                                {/each}
                                            </tr>
                                        {/each}
                                    {:else}
                                        <!-- Dummy-Zeilen bis echte Ergebnisdaten vorhanden sind -->
                                        {#each Array(6) as _}
                                            <tr class="placeholder-row">
                                                {#each columns as _}
                                                    <td>—</td>
                                                {/each}
                                            </tr>
                                        {/each}
                                    {/if}
                                </tbody>
                            </table>
                        </div>
                    </section>
                {:else}
                    <!-- Platzhalter, solange noch keine Ergebnisse vorhanden sind -->
                    <section class="info-placeholder">
                        <h3>No results found yet.</h3>
                        <p>Tell the AI what you are looking for.</p>
                    </section>
                {/if}

                <section class="map-preview-card">
                    <div class="map-preview-header">
                        <div>
                            <h3>Map Preview</h3>
                            <p>
                                {fullResultCount > 0
                                    ? 'Observation counts by botanical garden.'
                                    : 'Available botanical gardens.'}
                            </p>
                        </div>

                        <button onclick={() => goto('/map')}>Open Map</button>
                    </div>

                    <div class="map-preview" bind:this={mapPreviewElement}></div>
                </section>
            </section>

            <section class="data-column insight-column">
                <h2 class="insights-title">Data Insights</h2>

                <!-- Zusammenfassung der aktuellen Ergebnisdaten -->
                <section class="info-placeholder insights-card">
                    {#if fullResultCount > 0}
                        <h3>{fullResultCount} phenology records</h3>
                        <p>{summaryText}</p>

                        <div class="insight-placeholder-grid">
                            <div>
                                <span>Plant species</span>
                                <strong>{speciesCount || '—'}</strong>
                            </div>

                            <div>
                                <span>Botanical gardens</span>
                                <strong>{gardenCount || '—'}</strong>
                            </div>

                            <div>
                                <span>Observation period</span>
                                <strong>{yearRange}</strong>
                            </div>

                            <div>
                                <span>Earliest first flower</span>
                                <strong>{earliestFlowerDay === null ? '—' : `Day ${earliestFlowerDay}`}</strong>
                            </div>

                            <div>
                                <span>Median flowering duration</span>
                                <strong>{medianFloweringDuration === null ? '—' : `${medianFloweringDuration} days`}</strong>
                            </div>
                        </div>
                    {:else}
                        <h3>{resultCount > 0 ? 'Full-table data unavailable' : 'No results found yet.'}</h3>
                        <p>
                            {resultCount > 0
                                ? 'Run the query again to load the phenology records required for reliable insights.'
                                : 'Insights will appear here after a query.'}
                        </p>

                        <div class="insight-placeholder-grid">
                            <div>
                                <span>Plant species</span>
                                <strong>—</strong>
                            </div>

                            <div>
                                <span>Botanical gardens</span>
                                <strong>—</strong>
                            </div>

                            <div>
                                <span>Years</span>
                                <strong>—</strong>
                            </div>

                            <div>
                                <span>Observation type</span>
                                <strong>—</strong>
                            </div>
                        </div>
                    {/if}
                </section>

                <section class="chart-card">
                    <h3>{fullResultCount > 0 ? previewChartTitle : 'Visualization Preview'}</h3>
                    <p>
                        {fullResultCount > 0
                            ? previewChartDescription
                            : resultCount > 0
                                ? 'Run the query again to load the full-table data for this chart.'
                                : 'A chart will appear here after a query.'}
                    </p>

                    {#if previewChartData.length > 0}
                        <div class="preview-bar-chart">
                            {#each previewChartData as item}
                                <div class="preview-bar-column">
                                    <strong>{item.count}</strong>
                                    <div class="preview-bar-track">
                                        <div
                                            class="preview-bar"
                                            style={`height: ${Math.max((item.count / previewChartMax) * 100, 5)}%`}
                                            title={`${item.label}: ${item.count} observation records`}
                                        ></div>
                                    </div>
                                    <span title={item.label}>{item.label}</span>
                                </div>
                            {/each}
                        </div>
                    {:else}
                        <div class="chart-empty-state">
                            {resultCount > 0
                                ? 'Full-table data is missing for this saved query.'
                                : 'No full-table data available yet.'}
                        </div>
                    {/if}
                </section>
            </section>
        </div>

        <!-- Anzeige der generierten SPARQL Query -->
        <section class="query-dropdown">
            <button
                class="query-toggle"
                onclick={() => showGeneratedQuery = !showGeneratedQuery}
            >
                Generated Query {showGeneratedQuery ? '▼' : '▲'}
            </button>

            {#if showGeneratedQuery}
                <div class="query-box">
                    <pre><code>{generatedQuery || 'No query generated yet.'}</code></pre>
                </div>
            {/if}
        </section>
    </section>
</div>

<style>
    /****************************************
    MAIN PAGE LAYOUT
    ****************************************/

    .main-layout {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 32px;
        margin-top: 10px;
        height: calc(100vh - 80px);
    }

    .chat-area {
        display: flex;
        flex-direction: column;
        min-height: 100%;
    }

    .chat-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 32px;
    }

    .data-area {
        display: flex;
        flex-direction: column;
        overflow: hidden;
        min-height: 0;
    }

    .data-columns {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(280px, 1fr);
        gap: 20px;
        flex: 1;
        min-height: 0;
    }

    .data-column {
        display: flex;
        flex-direction: column;
        min-height: 0;
    }

    .table-column,
    .insight-column {
        min-width: 0;
    }

    /****************************************
    CHAT AREA
    ****************************************/

    .ai-chat-output {
        flex: 1;
        border-radius: 16px;
        padding: 22px;
        line-height: 1.6;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .empty-chat-state {
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .chat-message {
        max-width: 75%;
        padding: 12px 16px;
        border-radius: 16px;
        font-size: 0.95rem;
    }

    .message-user {
        align-self: flex-end;
        background: #07142c;
        color: white;
        border-bottom-right-radius: 4px;
    }

    .message-ai {
        align-self: flex-start;
        background: #babcc4;
        color: #07142c;
        border-bottom-left-radius: 4px;
    }

    .message-error {
        align-self: flex-start;
        background: #ffe6e6;
        color: #b00020;
    }

    /****************************************
    CHAT BUTTONS
    ****************************************/

    .reset-chat-button {
        height: 60px;
        padding: 0 16px;
        border: none;
        border-radius: 10px;
        background: #e44e4e;
        color: white;
        font-weight: 750;
        font-size: 0.95rem;
        cursor: pointer;
    }

    .reset-chat-button:hover {
        background: #0f2550;
    }

    .how-to-use-button {
        min-width: 190px;
        height: 58px;
        padding: 0 28px;
        border: none;
        border-radius: 12px;
        background: #07142c;
        color: white;
        font-size: 1rem;
        font-weight: 800;
        letter-spacing: 0.01em;
        cursor: pointer;
        box-shadow: 0 10px 24px rgba(7, 20, 44, 0.22);
        transition:
            background 0.15s ease,
            transform 0.15s ease,
            box-shadow 0.15s ease;
    }

    .how-to-use-button:hover {
        background: #0f2550;
        transform: translateY(-1px);
        box-shadow: 0 12px 28px rgba(7, 20, 44, 0.28);
    }

    .how-to-use-button:active {
        transform: translateY(0);
        box-shadow: 0 8px 18px rgba(7, 20, 44, 0.22);
    }

    /****************************************
    SEARCH BOX
    ****************************************/

    .search-box {
        display: flex;
        gap: 16px;
        align-items: center;
        background: transparent;
        padding: 0;
        border-radius: 0;
        margin-top: auto;
        margin-bottom: 0;
    }

    .search-box input {
        flex: 1;
        height: 48px;
        border: 1px solid #cbd5e1;
        border-radius: 12px;
        padding: 0 16px;
        font-size: 1rem;
    }

    .search-box input:focus {
        outline: none;
        border-color: #2563eb;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
    }

    .search-box button {
        height: 48px;
        padding: 0 22px;
        border: none;
        border-radius: 12px;
        background: #07142c;
        color: white;
        font-size: 0.95rem;
        font-weight: 750;
        cursor: pointer;
    }

    .search-box button:hover {
        background: #0f2550;
    }

    /****************************************
    ACTION BUTTONS
    ****************************************/

    .action-row {
        display: flex;
        gap: 12px;
        margin-bottom: 16px;
    }

    .action-button {
        height: 40px;
        padding: 0 16px;
        border: none;
        border-radius: 10px;
        background: #07142c;
        color: white;
        font-size: 0.9rem;
        font-weight: 750;
        cursor: pointer;
    }

    .action-button:hover {
        background: #0f2550;
    }

    /****************************************
    PREVIEW TABLE
    ****************************************/

    .results {
        background: white;
        padding: 20px;
        border-radius: 16px;
        min-height: 300px;
        margin-bottom: 24px;
        overflow: hidden;
    }

    .results h3 {
        margin: 0 0 12px 0;
        font-size: 1rem;
        font-weight: 750;
    }

    table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.85rem;
    }

    th,
    td {
        padding: 10px 8px;
        border-bottom: 1px solid #ddd;
        text-align: left;
    }

    th {
        font-weight: 750;
    }

    .placeholder-row td {
        color: #cbd5e1;
    }

    .preview-wrapper {
        position: relative;
        overflow-y: auto;
    }

    .preview-wrapper.preview-small {
        max-height: 280px;
    }

    .preview-wrapper.preview-medium {
        max-height: 520px;
    }

    .preview-wrapper.preview-large {
        max-height: 720px;
    }

    .preview-wrapper::-webkit-scrollbar {
        width: 6px;
    }

    .preview-wrapper::-webkit-scrollbar-thumb {
        background: #cbd5e1;
        border-radius: 6px;
    }

    .table-column .results {
        flex: 1;
        min-height: 0;
        margin-bottom: 0;
        display: flex;
        flex-direction: column;
    }

    .table-column .preview-wrapper {
        flex: 1;
        min-height: 0;
        max-height: none;
        overflow-y: auto;
    }

    /****************************************
    MAP PREVIEW
    ****************************************/

    .map-preview-card {
        height: 270px;
        flex-shrink: 0;
        margin-top: 16px;
        padding: 16px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        border-radius: 16px;
        background: white;
    }

    .map-preview-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 12px;
        margin-bottom: 12px;
    }

    .map-preview-header h3 {
        margin: 0 0 4px 0;
        color: #07142c;
        font-size: 1rem;
        font-weight: 800;
    }

    .map-preview-header p {
        margin: 0;
        color: #6b7280;
        font-size: 0.78rem;
    }

    .map-preview-header button {
        flex-shrink: 0;
        padding: 7px 10px;
        border: none;
        border-radius: 9px;
        background: #07142c;
        color: white;
        font-size: 0.75rem;
        font-weight: 800;
        cursor: pointer;
    }

    .map-preview {
        flex: 1;
        min-height: 0;
        overflow: hidden;
        border: 1px solid #d7dee8;
        border-radius: 12px;
        background: #f4f6fb;
    }

    :global(.mini-map-marker-wrapper) {
        border: none;
        background: transparent;
    }

    :global(.mini-map-marker) {
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-end;
        filter: drop-shadow(0 2px 3px rgba(7, 20, 44, 0.3));
    }

    :global(.mini-map-marker strong) {
        margin-bottom: 2px;
        padding: 1px 4px;
        border-radius: 999px;
        background: white;
        color: #07142c;
        font-size: 0.58rem;
        font-weight: 950;
    }

    :global(.mini-map-marker > div) {
        width: 18px;
        display: flex;
        flex-direction: column-reverse;
        overflow: hidden;
        border: 2px solid white;
        border-radius: 5px 5px 2px 2px;
    }

    :global(.mini-map-marker span) {
        display: block;
        width: 100%;
    }

    /****************************************
    INFOBOX
    ****************************************/

    .info-placeholder {
        background: white;
        padding: 20px;
        border-radius: 16px;
        min-height: 130px;
        margin-bottom: 24px;
    }

    .info-placeholder h3 {
        margin: 0 0 8px 0;
        font-size: 1rem;
        font-weight: 750;
    }

    .info-placeholder p {
        margin: 0;
        color: #6b7280;
    }

    /****************************************
    INSIGHTS
    ****************************************/

    .insight-column {
        display: flex;
        flex-direction: column;
        min-height: 0;
    }

    .insights-title {
        margin: 0 0 16px 0;
        font-size: 1.25rem;
        font-weight: 800;
    }

    .insights-card {
        flex-shrink: 0;
        min-height: 210px;
        margin-bottom: 16px;
    }

    .insight-placeholder-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
        margin-top: 18px;
    }

    .insight-placeholder-grid div {
        background: #f4f6fb;
        border-radius: 12px;
        padding: 14px;
    }

    .insight-placeholder-grid span {
        display: block;
        color: #6b7280;
        font-size: 0.8rem;
        margin-bottom: 6px;
    }

    .insight-placeholder-grid strong {
        display: block;
        color: #07142c;
        font-size: 1.15rem;
        font-weight: 800;
    }

    .insight-placeholder-grid div:last-child:nth-child(odd) {
        grid-column: 1 / -1;
    }

    /****************************************
    CHART PREVIEW
    ****************************************/

    .chart-card {
        flex: 1;
        min-height: 0;
        display: flex;
        flex-direction: column;
        background: white;
        padding: 20px;
        border-radius: 16px;
        margin-bottom: 0;
    }

    .chart-card h3 {
        margin: 0 0 8px 0;
        font-size: 1rem;
        font-weight: 750;
    }

    .chart-card p {
        margin: 0 0 18px 0;
        color: #6b7280;
    }

    .preview-bar-chart {
        flex: 1;
        min-height: 140px;
        height: 145px;
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(38px, 1fr));
        align-items: stretch;
        gap: 10px;
        padding: 16px 12px 10px;
        border-radius: 14px;
        background: #f4f6fb;
    }

    .preview-bar-column {
        min-width: 0;
        display: grid;
        grid-template-rows: 20px minmax(100px, 1fr) 22px;
        gap: 6px;
        text-align: center;
    }

    .preview-bar-column strong {
        color: #07142c;
        font-size: 0.78rem;
        font-weight: 850;
    }

    .preview-bar-column span {
        overflow: hidden;
        color: #64748b;
        font-size: 0.7rem;
        font-weight: 750;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .preview-bar-track {
        min-height: 100px;
        display: flex;
        align-items: end;
        border-bottom: 2px solid #cbd5e1;
    }

    .preview-bar {
        width: 100%;
        background: #07142c;
        border-radius: 8px 8px 0 0;
        opacity: 0.85;
    }

    .chart-empty-state {
        flex: 1;
        min-height: 140px;
        display: grid;
        place-items: center;
        border-radius: 14px;
        background: #f4f6fb;
        color: #6b7280;
        font-size: 0.85rem;
    }

    /****************************************
    QUERY BOX
    ****************************************/

    .query-dropdown {
        width: 100%;
        margin-top: 16px;
        flex-shrink: 0;
    }

    .query-toggle {
        width: 100%;
        height: 44px;
        border: none;
        border-radius: 12px;
        background: #07142c;
        color: white;
        font-size: 0.95rem;
        font-weight: 750;
        cursor: pointer;
    }

    .query-toggle:hover {
        background: #0f2550;
    }

    .query-box {
        margin-top: 12px;
        background: #1f2937;
        color: #e5e7eb;
        padding: 18px;
        border-radius: 16px;
        height: 45vh;
        max-height: 460px;
        overflow: auto;
    }

    .query-box pre {
        max-width: 100%;
        overflow-x: auto;
    }

    .query-box code {
        font-family: var(--font-mono);
        font-size: 0.9rem;
    }

</style>
