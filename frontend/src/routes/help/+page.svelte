<h1 class="datahub-title">Help</h1>

<section class="help-page">
    <!-- Einführung in die Nutzung der Anwendung -->
    <div class="help-hero">
        <h2>How to use DataExplorer</h2>
        <p>
            DataExplorer helps you ask natural language questions about phenological observation data
            and turns them into SPARQL queries.
        </p>
    </div>

    <!-- Schrittweise Anleitung für neue Nutzer -->
    <div class="help-grid">
        <section class="help-card">
            <span class="step">1</span>
            <h3>Ask a question</h3>
            <p>
                Type a question into the chat, for example:
                <strong>“Which botanical gardens are in the database?”</strong>
            </p>
        </section>

        <section class="help-card">
            <span class="step">2</span>
            <h3>Review the answer</h3>
            <p>
                The AI summarizes the result and explains what was found in the database.
            </p>
        </section>

        <section class="help-card">
            <span class="step">3</span>
            <h3>Check the table preview</h3>
            <p>
                The preview table shows the first results returned by the generated SPARQL query.
            </p>
        </section>

        <section class="help-card">
            <span class="step">4</span>
            <h3>Open the full table</h3>
            <p>
                Click <strong>Show Table</strong> to inspect the results in a larger table view.
            </p>
        </section>
    </div>

    <!-- Beispiel-Fragen für den AI Chat -->
    <section class="help-section">
        <h2>Useful example questions</h2>

        <div class="example-list">
            <button>Which botanical gardens are in the database?</button>
            <button>In which gardens was Achillea millefolium observed?</button>
            <button>Which plant species are available in Jena?</button>
            <button>How did flowering duration of Achillea millefolium change from 2019 to 2024?</button>
        </div>
    </section>

    <!-- Übersicht der wichtigsten Funktionen -->
    <section class="help-section">
        <h2>Main features</h2>

        <div class="feature-list">
            <div>
                <h3>Generated Query</h3>
                <p>Shows the SPARQL query created by the AI.</p>
            </div>

            <div>
                <h3>Download CSV</h3>
                <p>Exports the currently displayed table as a CSV file.</p>
            </div>

            <div>
                <h3>Result Table</h3>
                <p>Displays query results in a larger table view with switchable modes.</p>
            </div>

            <div>
                <h3>Other Settings</h3>
                <p>Configure display behavior, export format, language placeholders and AI mode.</p>
            </div>
        </div>
    </section>

    <!-- Kurze Tipps für bessere Suchanfragen -->
    <section class="help-section">
        <h2>Tips</h2>

        <ul class="tips-list">
            <li>Use specific plant names, garden names or years for better results.</li>
            <li>If the AI asks a follow-up question, add the missing information.</li>
            <li>Open “Generated Query” if you want to understand what the AI searched for.</li>
            <li>Use “Download CSV” if you want to work with the results in Excel or another tool.</li>
        </ul>
    </section>
</section>

<style>
    /****************************************
    HELP PAGE LAYOUT
    ****************************************/

    .help-page {
        display: flex;
        flex-direction: column;
        gap: 28px;
        max-width: 1200px;
        margin-top: 28px;
    }

    /****************************************
    HELP HERO
    ****************************************/

    .help-hero {
        background: white;
        padding: 28px;
        border-radius: 18px;
    }

    .help-hero h2 {
        margin: 0 0 10px 0;
        font-size: 1.8rem;
        font-weight: 800;
    }

    .help-hero p {
        margin: 0;
        color: #6b7280;
        max-width: 760px;
        line-height: 1.6;
    }

    /****************************************
    HELP CARDS
    ****************************************/

    .help-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 18px;
    }

    .help-card,
    .help-section {
        background: white;
        padding: 22px;
        border-radius: 18px;
    }

    .help-card h3,
    .help-section h2 {
        margin: 0 0 10px 0;
        font-weight: 800;
    }

    .help-card p,
    .help-section p {
        color: #6b7280;
        line-height: 1.5;
    }

    .step {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        background: #07142c;
        color: white;
        border-radius: 999px;
        font-weight: 800;
        margin-bottom: 14px;
    }

    /****************************************
    EXAMPLE QUESTIONS
    ****************************************/

    .example-list {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
    }

    .example-list button {
        border: none;
        background: #07142c;
        color: white;
        padding: 10px 14px;
        border-radius: 12px;
        font-size: 0.9rem;
        font-weight: 750;
        cursor: pointer;
    }

    .example-list button:hover {
        background: #0f2550;
    }

    /****************************************
    FEATURE LIST
    ****************************************/

    .feature-list {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 20px;
    }

    .feature-list h3 {
        margin: 0 0 6px 0;
        font-weight: 750;
    }

    /****************************************
    TIPS
    ****************************************/

    .tips-list {
        margin: 0;
        padding-left: 20px;
        color: #4b5563;
        line-height: 1.8;
    }
</style>
