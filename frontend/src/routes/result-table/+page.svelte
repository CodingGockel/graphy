<script lang="ts">
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { filterFullTableRows } from '$lib/fullTableFilter';
    import { API_BASE_URL } from '$lib/api';

    type Mode = 'preview' | 'full';

    type ChartType = 'boxplot' | 'barplot' | 'pie';

    const FULL_TABLE_CACHE_KEY = 'fullTableRaw';
    const FULL_TABLE_FILTER_QUERY_KEY = 'fullTableFilterQuery';

    let mode = $state<Mode>('full');

    let previewColumns = $state<string[]>([]);
    let previewResults = $state<any[]>([]);
    let fullTableFilterQuery = $state('');

    // The Full Table always starts with the complete graph and is filtered
    // solely by words from the most recent user input.
    let fullTableRows = $state<any[]>([]);
    let fullResults = $derived(filterFullTableRows(fullTableRows, fullTableFilterQuery));

    // Aktuell geöffnetes Diagramm
    let openChart = $state<ChartType | null>(null);

    // Diagramm, das gerade "generiert" wird
    let loadingChart = $state<ChartType | null>(null);

    /****************************************
    BOXPLOT CHART STATE
    ****************************************/

    let boxplotValueColumn = $state('floweringDuration');
    let boxplotGroupColumn = $state('garden');

    const boxplotChartWidth = 1200;
    const boxplotChartHeight = 520;

    const boxplotPadding = {
        top: 40,
        right: 70,
        bottom: 70,
        left: 360
    };

    /****************************************
    BARPLOT CHART STATE
    ****************************************/

    const barplotChartWidth = 1200;
    const barplotChartHeight = 520;

    const barplotPadding = {
        top: 40,
        right: 90,
        bottom: 70,
        left: 360
    };

    /****************************************
    PIE CHART STATE
    ****************************************/

    let pieCategoryColumn = $state('garden');
    let pieValueMode = $state<'count' | 'sum'>('count');
    let pieValueColumn = $state('floweringDuration');

    const pieChartWidth = 900;
    const pieChartHeight = 520;

    const pieCenterX = 450;
    const pieCenterY = 250;
    const pieRadius = 160;

    /****************************************
    FULL TABLE DUMMY
    ****************************************/

    // Dummy-Spalten für die Full Table, bis echte Daten angebunden sind
    const fullColumns = [
        'species',
        'garden',
        'city',
        'country',
        'year',
        'firstFlowerDay',
        'lastFlowerDay',
        'floweringDuration'
    ];

    let activeResults = $derived(
        mode === 'preview' ? previewResults : fullResults
    );

    let activeColumns = $derived(
        mode === 'preview' ? previewColumns : fullColumns
    );

    // Numerische Full-Table-Spalten werden automatisch als Werte angeboten
    let numericColumns = $derived(
        getNumericColumns(fullColumns, fullResults)
    );

    // Text-/Kategorie-Spalten werden automatisch als Gruppierung angeboten
    let categoryColumns = $derived(
        getCategoricalColumns(fullColumns, fullResults)
    );

    // Falls später andere Daten kommen, werden ungültige Dropdown-Werte automatisch korrigiert
    $effect(() => {
        if (fullResults.length === 0) return;

        if (numericColumns.length > 0 && !numericColumns.includes(boxplotValueColumn)) {
            boxplotValueColumn = numericColumns.includes('floweringDuration')
                ? 'floweringDuration'
                : numericColumns[0];
        }

        if (categoryColumns.length > 0 && !categoryColumns.includes(boxplotGroupColumn)) {
            boxplotGroupColumn = categoryColumns.includes('garden')
                ? 'garden'
                : categoryColumns[0];
        }

        if (categoryColumns.length > 0 && !categoryColumns.includes(pieCategoryColumn)) {
            pieCategoryColumn = categoryColumns.includes('garden')
                ? 'garden'
                : categoryColumns[0];
        }

        if (numericColumns.length > 0 && !numericColumns.includes(pieValueColumn)) {
            pieValueColumn = numericColumns.includes('floweringDuration')
                ? 'floweringDuration'
                : numericColumns[0];
        }
    });

    // Formatiert Spaltennamen für die Tabellenanzeige
    function formatColumnName(col: string) {
        const columnNames: Record<string, string> = {
            species: 'Species / Organism',
            garden: 'Garden',
            city: 'City',
            country: 'Country',
            year: 'Year',
            firstFlowerDay: 'First Flower Day',
            lastFlowerDay: 'Last Flower Day',
            floweringDuration: 'Flowering Duration'
        };

        return columnNames[col] ??
            col
                .replace(/([A-Z])/g, ' $1')
                .replace(/^./, (char) => char.toUpperCase());
    }

    function cleanDisplayText(value: any) {
        return String(value ?? '')
            .replace(/Ã¤/g, 'ä')
            .replace(/Ã¶/g, 'ö')
            .replace(/Ã¼/g, 'ü')
            .replace(/Ã„/g, 'Ä')
            .replace(/Ã–/g, 'Ö')
            .replace(/Ãœ/g, 'Ü')
            .replace(/ÃŸ/g, 'ß');
    }

    function truncateChartLabel(value: any, maxLength = 27) {
        const text = cleanDisplayText(value);
        return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
    }

    //Öffnet Map Page mit gewähltem Botanischen Garten
    function openMapForRow(row: any) {
        const params = new URLSearchParams();

        if (row.city) params.set('city', String(row.city));
        if (row.country) params.set('country', String(row.country));
        if (row.garden) params.set('garden', String(row.garden));

        goto(`/map?${params.toString()}`);
    }

    // Öffnet oder schließt ein Diagramm.
    // Beim ersten Öffnen wird kurz eine Ladeanimation angezeigt,
    // später kann hier die echte Diagramm-Generierung gestartet werden.
    function toggleChart(chart: ChartType) {
        if (openChart === chart) {
            openChart = null;
            loadingChart = null;
            return;
        }

        openChart = chart;
        loadingChart = chart;

        setTimeout(() => {
            if (openChart === chart) {
                loadingChart = null;
            }
        }, 700);
    }

    /****************************************
    SHARED CHART HELPERS
    ****************************************/

    // Wandelt Tabellenwerte sicher in Zahlen um
    function toNumber(value: any) {
        const numberValue = Number(value);

        return Number.isNaN(numberValue) ? null : numberValue;
    }

    // Prüft, ob eine Tabellenzelle wirklich Inhalt hat
    function hasCellValue(value: any) {
        return value !== null &&
            value !== undefined &&
            String(value).trim() !== '';
    }

    // Prüft, ob eine Spalte überwiegend numerisch ist
    function isNumericDataColumn(rows: any[], col: string) {
        const values = rows
            .map((row) => row[col])
            .filter(hasCellValue);

        if (values.length === 0) return false;

        return values.every((value) => toNumber(value) !== null);
    }

    // Holt alle numerischen Spalten aus der Full Table
    function getNumericColumns(columns: string[], rows: any[]) {
        return columns.filter((col) => isNumericDataColumn(rows, col));
    }

    // Holt alle nicht-numerischen Spalten aus der Full Table
    function getCategoricalColumns(columns: string[], rows: any[]) {
        return columns.filter((col) => {
            const values = rows
                .map((row) => row[col])
                .filter(hasCellValue);

            if (values.length === 0) return false;

            return !isNumericDataColumn(rows, col);
        });
    }

    /****************************************
    BOXPLOT CHART LOGIC
    ****************************************/

    function getQuantile(values: number[], q: number) {
        const sorted = [...values].sort((a, b) => a - b);
        const pos = (sorted.length - 1) * q;
        const base = Math.floor(pos);
        const rest = pos - base;

        if (sorted[base + 1] !== undefined) {
            return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
        }

        return sorted[base];
    }

    function buildBoxplotData(rows: any[], valueCol: string, groupCol: string) {
        const groups = new Map<string, number[]>();

        for (const row of rows) {
            const value = toNumber(row[valueCol]);
            if (value === null) continue;

            const group = hasCellValue(row[groupCol])
                ? String(row[groupCol])
                : 'All data';

            if (!groups.has(group)) groups.set(group, []);
            groups.get(group)?.push(value);
        }

        return Array.from(groups.entries())
            .map(([name, values]) => {
                const sorted = values.sort((a, b) => a - b);

                return {
                    name,
                    values: sorted,
                    min: Math.min(...sorted),
                    q1: getQuantile(sorted, 0.25),
                    median: getQuantile(sorted, 0.5),
                    q3: getQuantile(sorted, 0.75),
                    max: Math.max(...sorted),
                    count: sorted.length
                };
            })
            .slice(0, 8);
    }

    function getBoxplotBounds(boxes: ReturnType<typeof buildBoxplotData>) {
        const values = boxes.flatMap((box) => box.values);

        if (values.length === 0) {
            return { min: 0, max: 1 };
        }

        const min = Math.min(...values);
        const max = Math.max(...values);
        const padding = Math.max(5, (max - min) * 0.12);

        return {
            min: min - padding,
            max: max === min ? max + 1 : max + padding
        };
    }

    function getBoxplotX(value: number, bounds: ReturnType<typeof getBoxplotBounds>) {
        const innerWidth = boxplotChartWidth - boxplotPadding.left - boxplotPadding.right;
        const ratio = (value - bounds.min) / (bounds.max - bounds.min);

        return boxplotPadding.left + ratio * innerWidth;
    }

    function getBoxplotY(index: number, total: number) {
        const innerHeight = boxplotChartHeight - boxplotPadding.top - boxplotPadding.bottom;
        const gap = innerHeight / Math.max(total, 1);

        return boxplotPadding.top + gap * index + gap / 2;
    }

    function getBoxplotTicks(bounds: ReturnType<typeof getBoxplotBounds>) {
        const steps = 5;
        const ticks = [];

        for (let i = 0; i <= steps; i++) {
            ticks.push(Math.round(bounds.min + ((bounds.max - bounds.min) / steps) * i));
        }

        return ticks;
    }

    let boxplotData = $derived(
        buildBoxplotData(fullResults, boxplotValueColumn, boxplotGroupColumn)
    );

    let boxplotBounds = $derived(
        getBoxplotBounds(boxplotData)
    );

    let boxplotTicks = $derived(
        getBoxplotTicks(boxplotBounds)
    );

    /****************************************
    BARPLOT CHART LOGIC
    ****************************************/

    function buildBarplotData(rows: any[]) {
        const locations = new Map<string, Map<string, number>>();

        for (const row of rows) {
            const location = hasCellValue(row.garden)
                ? cleanDisplayText(row.garden)
                : hasCellValue(row.city)
                    ? cleanDisplayText(row.city)
                : 'Unknown';
            const year = hasCellValue(row.year) ? String(row.year) : 'Unknown year';

            if (!locations.has(location)) locations.set(location, new Map());

            const yearCounts = locations.get(location);
            yearCounts?.set(year, (yearCounts.get(year) ?? 0) + 1);
        }

        return Array.from(locations.entries())
            .map(([name, yearCounts]) => {
                let start = 0;
                const segments = Array.from(yearCounts.entries())
                    .sort(([yearA], [yearB]) => yearA.localeCompare(yearB))
                    .map(([year, count]) => {
                        const segment = { year, count, start, end: start + count };
                        start += count;
                        return segment;
                    });

                return { name, total: start, segments };
            })
            .sort((a, b) => b.total - a.total)
            .slice(0, 8);
    }

    function getBarplotX(value: number, max: number) {
        const innerWidth = barplotChartWidth - barplotPadding.left - barplotPadding.right;
        return barplotPadding.left + (value / Math.max(max, 1)) * innerWidth;
    }

    function getBarplotY(index: number, total: number) {
        const innerHeight = barplotChartHeight - barplotPadding.top - barplotPadding.bottom;
        const gap = innerHeight / Math.max(total, 1);

        return barplotPadding.top + gap * index + gap * 0.15;
    }

    function getBarplotTicks(max: number) {
        return Array.from({ length: 6 }, (_, index) => Math.round((max / 5) * index));
    }

    let barplotData = $derived(
        buildBarplotData(fullResults)
    );

    let barplotYears = $derived(
        Array.from(
            new Set(barplotData.flatMap((location) => location.segments.map((segment) => segment.year)))
        ).sort((a, b) => a.localeCompare(b))
    );

    let barplotMax = $derived(
        Math.max(...barplotData.map((item) => item.total), 1)
    );

    let barplotTicks = $derived(
        getBarplotTicks(barplotMax)
    );

    /****************************************
    PIE CHART LOGIC
    ****************************************/

    function buildPieData(rows: any[], categoryCol: string, valueMode: 'count' | 'sum', valueCol: string) {
        const groups = new Map<string, number>();

        for (const row of rows) {
            const category = hasCellValue(row[categoryCol])
                ? String(row[categoryCol])
                : 'Unknown';

            const value = valueMode === 'sum'
                ? toNumber(row[valueCol])
                : 1;

            if (value === null) continue;

            groups.set(category, (groups.get(category) ?? 0) + value);
        }

        const total = Array.from(groups.values()).reduce((sum, value) => sum + value, 0);

        if (total === 0) return [];

        return Array.from(groups.entries())
            .map(([name, value], index) => ({
                name,
                value,
                percentage: value / total,
                colorClass: `series-${index % 6}`
            }))
            .sort((a, b) => b.value - a.value)
            .slice(0, 8);
    }

    function polarToCartesian(cx: number, cy: number, radius: number, angleInDegrees: number) {
        const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180;

        return {
            x: cx + radius * Math.cos(angleInRadians),
            y: cy + radius * Math.sin(angleInRadians)
        };
    }

    function describePieSlice(cx: number, cy: number, radius: number, startAngle: number, endAngle: number) {
        const start = polarToCartesian(cx, cy, radius, endAngle);
        const end = polarToCartesian(cx, cy, radius, startAngle);
        const largeArcFlag = endAngle - startAngle <= 180 ? 0 : 1;

        return [
            `M ${cx} ${cy}`,
            `L ${start.x} ${start.y}`,
            `A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`,
            'Z'
        ].join(' ');
    }

    function getPieSlices(data: ReturnType<typeof buildPieData>) {
        let currentAngle = 0;

        return data.map((item) => {
            const startAngle = currentAngle;
            const endAngle = currentAngle + item.percentage * 360;

            currentAngle = endAngle;

            return {
                ...item,
                startAngle,
                endAngle,
                path: describePieSlice(
                    pieCenterX,
                    pieCenterY,
                    pieRadius,
                    startAngle,
                    endAngle
                )
            };
        });
    }

    function formatPieValue(value: number) {
        return Number.isInteger(value)
            ? String(value)
            : value.toFixed(1);
    }

    let pieData = $derived(
        buildPieData(fullResults, pieCategoryColumn, pieValueMode, pieValueColumn)
    );

    let pieSlices = $derived(
        getPieSlices(pieData)
    );

    let pieTotal = $derived(
        pieData.reduce((sum, item) => sum + item.value, 0)
    );

    function parseSparqlResultString(raw: string | null) {
        if (!raw) return [];

        try {
            const parsed = JSON.parse(raw);
            const table = parsed.full_table ?? parsed;

            if (Array.isArray(table.rows)) {
                return table.rows;
            }

            const bindings = parsed?.results?.bindings ?? [];

            return bindings
                .map((binding: any) => {
                    const row: Record<string, any> = {};

                    for (const col of fullColumns) {
                        row[col] = binding?.[col]?.value ?? '';
                    }

                    return row;
                })
                .filter((row: any) =>
                    fullColumns.some((col) => {
                        const value = row[col];

                        return value !== null &&
                            value !== undefined &&
                            String(value).trim() !== '';
                    })
                );
        } catch (error) {
            console.error('Could not parse full_table result:', error);
            return [];
        }
    }

    // Lädt gespeicherte Query-Ergebnisse und echte Full-Table-Daten
    onMount(async () => {
        previewColumns = JSON.parse(localStorage.getItem('previewColumns') ?? '[]');
        previewResults = JSON.parse(localStorage.getItem('previewResults') ?? '[]');
        fullTableFilterQuery = localStorage.getItem(FULL_TABLE_FILTER_QUERY_KEY) ?? '';

        let storedFullTable = localStorage.getItem(FULL_TABLE_CACHE_KEY);
        let parsedFullTable = parseSparqlResultString(storedFullTable);

        if (parsedFullTable.length === 0) {
            try {
                const response = await fetch(`${API_BASE_URL}/chat/full_table`);
                const data = await response.json();

                if (response.ok && Array.isArray(data.full_table?.rows)) {
                    localStorage.setItem(FULL_TABLE_CACHE_KEY, JSON.stringify(data.full_table));
                    storedFullTable = JSON.stringify(data.full_table);
                    parsedFullTable = parseSparqlResultString(storedFullTable);
                }
            } catch (error) {
                console.error('Could not load Full Table:', error);
            }
        }

        fullTableRows = parsedFullTable;
    });

    // Lädt die Full Table als CSV-Datei herunter
    function downloadCSV() {
        if (fullResults.length === 0 || fullColumns.length === 0) return;

        const escapeCSV = (value: any) => {
            const text = String(value ?? '');
            return `"${text.replace(/"/g, '""')}"`;
        };

        const header = fullColumns.map(escapeCSV).join(',');

        const rows = fullResults.map((row) =>
            fullColumns.map((col) => escapeCSV(row[col])).join(',')
        );

        const csv = ['sep=,', header, ...rows].join('\n');

        const blob = new Blob([csv], {
            type: 'text/csv;charset=utf-8;'
        });

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');

        a.href = url;
        a.download = 'full-table-results.csv';

        a.click();
        URL.revokeObjectURL(url);
    }

    // Erkennt lange Textwerte, damit sie in der Tabelle kompakter angezeigt werden können
    function isLongCellValue(value: any) {
        return String(value ?? '').length > 80;
    }

    // Kürzt lange Zellwerte für die Tabellenansicht.
    // Der volle Wert bleibt später über das title-Attribut sichtbar.
    function formatCellValue(value: any) {
        const text = cleanDisplayText(value);

        if (text.length <= 120) {
            return text;
        }

        return `${text.slice(0, 120)}...`;
    }

    // Erkennt numerische Werte, damit sie rechtsbündig angezeigt werden können
    function isNumericCellValue(value: any) {
        if (value === null || value === undefined || value === '') return false;

        return !Number.isNaN(Number(value));
    }

    // Erkennt, ob eine ganze Spalte hauptsächlich numerische Werte enthält
    function isNumericColumn(col: string) {
        const values = activeResults
            .map((row) => row[col])
            .filter(hasCellValue);

        if (values.length === 0) return false;

        return values.every((value) => !Number.isNaN(Number(value)));
    }
</script>

<div class="table-page">
    <div class="table-header">
        <h1 class="datahub-title">Results Table</h1>

        <!-- Aktionen für CSV-Export und Tabellenmodus -->
        <div class="table-actions">
            <div
                class="filter-status"
                class:filtered={fullTableFilterQuery.trim().length > 0}
                title={fullTableFilterQuery.trim().length > 0
                    ? `Filtered by: ${fullTableFilterQuery}`
                    : 'No Full Table filter is active'}
            >
                Filtered
            </div>
            <button class="download-button" onclick={downloadCSV}>
                Download CSV
            </button>

            <div class="mode-toggle">
                <button
                    class:active={mode === 'full'}
                    onclick={() => mode = 'full'}
                >
                    Full Table
                </button>

                <button
                    class:active={mode === 'preview'}
                    onclick={() => mode = 'preview'}
                >
                    Query Result
                </button>

                <div class="slider" class:preview={mode === 'preview'}></div>
            </div>
        </div>
    </div>

    <!-- Große Ergebnis-Tabelle -->
    <section class="results big-table">
        <h3>{mode === 'preview' ? 'Query Results' : 'Full Data Table'}</h3>

        {#if activeColumns.length > 0 && activeResults.length > 0}
            <div class="table-scroll">
                <table class="data-table">
                    <thead>
                        <tr>
                            {#each activeColumns as col}
                                <th class:numeric-column={isNumericColumn(col)}>
                                    <span>{formatColumnName(col)}</span>
                                </th>
                            {/each}
                        </tr>
                    </thead>

                    <tbody>
                        {#each activeResults as row}
                            <tr>
                                {#each activeColumns as col}
                                    <td
                                        class:long-cell={isLongCellValue(row[col])}
                                        class:numeric-cell={isNumericCellValue(row[col])}
                                        class:city-cell={col === 'city'}
                                        title={cleanDisplayText(row[col])}
                                        >
                                            {#if col === 'city'}
                                                <div class="city-cell-content">
                                                    <button
                                                        class="map-pin-button"
                                                        type="button"
                                                        title="Show on map"
                                                        onclick={(event) => {
                                                            event.stopPropagation();
                                                            openMapForRow(row);
                                                        }}
                                                    >
                                                        📍
                                                    </button>

                                                    <span>{formatCellValue(row[col])}</span>
                                                </div>
                                            {:else}
                                                {formatCellValue(row[col])}
                                            {/if}
                                    </td>
                                {/each}
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        {:else if mode === 'preview'}
            <div class="empty-state">
                No query results available yet.
            </div>
        {/if}
    </section>

    <!-- Bereich für Diagramme -->
    <section class="visualization-section">
        <div class="visualization-header">
            <div>
                <h2>Visualizations</h2>
                <p>Dynamic charts generated from the result table.</p>
            </div>
        </div>

        <div class="chart-accordion">
            <!-- Boxplot: sinnvoll für Verteilungen, z.B. flowering duration pro Art oder Garten -->
            <section class="chart-accordion-item">
                <button
                    class="chart-accordion-trigger"
                    class:active={openChart === 'boxplot'}
                    onclick={() => toggleChart('boxplot')}
                >
                    <div>
                        <h3>Boxplot</h3>
                        <p>Compares distributions, for example flowering duration by species.</p>
                    </div>

                    <span>{openChart === 'boxplot' ? '−' : '+'}</span>
                </button>

                {#if openChart === 'boxplot'}
                    <div class="chart-accordion-content">
                        {#if loadingChart === 'boxplot'}
                            <div class="chart-loading">
                                <span></span>
                                <p>Generating boxplot...</p>
                            </div>
                        {:else}
                            <div class="chart-panel chart-panel-content">
                                <div class="chart-builder-layout">
                                    <aside class="chart-sidebar">
                                        <div class="chart-sidebar-header">
                                            <h3>Boxplot Settings</h3>

                                            <span class="chart-badge">
                                                {boxplotData.length} group{boxplotData.length === 1 ? '' : 's'}
                                            </span>
                                        </div>

                                        <p>
                                            Select a numeric value and a category to compare distributions.
                                        </p>

                                        <div class="chart-controls">
                                            <label>
                                                <span>Value</span>

                                                <select bind:value={boxplotValueColumn}>
                                                    {#each numericColumns as col}
                                                        <option value={col}>{formatColumnName(col)}</option>
                                                    {/each}
                                                </select>
                                            </label>

                                            <label>
                                                <span>Group by</span>

                                                <select bind:value={boxplotGroupColumn}>
                                                    {#each categoryColumns as col}
                                                        <option value={col}>{formatColumnName(col)}</option>
                                                    {/each}
                                                </select>
                                            </label>
                                        </div>
                                    </aside>

                                    <div class="boxplot-chart">
                                        {#if boxplotData.length > 0}
                                            <svg
                                                viewBox={`0 0 ${boxplotChartWidth} ${boxplotChartHeight}`}
                                                preserveAspectRatio="none"
                                            >
                                                <rect
                                                    x="0"
                                                    y="0"
                                                    width={boxplotChartWidth}
                                                    height={boxplotChartHeight}
                                                    rx="14"
                                                />

                                                {#each boxplotTicks as tick}
                                                    {@const x = getBoxplotX(tick, boxplotBounds)}

                                                    <line
                                                        class="boxplot-grid-line"
                                                        x1={x}
                                                        y1={boxplotPadding.top}
                                                        x2={x}
                                                        y2={boxplotChartHeight - boxplotPadding.bottom}
                                                    />

                                                    <text
                                                        class="axis-label"
                                                        x={x}
                                                        y={boxplotChartHeight - boxplotPadding.bottom + 34}
                                                        text-anchor="middle"
                                                    >
                                                        {tick}
                                                    </text>
                                                {/each}

                                                <line
                                                    class="axis-line"
                                                    x1={boxplotPadding.left}
                                                    y1={boxplotChartHeight - boxplotPadding.bottom}
                                                    x2={boxplotChartWidth - boxplotPadding.right}
                                                    y2={boxplotChartHeight - boxplotPadding.bottom}
                                                />

                                                {#each boxplotData as box, index}
                                                    {@const y = getBoxplotY(index, boxplotData.length)}
                                                    {@const minX = getBoxplotX(box.min, boxplotBounds)}
                                                    {@const q1X = getBoxplotX(box.q1, boxplotBounds)}
                                                    {@const medianX = getBoxplotX(box.median, boxplotBounds)}
                                                    {@const q3X = getBoxplotX(box.q3, boxplotBounds)}
                                                    {@const maxX = getBoxplotX(box.max, boxplotBounds)}

                                                    <text
                                                        class="boxplot-group-label"
                                                        x={boxplotPadding.left - 18}
                                                        y={y + 5}
                                                        text-anchor="end"
                                                    >
                                                        {box.name}
                                                    </text>

                                                    <line class="boxplot-whisker" x1={minX} y1={y} x2={q1X} y2={y} />
                                                    <line class="boxplot-whisker" x1={q3X} y1={y} x2={maxX} y2={y} />

                                                    <line class="boxplot-cap" x1={minX} y1={y - 18} x2={minX} y2={y + 18} />
                                                    <line class="boxplot-cap" x1={maxX} y1={y - 18} x2={maxX} y2={y + 18} />

                                                    <rect
                                                        class="boxplot-box"
                                                        x={q1X}
                                                        y={y - 24}
                                                        width={Math.max(q3X - q1X, 4)}
                                                        height="48"
                                                        rx="10"
                                                    />

                                                    <line
                                                        class="boxplot-median"
                                                        x1={medianX}
                                                        y1={y - 26}
                                                        x2={medianX}
                                                        y2={y + 26}
                                                    />

                                                    <text
                                                        class="boxplot-count"
                                                        x={maxX + 14}
                                                        y={y + 5}
                                                    >
                                                        n={box.count}
                                                    </text>

                                                    <title>
                                                        {box.name}
                                                        Min: {Math.round(box.min)}
                                                        Q1: {Math.round(box.q1)}
                                                        Median: {Math.round(box.median)}
                                                        Q3: {Math.round(box.q3)}
                                                        Max: {Math.round(box.max)}
                                                    </title>
                                                {/each}

                                                <text
                                                    class="axis-title"
                                                    x={(boxplotPadding.left + boxplotChartWidth - boxplotPadding.right) / 2}
                                                    y={boxplotChartHeight - 18}
                                                    text-anchor="middle"
                                                >
                                                    {formatColumnName(boxplotValueColumn)}
                                                </text>
                                            </svg>
                                        {:else}
                                            <div class="chart-empty-state">
                                                No boxplot data available for the selected columns.
                                            </div>
                                        {/if}
                                    </div>
                                </div>
                            </div>
                        {/if}
                    </div>
                {/if}
            </section>

            <!-- Horizontaler Barplot für gut lesbare Kategorienamen -->
            <section class="chart-accordion-item">
                <button
                    class="chart-accordion-trigger"
                    class:active={openChart === 'barplot'}
                    onclick={() => toggleChart('barplot')}
                >
                    <div>
                        <h3>Stacked Barplot</h3>
                        <p>Shows observation counts per location, stacked and colored by year.</p>
                    </div>

                    <span>{openChart === 'barplot' ? '−' : '+'}</span>
                </button>

                {#if openChart === 'barplot'}
                    <div class="chart-accordion-content">
                        {#if loadingChart === 'barplot'}
                            <div class="chart-loading">
                                <span></span>
                                <p>Generating barplot...</p>
                            </div>
                        {:else}
                            <div class="chart-panel chart-panel-content">
                                <div class="chart-builder-layout">
                                    <aside class="chart-sidebar">
                                        <div class="chart-sidebar-header">
                                            <h3>Observation Counts</h3>
                                            <span class="chart-badge">
                                                {barplotData.length} location{barplotData.length === 1 ? '' : 's'}
                                            </span>
                                        </div>

                                        <p>
                                            Each bar represents a location. Colored segments show how many observations
                                            were recorded in each year.
                                        </p>

                                        <div class="barplot-legend">
                                            {#each barplotYears as year, index}
                                                <div>
                                                    <span class={`legend-dot series-${index % 6}`}></span>
                                                    <strong>{year}</strong>
                                                </div>
                                            {/each}
                                        </div>
                                    </aside>

                                    <div class="barplot-chart">
                                        {#if barplotData.length > 0}
                                            <svg viewBox={`0 0 ${barplotChartWidth} ${barplotChartHeight}`} preserveAspectRatio="none">
                                                <rect x="0" y="0" width={barplotChartWidth} height={barplotChartHeight} rx="14" />

                                                {#each barplotTicks as tick}
                                                    {@const x = getBarplotX(tick, barplotMax)}
                                                    <line
                                                        class="barplot-grid-line"
                                                        x1={x}
                                                        y1={barplotPadding.top}
                                                        x2={x}
                                                        y2={barplotChartHeight - barplotPadding.bottom}
                                                    />
                                                    <text
                                                        class="axis-label"
                                                        x={x}
                                                        y={barplotChartHeight - barplotPadding.bottom + 34}
                                                        text-anchor="middle"
                                                    >
                                                        {tick}
                                                    </text>
                                                {/each}

                                                {#each barplotData as bar, index}
                                                    {@const y = getBarplotY(index, barplotData.length)}
                                                    {@const barHeight = (barplotChartHeight - barplotPadding.top - barplotPadding.bottom) / Math.max(barplotData.length, 1) * 0.7}
                                                    {@const endX = getBarplotX(bar.total, barplotMax)}

                                                    <text
                                                        class="barplot-group-label"
                                                        x={barplotPadding.left - 18}
                                                        y={y + barHeight / 2 + 5}
                                                        text-anchor="end"
                                                    >
                                                        {truncateChartLabel(bar.name)}
                                                        <title>{bar.name}</title>
                                                    </text>
                                                    {#each bar.segments as segment}
                                                        {@const yearIndex = barplotYears.indexOf(segment.year)}
                                                        {@const segmentStartX = getBarplotX(segment.start, barplotMax)}
                                                        {@const segmentEndX = getBarplotX(segment.end, barplotMax)}
                                                        <rect
                                                            class={`barplot-bar series-${yearIndex % 6}`}
                                                            x={segmentStartX}
                                                            y={y}
                                                            width={Math.max(segmentEndX - segmentStartX, 2)}
                                                            height={barHeight}
                                                            rx="4"
                                                        >
                                                            <title>{bar.name}, {segment.year}: {segment.count} observations</title>
                                                        </rect>
                                                    {/each}
                                                    <text class="barplot-value" x={endX + 12} y={y + barHeight / 2 + 5}>
                                                        {bar.total}
                                                    </text>
                                                {/each}

                                                <text
                                                    class="axis-title"
                                                    x={(barplotPadding.left + barplotChartWidth - barplotPadding.right) / 2}
                                                    y={barplotChartHeight - 18}
                                                    text-anchor="middle"
                                                >
                                                    Observation count
                                                </text>
                                            </svg>
                                        {:else}
                                            <div class="chart-empty-state">
                                                No barplot data available for the selected columns.
                                            </div>
                                        {/if}
                                    </div>
                                </div>
                            </div>
                        {/if}
                    </div>
                {/if}
            </section>

            <!-- Pie Chart: eher für einfache Anteilsverteilungen, deshalb bewusst unten -->
            <section class="chart-accordion-item">
                <button
                    class="chart-accordion-trigger"
                    class:active={openChart === 'pie'}
                    onclick={() => toggleChart('pie')}
                >
                    <div>
                        <h3>Pie Chart</h3>
                        <p>Shows simple proportions, for example observations by garden.</p>
                    </div>

                    <span>{openChart === 'pie' ? '−' : '+'}</span>
                </button>

                {#if openChart === 'pie'}
                    <div class="chart-accordion-content">
                        {#if loadingChart === 'pie'}
                            <div class="chart-loading">
                                <span></span>
                                <p>Generating pie chart...</p>
                            </div>
                        {:else}
                            <div class="chart-panel chart-panel-content">
                                <div class="chart-builder-layout">
                                    <aside class="chart-sidebar">
                                        <div class="chart-sidebar-header">
                                            <h3>Pie Settings</h3>

                                            <span class="chart-badge">
                                                {pieData.length} slice{pieData.length === 1 ? '' : 's'}
                                            </span>
                                        </div>

                                        <p>
                                            Select a category and choose whether slices count rows or sum a numeric value.
                                        </p>

                                        <div class="chart-controls">
                                            <label>
                                                <span>Category</span>

                                                <select bind:value={pieCategoryColumn}>
                                                    {#each categoryColumns as col}
                                                        <option value={col}>{formatColumnName(col)}</option>
                                                    {/each}
                                                </select>
                                            </label>

                                            <label>
                                                <span>Value mode</span>

                                                <select bind:value={pieValueMode}>
                                                    <option value="count">Count rows</option>
                                                    <option value="sum">Sum numeric column</option>
                                                </select>
                                            </label>

                                            {#if pieValueMode === 'sum'}
                                                <label>
                                                    <span>Value</span>

                                                    <select bind:value={pieValueColumn}>
                                                        {#each numericColumns as col}
                                                            <option value={col}>{formatColumnName(col)}</option>
                                                        {/each}
                                                    </select>
                                                </label>
                                            {/if}
                                        </div>
                                    </aside>

                                    <div class="pie-chart">
                                        {#if pieSlices.length > 0}
                                            <div class="pie-chart-layout">
                                                <svg
                                                    viewBox={`0 0 ${pieChartWidth} ${pieChartHeight}`}
                                                    preserveAspectRatio="xMidYMid meet"
                                                >
                                                    <rect
                                                        x="0"
                                                        y="0"
                                                        width={pieChartWidth}
                                                        height={pieChartHeight}
                                                        rx="14"
                                                    />

                                                    {#each pieSlices as slice}
                                                        <path
                                                            class={`pie-slice ${slice.colorClass}`}
                                                            d={slice.path}
                                                        >
                                                            <title>
                                                                {slice.name}
                                                                Value: {formatPieValue(slice.value)}
                                                                Share: {Math.round(slice.percentage * 100)}%
                                                            </title>
                                                        </path>
                                                    {/each}

                                                    <circle
                                                        class="pie-hole"
                                                        cx={pieCenterX}
                                                        cy={pieCenterY}
                                                        r="86"
                                                    />

                                                    <text
                                                        class="pie-center-value"
                                                        x={pieCenterX}
                                                        y={pieCenterY - 6}
                                                        text-anchor="middle"
                                                    >
                                                        {formatPieValue(pieTotal)}
                                                    </text>

                                                    <text
                                                        class="pie-center-label"
                                                        x={pieCenterX}
                                                        y={pieCenterY + 24}
                                                        text-anchor="middle"
                                                    >
                                                        total
                                                    </text>
                                                </svg>

                                                <div class="pie-chart-legend">
                                                    {#each pieData as item}
                                                        <div class="pie-legend-row">
                                                            <span class={`legend-dot ${item.colorClass}`}></span>

                                                            <div>
                                                                <strong>
                                                                    {item.name.length > 34 ? `${item.name.slice(0, 34)}...` : item.name}
                                                                </strong>

                                                                <p>
                                                                    {formatPieValue(item.value)}
                                                                    · {Math.round(item.percentage * 100)}%
                                                                </p>
                                                            </div>
                                                        </div>
                                                    {/each}
                                                </div>
                                            </div>
                                        {:else}
                                            <div class="chart-empty-state">
                                                No pie chart data available for the selected columns.
                                            </div>
                                        {/if}
                                    </div>
                                </div>
                            </div>
                        {/if}
                    </div>
                {/if}
            </section>
        </div>
    </section>
</div>

<style>
    /****************************************
    TABLE PAGE LAYOUT
    ****************************************/

    .table-page {
        min-height: calc(100vh - 80px);
    }

    .table-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
    }

    .table-actions {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    /****************************************
    TABLE ACTIONS
    ****************************************/

    .filter-status {
        height: 46px;
        display: inline-flex;
        align-items: center;
        padding: 0 18px;
        border-radius: 10px;
        background: #d1d5db;
        color: #374151;
        font-weight: 800;
        font-size: 0.9rem;
        transition: background 0.2s ease, color 0.2s ease;
    }

    .filter-status.filtered {
        background: #15803d;
        color: #ffffff;
    }

    .download-button {
        height: 46px;
        padding: 0 18px;
        border: none;
        border-radius: 12px;
        background: #07142c;
        color: white;
        font-size: 0.95rem;
        font-weight: 750;
        cursor: pointer;
    }

    .download-button:hover {
        background: #0f2550;
    }

    .mode-toggle {
        position: relative;
        display: flex;
        background: #07142c;
        border-radius: 14px;
        padding: 4px;
        width: 280px;
        height: 46px;
    }

    .mode-toggle button {
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

    .mode-toggle button.active {
        color: #07142c;
    }

    .slider {
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

    .slider.preview {
        transform: translateX(100%);
    }

    /****************************************
    RESULT TABLE
    ****************************************/

    .results {
        background: white;
        padding: 20px;
        border-radius: 16px;
        margin-bottom: 24px;
        overflow: hidden;
    }

    .results h3 {
        margin: 0 0 16px 0;
        font-size: 1rem;
        font-weight: 800;
    }

    .big-table {
        width: 100%;
        height: 430px;
        min-height: 430px;
        max-height: 430px;
        display: flex;
        flex-direction: column;
    }

    .table-scroll {
        flex: 1;
        overflow: auto;
        border: 1px solid #eef1f6;
        border-radius: 14px;
        background: white;
    }

    .data-table {
        width: 100%;
        min-width: 1100px;
        table-layout: fixed;
        border-collapse: separate;
        border-spacing: 0;
        font-size: 0.82rem;
    }

    .data-table th {
        position: sticky;
        top: 0;
        z-index: 3;
        background: #f8fafc;
        color: #07142c;
        font-weight: 850;
        text-align: left;
        vertical-align: bottom;
        padding: 14px 16px;
        border-bottom: 1px solid #dbe2ec;
        white-space: nowrap;
    }

    .data-table th.numeric-column {
        text-align: right;
    }

    .data-table th span {
        display: block;
        line-height: 1.25;
    }

    .data-table td {
        max-width: 260px;
        padding: 14px 16px;
        border-bottom: 1px solid #eef1f6;
        color: #1f2937;
        vertical-align: top;
        line-height: 1.45;
        background: white;
    }

    .data-table tbody tr:nth-child(even) td {
        background: #fbfcff;
    }

    .data-table tbody tr:hover td {
        background: #f4f6fb;
    }

    .data-table td.long-cell {
        min-width: 280px;
        max-width: 360px;
        color: #374151;
    }

    .data-table td.numeric-cell {
        text-align: right;
        font-variant-numeric: tabular-nums;
        color: #07142c;
        font-weight: 400;
    }

    .data-table th:first-child,
    .data-table td:first-child {
        position: sticky;
        left: 0;
        z-index: 2;
        max-width: 360px;
        min-width: 320px;
        box-shadow: 8px 0 12px rgba(7, 20, 44, 0.04);
    }

    .data-table th:first-child {
        z-index: 4;
        background: #f8fafc;
    }

    .data-table td:first-child {
        background: white;
    }

    .data-table tbody tr:nth-child(even) td:first-child {
        background: #fbfcff;
    }

    .data-table tbody tr:hover td:first-child {
        background: #f4f6fb;
    }

    .empty-state {
        color: #6b7280;
        padding: 24px 0;
    }

    .data-table td.city-cell {
        color: #07142c;
        font-weight: 400;
        text-decoration: none;
    }

    .city-cell-content {
        display: grid;
        grid-template-columns: 28px 1fr;
        align-items: center;
        gap: 8px;
    }

    .map-pin-button {
        width: 26px;
        height: 26px;
        border: 1px solid #dbe2ec;
        border-radius: 999px;
        background: #ffffff;
        cursor: pointer;
        font-size: 0.85rem;
        line-height: 1;
        display: grid;
        place-items: center;
        transition:
            background 0.15s ease,
            transform 0.15s ease,
            border-color 0.15s ease;
    }

    .map-pin-button:hover {
        background: #f4f6fb;
        border-color: #07142c;
        transform: translateY(-1px);
    }

    /****************************************
    VISUALIZATION AREA
    ****************************************/

    .visualization-section {
        margin-top: 28px;
    }

    .visualization-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 24px;
        margin-bottom: 18px;
    }

    .visualization-header h2 {
        margin: 0 0 6px 0;
        font-size: 1.4rem;
        font-weight: 800;
    }

    .visualization-header p {
        margin: 0;
        color: #6b7280;
    }

    /****************************************
    CHART ACCORDION
    ****************************************/

    .chart-accordion {
        display: flex;
        flex-direction: column;
        gap: 14px;
    }

    .chart-accordion-item {
        background: white;
        border-radius: 16px;
        overflow: hidden;
    }

    .chart-accordion-trigger {
        width: 100%;
        min-height: 82px;
        padding: 18px 22px;
        border: none;
        background: white;
        color: #07142c;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 20px;
        cursor: pointer;
        text-align: left;
    }

    .chart-accordion-trigger:hover,
    .chart-accordion-trigger.active {
        background: #f4f6fb;
    }

    .chart-accordion-trigger h3 {
        margin: 0 0 6px 0;
        font-size: 1.05rem;
        font-weight: 850;
    }

    .chart-accordion-trigger p {
        margin: 0;
        color: #6b7280;
        font-size: 0.9rem;
    }

    .chart-accordion-trigger span {
        width: 34px;
        height: 34px;
        border-radius: 10px;
        background: #07142c;
        color: white;
        display: grid;
        place-items: center;
        font-size: 1.4rem;
        font-weight: 800;
        flex-shrink: 0;
    }

    .chart-accordion-content {
        padding: 0 18px 18px 18px;
    }

    /****************************************
    CHART LOADING
    ****************************************/

    .chart-loading {
        height: 180px;
        border-radius: 14px;
        background: #f4f6fb;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        gap: 14px;
        color: #6b7280;
    }

    .chart-loading span {
        width: 34px;
        height: 34px;
        border: 4px solid #d8dee9;
        border-top-color: #07142c;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
    }

    .chart-loading p {
        margin: 0;
        font-weight: 700;
    }

    @keyframes spin {
        to {
            transform: rotate(360deg);
        }
    }

    /****************************************
    CHART PANEL
    ****************************************/

    .chart-panel {
        background: #ffffff;
        border: 1px solid #eef1f6;
        border-radius: 16px;
        padding: 20px;
        min-height: 300px;
    }

    .chart-panel-content {
        padding: 18px;
    }

    /****************************************
    CHART BUILDER
    ****************************************/

    .chart-builder-layout {
        display: grid;
        grid-template-columns: 240px minmax(0, 1fr);
        gap: 18px;
        align-items: stretch;
    }

    .chart-sidebar {
        border-radius: 16px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 16px;
        min-height: 100%;
    }

    .chart-sidebar-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
        margin-bottom: 10px;
    }

    .chart-sidebar h3 {
        margin: 0;
        color: #07142c;
        font-size: 1rem;
        font-weight: 850;
    }

    .chart-sidebar p {
        margin: 0 0 16px 0;
        color: #64748b;
        font-size: 0.85rem;
        line-height: 1.45;
    }

    .chart-controls {
        display: flex;
        flex-direction: column;
        gap: 14px;
    }

    .chart-controls label {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .chart-controls span {
        color: #64748b;
        font-size: 0.75rem;
        font-weight: 850;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .chart-controls select {
        height: 44px;
        width: 100%;
        border: 1px solid #dbe2ec;
        border-radius: 12px;
        padding: 0 12px;
        background: white;
        color: #07142c;
        font-weight: 800;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(7, 20, 44, 0.04);
    }

    .chart-controls select:hover {
        border-color: #94a3b8;
    }

    .chart-controls select:focus {
        outline: none;
        border-color: #07142c;
        box-shadow: 0 0 0 3px rgba(7, 20, 44, 0.12);
    }

    .axis-label {
        fill: #07142c;
        font-size: 1rem;
        font-weight: 800;
    }

    .axis-title {
        fill: #07142c;
        font-size: 1.05rem;
        font-weight: 900;
    }

    .legend-dot {
        width: 11px;
        height: 11px;
        border-radius: 999px;
        flex-shrink: 0;
        background: var(--series-color);
    }

    .series-0 {
        --series-color: #07142c;
    }

    .series-1 {
        --series-color: #2563eb;
    }

    .series-2 {
        --series-color: #059669;
    }

    .series-3 {
        --series-color: #dc2626;
    }

    .series-4 {
        --series-color: #7c3aed;
    }

    .series-5 {
        --series-color: #f59e0b;
    }

    .chart-empty-state {
        min-height: 420px;
        display: grid;
        place-items: center;
        color: #6b7280;
        font-weight: 750;
    }

    .chart-badge {
        padding: 6px 9px;
        border-radius: 999px;
        background: white;
        color: #07142c !important;
        border: 1px solid #dbe2ec;
        font-size: 0.74rem !important;
        font-weight: 850;
        white-space: nowrap;
    }

    /****************************************
    BOXPLOT PLACEHOLDER
    ****************************************/

    .boxplot-chart {
        min-width: 0;
        border-radius: 18px;
        background: #f8fafc;
        padding: 18px 22px 16px;
        border: 1px solid #d7dee8;
        overflow: hidden;
    }

    .boxplot-chart svg {
        width: 100%;
        height: 560px;
        display: block;
    }

    .boxplot-chart rect:first-child {
        fill: #ffffff;
    }

    .boxplot-grid-line {
        stroke: #d7dee8;
        stroke-width: 1.2;
    }

    .axis-line {
        stroke: #07142c;
        stroke-width: 2;
        stroke-linecap: round;
    }

    .boxplot-group-label {
        fill: #07142c;
        font-size: 0.9rem;
        font-weight: 850;
    }

    .boxplot-whisker,
    .boxplot-cap {
        stroke: #07142c;
        stroke-width: 3;
        stroke-linecap: round;
    }

    .boxplot-box {
        fill: #dbeafe;
        stroke: #2563eb;
        stroke-width: 3;
        filter: drop-shadow(0 4px 8px rgba(7, 20, 44, 0.12));
    }

    .boxplot-median {
        stroke: #dc2626;
        stroke-width: 4;
        stroke-linecap: round;
    }

    .boxplot-count {
        fill: #64748b;
        font-size: 0.82rem;
        font-weight: 800;
    }

    /****************************************
    BARPLOT
    ****************************************/

    .barplot-chart {
        min-width: 0;
        border-radius: 18px;
        background: #f8fafc;
        padding: 18px 22px 16px;
        border: 1px solid #d7dee8;
        overflow: hidden;
    }

    .barplot-chart svg {
        width: 100%;
        height: 560px;
        display: block;
    }

    .barplot-chart rect:first-child {
        fill: #ffffff;
    }

    .barplot-grid-line {
        stroke: #d7dee8;
        stroke-width: 1.2;
    }

    .barplot-group-label {
        fill: #07142c;
        font-size: 0.82rem;
        font-weight: 850;
    }

    .barplot-bar {
        fill: var(--series-color);
        filter: drop-shadow(0 4px 8px rgba(7, 20, 44, 0.12));
    }

    .barplot-value {
        fill: #64748b;
        font-size: 0.82rem;
        font-weight: 800;
    }

    .barplot-legend {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }

    .barplot-legend div {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #07142c;
        font-size: 0.82rem;
    }

    /****************************************
    PIE CHART PLACEHOLDER
    ****************************************/

    .pie-chart {
        min-width: 0;
        border-radius: 18px;
        background: #f8fafc;
        padding: 18px 22px 16px;
        border: 1px solid #d7dee8;
        overflow: hidden;
    }

    .pie-chart-layout {
        display: grid;
        grid-template-columns: minmax(0, 1.15fr) 340px;
        gap: 18px;
        align-items: center;
    }

    .pie-chart svg {
        width: 100%;
        height: 560px;
        display: block;
    }

    .pie-chart rect {
        fill: #ffffff;
    }

    .pie-slice {
        fill: var(--series-color);
        stroke: #ffffff;
        stroke-width: 5;
        cursor: pointer;
        transition:
            opacity 0.15s ease,
            transform 0.15s ease;
        transform-box: fill-box;
        transform-origin: center;
    }

    .pie-slice:hover {
        opacity: 0.86;
        transform: scale(1.015);
    }

    .pie-hole {
        fill: #ffffff;
        stroke: #e2e8f0;
        stroke-width: 2;
        filter: drop-shadow(0 4px 10px rgba(7, 20, 44, 0.10));
    }

    .pie-center-value {
        fill: #07142c;
        font-size: 2rem;
        font-weight: 950;
    }

    .pie-center-label {
        fill: #64748b;
        font-size: 0.95rem;
        font-weight: 850;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    .pie-chart-legend {
        border-radius: 16px;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 14px;
        max-height: 500px;
        overflow: auto;
    }

    .pie-legend-row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 11px 10px;
        border-radius: 12px;
    }

    .pie-legend-row:hover {
        background: #f4f6fb;
    }

    .pie-legend-row strong {
        display: block;
        color: #07142c;
        font-size: 0.88rem;
        font-weight: 850;
        line-height: 1.25;
    }

    .pie-legend-row p {
        margin: 3px 0 0 0;
        color: #64748b;
        font-size: 0.8rem;
        font-weight: 750;
    }

    /****************************************
    RESPONSIVE CHART AREA
    ****************************************/

    @media (max-width: 1100px) {
        .chart-builder-layout {
            grid-template-columns: 1fr;
        }

        .chart-sidebar {
            min-height: auto;
        }

        .chart-controls {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
    }

    @media (max-width: 900px) {
        .chart-controls {
            grid-template-columns: 1fr;
        }

        .pie-chart-layout {
            grid-template-columns: 1fr;
        }

        .pie-chart svg {
            height: 420px;
        }
    }
</style>
