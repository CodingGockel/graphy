<script lang="ts">
    import { onMount } from 'svelte';
    import { page } from '$app/state';

    // Referenz auf das HTML-Element, in das Leaflet die Karte rendert.
    let mapContainer: HTMLDivElement;
    let hasObservationData = $state(false);
    let observationCount = $state(0);

    // Wiederkehrende Farben für die Jahressegmente in den Kartenmarkern.
    const yearColors = ['#07142c', '#2563eb', '#059669', '#dc2626', '#7c3aed', '#f59e0b'];

    // Koordinaten und externe Links der Gärten, die auf der Karte angezeigt werden.
    const gardens = [
        {
            garden: 'Botanischer Garten Jena',
            city: 'Jena',
            country: 'Germany',
            lat: 50.9271,
            lng: 11.5892,
            url: 'https://www.botanischergarten.uni-jena.de/'
        },
        {
            garden: 'Botanic Garden and Botanical Museum Berlin',
            city: 'Berlin',
            country: 'Germany',
            lat: 52.4573,
            lng: 13.3053,
            url: 'https://www.bgbm.org/'
        },
        {
            garden: 'Alpinum Schatzalp',
            city: 'Davos',
            country: 'Switzerland',
            lat: 46.7985,
            lng: 9.8203,
            url: 'https://www.schatzalp.ch/'
        },
        {
            garden: 'Loki-Schmidt-Garten',
            city: 'Hamburg',
            country: 'Germany',
            lat: 53.5612,
            lng: 9.8603,
            url: 'https://www.loki-schmidt-garten.de/'
        },
        {
            garden: 'Botanischer Garten der Martin-Luther-Universität Halle-Wittenberg',
            city: 'Halle',
            country: 'Germany',
            lat: 51.4860,
            lng: 11.9618,
            url: 'https://www.botanik.uni-halle.de/botanischer_garten/'
        }
    ];

    // Behebt falsch kodierte Umlaute, die in einigen importierten Daten vorkommen.
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

    // Vereinheitlicht Namen für einen robusten Vergleich von Garten- und Stadtwerten.
    function normalize(value: any) {
        return cleanDisplayText(value).trim().toLowerCase();
    }

    // Bereinigt Werte, bevor sie als HTML in Leaflet-Popups eingesetzt werden.
    function escapeHtml(value: any) {
        return cleanDisplayText(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Die gefilterte Full Table wird von der Hauptseite im Browser abgelegt.
    function loadFullResults() {
        try {
            return JSON.parse(localStorage.getItem('fullResults') ?? '[]');
        } catch {
            return [];
        }
    }

    // Zählt Beobachtungen pro Garten und Jahr für die gestapelten Marker.
    function buildGardenObservations(rows: any[]) {
        const observations = new Map<string, Map<string, number>>();

        for (const row of rows) {
            const garden = gardens.find((item) =>
                normalize(item.garden) === normalize(row.garden) ||
                normalize(item.city) === normalize(row.city)
            );

            if (!garden) continue;

            const year = cleanDisplayText(row.year).trim() || 'Unknown year';
            const years = observations.get(garden.garden) ?? new Map<string, number>();

            years.set(year, (years.get(year) ?? 0) + 1);
            observations.set(garden.garden, years);
        }

        return observations;
    }

    // Erstellt den HTML-Inhalt, der beim Klick auf einen Marker angezeigt wird.
    function buildPopup(item: typeof gardens[number], years?: Map<string, number>) {
        const counts = years
            ? Array.from(years.entries())
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([year, count]) => `<li><span>${escapeHtml(year)}</span><strong>${count}</strong></li>`)
                .join('')
            : '';
        const total = years
            ? Array.from(years.values()).reduce((sum, count) => sum + count, 0)
            : 0;

        return `
            <div class="map-popup">
                <strong>${escapeHtml(item.garden)}</strong>
                <p>${escapeHtml(item.city)}, ${escapeHtml(item.country)}</p>
                ${years ? `
                    <p class="map-popup-total">${total} observation${total === 1 ? '' : 's'}</p>
                    <ul>${counts}</ul>
                ` : ''}
                <a href="${item.url}" target="_blank" rel="noreferrer">Open garden website</a>
            </div>
        `;
    }

    onMount(async () => {
        // Leaflet wird erst im Browser geladen, da es auf DOM-APIs zugreift.
        const L = await import('leaflet');
        await import('leaflet/dist/leaflet.css');
        const fullResults = loadFullResults();
        const gardenObservations = buildGardenObservations(fullResults);
        const years = Array.from(
            new Set(Array.from(gardenObservations.values()).flatMap((counts) => Array.from(counts.keys())))
        ).sort((a, b) => a.localeCompare(b));
        const maxTotal = Math.max(
            ...Array.from(gardenObservations.values()).map((counts) =>
                Array.from(counts.values()).reduce((sum, count) => sum + count, 0)
            ),
            1
        );

        hasObservationData = gardenObservations.size > 0;
        observationCount = Array.from(gardenObservations.values())
            .flatMap((counts) => Array.from(counts.values()))
            .reduce((sum, count) => sum + count, 0);

        const map = L.map(mapContainer).setView([51.1, 10.4], 5);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        // Alle Marker werden gruppiert, damit die Karte passend auf ihre Bounds zoomen kann.
        const markerGroup = L.featureGroup();
        const markers = new Map<string, any>();

        for (const item of gardens) {
            const counts = gardenObservations.get(item.garden);

            if (hasObservationData && !counts) continue;

            let marker;

            if (counts) {
                const total = Array.from(counts.values()).reduce((sum, count) => sum + count, 0);
                const height = Math.round(46 + (total / maxTotal) * 76);
                const segments = Array.from(counts.entries())
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([year, count]) => {
                        const color = yearColors[years.indexOf(year) % yearColors.length];
                        const segmentHeight = Math.max((count / total) * height, 5);

                        return `<span style="height:${segmentHeight}px;background:${color}" title="${escapeHtml(year)}: ${count}"></span>`;
                    })
                    .join('');
                const icon = L.divIcon({
                    className: 'observation-marker-wrapper',
                    html: `
                        <div class="observation-marker">
                            <strong>${total}</strong>
                            <div class="observation-stack">${segments}</div>
                        </div>
                    `,
                    iconSize: [42, height + 30],
                    iconAnchor: [21, height + 25],
                    popupAnchor: [0, -(height + 16)]
                });

                marker = L.marker([item.lat, item.lng], { icon }).bindPopup(buildPopup(item, counts));
            } else {
                marker = L.marker([item.lat, item.lng]).bindPopup(buildPopup(item));
            }

            const key = `${item.garden}|${item.city}|${item.country}`.toLowerCase();

            markers.set(key, marker);
            marker.addTo(markerGroup);
        }

        markerGroup.addTo(map);

        map.fitBounds(markerGroup.getBounds(), {
            padding: [70, 70]
        });

        // Die Legende wird nur angezeigt, wenn die Karte echte Beobachtungsdaten hat.
        if (hasObservationData) {
            const legend = new L.Control({ position: 'bottomright' });

            legend.onAdd = () => {
                const element = L.DomUtil.create('div', 'map-legend');
                element.innerHTML = `
                    <strong>Observation year</strong>
                    ${years.map((year, index) => `
                        <div>
                            <span style="background:${yearColors[index % yearColors.length]}"></span>
                            ${escapeHtml(year)}
                        </div>
                    `).join('')}
                `;
                return element;
            };

            legend.addTo(map);
        }

        // Ein Klick aus der Result Table kann Garten, Stadt oder Land per URL übergeben.
        const selectedGarden = page.url.searchParams.get('garden')?.toLowerCase();
        const selectedCity = page.url.searchParams.get('city')?.toLowerCase();
        const selectedCountry = page.url.searchParams.get('country')?.toLowerCase();

        const selectedItem = selectedGarden || selectedCity || selectedCountry
            ? gardens.find((item) =>
                (!selectedGarden || normalize(item.garden) === normalize(selectedGarden)) &&
                (!selectedCity || normalize(item.city) === normalize(selectedCity)) &&
                (!selectedCountry || normalize(item.country) === normalize(selectedCountry))
            )
            : undefined;

        if (selectedItem) {
            const key = `${selectedItem.garden}|${selectedItem.city}|${selectedItem.country}`.toLowerCase();
            const selectedMarker = markers.get(key);

            if (selectedMarker) {
                map.setView([selectedItem.lat, selectedItem.lng], 11);

                setTimeout(() => {
                    selectedMarker.openPopup();
                }, 250);
            }
        }
    });
</script>

<div class="map-page">
    <div class="map-header">
        <h1>Map</h1>
        <p>
            {hasObservationData
                ? `${observationCount} observations from the current full table, grouped by garden and year.`
                : 'Botanical gardens visualized on a world map.'}
        </p>
    </div>

    <section class="map-card">
        <div bind:this={mapContainer} class="map-container"></div>
    </section>
</div>

<style>
    .map-page {
        min-height: calc(100vh - 80px);
    }

    .map-header {
        margin-bottom: 22px;
    }

    .map-header h1 {
        margin: 0 0 6px 0;
        color: #07142c;
        font-size: 1.8rem;
        font-weight: 900;
    }

    .map-header p {
        margin: 0;
        color: #64748b;
        font-weight: 650;
    }

    .map-card {
        background: white;
        border-radius: 18px;
        padding: 18px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 8px 24px rgba(7, 20, 44, 0.06);
    }

    .map-container {
        width: 100%;
        height: 680px;
        border-radius: 16px;
        overflow: hidden;
        border: 1px solid #d7dee8;
    }

    :global(.leaflet-popup-content-wrapper) {
        border-radius: 14px;
        box-shadow: 0 12px 30px rgba(7, 20, 44, 0.18);
    }

    :global(.leaflet-popup-content) {
        margin: 14px 16px;
        color: #07142c;
        font-family: inherit;
    }

    :global(.map-popup strong) {
        display: block;
        margin-bottom: 6px;
        font-size: 0.95rem;
        font-weight: 900;
    }

    :global(.map-popup p) {
        margin: 0 0 10px 0;
        color: #64748b;
        font-weight: 700;
    }

    :global(.map-popup-total) {
        color: #07142c !important;
        font-weight: 900 !important;
    }

    :global(.map-popup ul) {
        margin: 0 0 12px 0;
        padding: 0;
        list-style: none;
    }

    :global(.map-popup li) {
        display: flex;
        justify-content: space-between;
        gap: 20px;
        padding: 3px 0;
        color: #475569;
    }

    :global(.map-popup a) {
        color: #2563eb;
        font-weight: 850;
        text-decoration: none;
    }

    :global(.map-popup a:hover) {
        text-decoration: underline;
    }

    :global(.observation-marker-wrapper) {
        background: transparent;
        border: none;
    }

    :global(.observation-marker) {
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: flex-end;
        filter: drop-shadow(0 4px 5px rgba(7, 20, 44, 0.28));
    }

    :global(.observation-marker > strong) {
        min-width: 24px;
        margin-bottom: 4px;
        padding: 2px 6px;
        border-radius: 999px;
        background: #ffffff;
        color: #07142c;
        font-size: 0.72rem;
        font-weight: 950;
        line-height: 1.2;
        text-align: center;
    }

    :global(.observation-stack) {
        width: 30px;
        display: flex;
        flex-direction: column-reverse;
        overflow: hidden;
        border: 2px solid #ffffff;
        border-radius: 7px 7px 3px 3px;
        background: #ffffff;
    }

    :global(.observation-stack span) {
        display: block;
        width: 100%;
        min-height: 5px;
    }

    :global(.map-legend) {
        min-width: 128px;
        padding: 10px 12px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.96);
        color: #07142c;
        box-shadow: 0 6px 18px rgba(7, 20, 44, 0.18);
        font-family: inherit;
    }

    :global(.map-legend > strong) {
        display: block;
        margin-bottom: 7px;
        font-size: 0.78rem;
        font-weight: 900;
    }

    :global(.map-legend div) {
        display: flex;
        align-items: center;
        gap: 7px;
        margin-top: 4px;
        font-size: 0.74rem;
        font-weight: 750;
    }

    :global(.map-legend div span) {
        width: 10px;
        height: 10px;
        border-radius: 999px;
    }
</style>
