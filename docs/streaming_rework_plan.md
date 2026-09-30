# Backend-Rework: Streaming + neue Sessions

Plan für den Umbau des Backends von der heutigen Einmal-Response auf einen
Event-Stream, inklusive Neuaufbau der Session-/Chat-Persistenz.

**Ausgangslage:** kein Live-System, keine Nutzdaten, kein Frontend, das die alte API
konsumiert (das bestehende wird ersetzt). Es muss also **nichts** migriert und nichts
rückwärtskompatibel gehalten werden.

---

## 1. Vorab-Entscheidungen

**Kein `/api/v2`.** Ein Versions-Namespace hat nur Sinn, wenn zwei Versionen
nebeneinander leben. Da die alte API ersatzlos verschwindet, bleibt alles unter
`/api/v1` und wird an Ort und Stelle ersetzt. Ein `v2`-Namespace ohne `v1` dahinter
wäre nur eine Lüge im Pfad.

**Kein Alembic, kein Migrationspfad.** `init_db()` nutzt `Base.metadata.create_all`
(`db/database.py:15`), was bestehende Tabellen **nicht** ändert. Neue Spalten würden
auf einer existierenden DB stillschweigend nicht entstehen. Da keine Daten schützenswert
sind, ist der Weg: **Tabellen wegwerfen und neu anlegen.**

```bash
docker compose down -v      # entfernt das db_data-Volume
```

Alembic kann später nachgezogen werden, sobald es echte Nutzdaten gibt. Vorher ist es
Ballast.

**Der Agenten-Loop selbst bleibt inhaltlich unangetastet.** Tool-Definitionen, Prompts,
`resolve_entity`, das Retry-auf-kaputte-Query, `ensure_limit`, `_truncate_results` — alles
fachlich erprobt und wird nur umgestülpt, nicht neu erfunden. Umgebaut wird die
*Kontrollstruktur* (Rückgabewert → Generator), nicht die Logik.

---

## 2. Zielarchitektur

Der Kern des Umbaus ist eine einzige Formänderung:

```python
# vorher
async def process(self, request: ChatRequest) -> ChatResponse

# nachher
async def run(self, session_id, message) -> AsyncIterator[ChatEvent]
```

Die Schleife in `chat_service.py` yielded an den Stellen, an denen sie heute schon
loggt — `logger.info` bei Zeile 191 (Tool gewählt), 200 (Query), 228 (Entity-Resolution)
sind wörtlich die Emit-Punkte. Der Router konsumiert den Generator und serialisiert ihn
nach SSE.

```
Router (SSE)  ──konsumiert──▶  ChatService.run()  ──yielded──▶  ChatEvent
                                      │
                                      ├─▶ LLMService     (Tool-Loop + Antwort)
                                      ├─▶ SparqlService  (GraphDB)
                                      ├─▶ LuceneService  (Entity-Resolution)
                                      └─▶ ChatRepository (inkrementelle Persistenz)
```

---

## 3. Event-Contract (SSE)

Transport: `text/event-stream` über `StreamingResponse` (Starlette). **Keine neue
Dependency nötig.** Im Frontend nicht per `EventSource` lesbar (das kann nur GET) —
also `fetch()` + `ReadableStream`.

```
event: session
data: {"session_id":"…","message_id":"…","title":null}

event: session_title
data: {"session_id":"…","title":"Blütezeit von Tulipa sylvestris"}

event: step_started
data: {"step_id":"…","ordinal":1,"kind":"resolve_entity","args":{"term":"Schneeglöckchen"}}

event: step_finished
data: {"step_id":"…","ok":true,"summary":"3 Kandidaten gefunden","duration_ms":412}

event: thinking
data: {"delta":"Der Nutzer meint vermutlich …"}

event: answer
data: {"delta":"Tulipa sylvestris blühte "}

event: done
data: {"message_id":"…","status":"complete","row_count":42}

event: error
data: {"kind":"llm_unavailable","message":"…","recoverable":false}

: ping
```

**`kind`-Werte für Steps:** `resolve_entity`, `sparql_query`, `previous_results`,
`papers`, `clarification`.

**Bewusste Entscheidung — Step-Payloads werden nicht gestreamt.** `step_finished`
trägt nur `summary` und Metadaten, nicht das SPARQL-Ergebnis. Grund: das Trace-Panel ist
im Frontend standardmäßig zugeklappt, die Daten werden also meist gar nicht angesehen.
Ein Turn mit vier Queries würde sonst hunderte KB durch den Stream schieben, die niemand
liest. Stattdessen lädt das Panel beim Aufklappen nach:

```
GET /api/v1/steps/{step_id}/result
```

Das hält den Stream leicht und passt exakt zum geplanten UI-Verhalten.

**Heartbeat:** alle 15 s eine SSE-Kommentarzeile (`: ping`), damit Proxies die
Verbindung während langer LLM-Denkpausen nicht kappen.

---

## 4. Datenmodell

```sql
sessions
  id            uuid        PK
  title         text        NULL          -- initial aus erster Nutzerfrage
  created_at    timestamptz
  updated_at    timestamptz               -- für die Sortierung der Sidebar

messages
  id            uuid        PK            -- UUID statt int: stabil für den Client
  session_id    uuid        FK → sessions ON DELETE CASCADE
  turn          int                       -- explizit, nicht aus der Reihenfolge geraten
  role          text                      -- user | assistant
  content       text
  thinking      text        NULL          -- nur assistant; nur wenn PERSIST_THINKING
  status        text                      -- complete | aborted | error
  created_at    timestamptz

steps
  id            uuid        PK
  message_id    uuid        FK → messages ON DELETE CASCADE
  ordinal       int
  kind          text
  args          jsonb
  ok            boolean
  summary       text
  result        jsonb       NULL          -- volle SPARQL-Antwort, lazy geladen
  error         text        NULL
  duration_ms   int
  created_at    timestamptz

INDEX messages (session_id, turn)
INDEX steps    (message_id, ordinal)
INDEX sessions (updated_at DESC)
```

### Warum eine `steps`-Tabelle und keine JSONB-Spalte auf `messages`

Das ist die zentrale Korrektur am alten Schema. Heute hat `Message` **je eine** Spalte
`sparql_query` und `sparql_results` (`db/models.py:35-36`), während der Agenten-Loop
**N Queries pro Turn** ausführt. `chat_service.py` hält nur `last_query`/`last_results`
und schreibt genau die weg — der Trace geht also nicht erst in der Response verloren,
sondern schon bei der Persistierung. Ohne diese Änderung wäre das aufklappbare
Trace-Panel nach jedem Reload leer.

Eine eigene Tabelle statt einer JSONB-Spalte, weil:

- **Steps werden während des Streams einzeln angehängt.** Bricht die Verbindung ab, ist
  der Trace bis dahin trotzdem persistiert. Eine JSONB-Spalte bräuchte pro Step ein
  Read-Modify-Write der gesamten Liste.
- Die Ordinal-Sortierung ist natürlich, statt auf Array-Reihenfolge zu vertrauen.
- `steps.result` kann einzeln nachgeladen werden, ohne den ganzen Turn zu lesen —
  genau der Zugriff, den `GET /steps/{id}/result` braucht.

Postgres TOASTet und komprimiert große JSONB-Werte automatisch; die Ergebnisgrößen
hier sind unkritisch.

### Titel — vom LLM, aber nebenläufig

Der Titel wird beim ersten Request einer Session per LLM aus der Nutzerfrage erzeugt
(kurzer Prompt, wenige Output-Tokens). Ausgelöst wird das genau dann, wenn
`sessions.title IS NULL` — also einmal pro Session, nicht pro Turn.

**Der Call darf den Stream nicht aufhalten.** Würde man ihn vor der Schleife abwarten,
verzögert er das `session`-Event — und genau das braucht das Frontend sofort, weil die
Session-ID daran hängt. Deshalb:

1. `session`-Event geht unmittelbar raus, mit `title: null`.
2. Der Titel-Call startet parallel als `asyncio.Task`.
3. Zwischen zwei Schleifendurchläufen wird `task.done()` geprüft. Ist er fertig, wird der
   Titel über die **ohnehin offene** DB-Session der Generator-Coroutine persistiert und
   als `session_title`-Event nachgeschoben.
4. Läuft der Task am Ende noch, wird er mit kurzem Timeout abgewartet.

Der Umweg über `task.done()` statt eines zweiten nebenläufigen DB-Zugriffs ist Absicht:
eine SQLAlchemy `AsyncSession` verträgt keine parallele Nutzung. So bleibt alles auf einem
Strang, und es braucht keine zweite Session.

**Fehler dürfen den Chat nie umbringen.** Schlägt der Titel-Call fehl oder läuft er in
den Timeout, fällt der Titel auf die gekürzte Nutzerfrage zurück (erste ~60 Zeichen an
Wortgrenze). Ein kaputter Titel-Call ist ein kosmetisches Problem, kein Fehlerfall des
Turns — er wird geloggt und sonst geschluckt.

Umbenennen per `PATCH /sessions/{id}`; ein manuell gesetzter Titel wird nie überschrieben.

Der Prompt liegt statisch unter `src/resources/prompts/title_prompt.md` und wird über
`load_prompt()` geladen. Er läuft **nicht** durch `build_prompt.py` — er ist
KG-unabhängig und braucht kein Schema.

### Neue Config-Felder

In `util/config.py` (`Settings`):

```python
persist_thinking: bool = True          # <think>-Inhalte in die DB schreiben
generate_session_titles: bool = True   # aus: Titel = gekürzte erste Frage
session_title_prompt_path: str = "src/resources/prompts/title_prompt.md"
session_title_timeout: float = 5.0     # danach greift der Fallback
```

`persist_thinking = False` schaltet nur die **Persistenz** ab — die `thinking`-Events
gehen weiterhin live über den Stream, sie werden nur nicht in `messages.thinking`
geschrieben. Das ist die sinnvolle Trennung: live mitlesen will man fast immer,
archivieren nicht unbedingt.

---

## 5. Neue API-Oberfläche

| Methode | Pfad | Zweck |
|---|---|---|
| `POST` | `/api/v1/chat` | **SSE-Stream.** `session_id` optional; fehlt sie, wird eine Session angelegt und im `session`-Event zurückgegeben |
| `GET` | `/api/v1/sessions` | Liste für die Sidebar (id, title, updated_at, message_count) |
| `GET` | `/api/v1/sessions/{id}` | Vollständiger Verlauf: Messages + Steps (ohne `result`-Payload) |
| `PATCH` | `/api/v1/sessions/{id}` | Titel ändern |
| `DELETE` | `/api/v1/sessions/{id}` | Session löschen (Cascade) |
| `GET` | `/api/v1/steps/{id}/result` | Volles Ergebnis eines Steps, lazy |
| `GET` | `/api/v1/table` | unverändert (heute `/chat/full_table`) |
| `GET` | `/api/v1/models` | unverändert (heute `/chat/models`) |
| `GET` | `/api/v1/health` | unverändert |

**Entfällt ersatzlos:** `PUT /session/{id}/history`. Das war eine Import/Export-Operation
in Chat-Kleidung; die Session-Liste macht sie überflüssig.

`POST /chat` mit optionaler `session_id` (statt streng REST-konform
`POST /sessions/{id}/messages`) spart dem Frontend den Doppel-Request beim allerersten
Turn. Der `session`-Event im ersten Frame liefert die ID.

---

## 6. Vier Fallstricke, die den Umbau sonst kosten

Diese Punkte sind der eigentliche Grund für einen geschriebenen Plan — jeder einzelne
davon fällt sonst erst beim Debuggen auf.

### 6.1 Die DB-Session ist beim Streamen bereits geschlossen

`get_db_session` (`api/dependencies.py:27`) liefert die Session per `yield` aus einem
`async with`. FastAPI räumt yield-Dependencies **auf, bevor der Response-Body gesendet
wird**. Bei einer `StreamingResponse` läuft der Generator aber *danach* — die Session
wäre also beim ersten Schreibversuch im Stream schon zu.

**Lösung:** die Streaming-Route bekommt den **Sessionmaker**, nicht die Session, und
öffnet die DB-Session *innerhalb* des Generators:

```python
async def event_stream():
    async with sessionmaker() as db:
        repo = ChatRepository(db)
        async for event in service.run(..., repo=repo):
            yield encode_sse(event)
```

Damit muss auch `get_chat_service` umgebaut werden: `ChatService` darf die Repository
nicht mehr im Konstruktor festhalten, sondern bekommt sie pro Lauf übergeben.

### 6.2 Fehler können nicht mehr über HTTP-Status laufen

`register_exception_handlers` (`api/exception_handlers.py`) mappt Domain-Exceptions auf
502/503. Sobald der Stream läuft, ist der Status-Code aber längst als 200 gesendet — die
Handler greifen für die Chat-Route nicht mehr.

**Lösung:** die Streaming-Route fängt Domain-Exceptions selbst ab und sendet ein
`event: error` im Stream. Nur Fehler *vor* dem ersten Byte (z. B. Session nicht gefunden)
gehen weiterhin als HTTP-Status raus. Für alle übrigen Routen (health, sessions, table)
bleiben die Handler unverändert in Kraft.

### 6.3 Tool-Calls dürfen nicht aus Deltas geparst werden

`_recover_tool_call_from_content` (`llm_service.py:122`) ist hier tragend, weil nicht alle
Blablador-Modelle strukturierte Tool-Calls liefern — die Funktion arbeitet mit Regex über
den **vollständigen** Text und kann auf Fragmenten nicht funktionieren.

**Prinzip, das festgeschrieben werden sollte: streamen fürs Anzeigen, parsen auf dem
Puffer.** `stream=True` setzen, Deltas live als `thinking`-Events rausgeben, die komplette
Message aber weiterhin sammeln und die bestehende Parse-Logik unverändert auf dem fertigen
Text laufen lassen. Streaming wird damit rein additiv und kann die Tool-Erkennung nicht
beschädigen. Gleiches gilt für das Zusammensetzen fragmentierter `tool_calls`-Deltas
(nach `index` akkumulieren).

### 6.4 `<think>`-Blöcke brauchen einen inkrementellen Splitter

`strip_think()` (`util/sparql_utils.py:51`) braucht den ganzen Text und ist für Deltas
unbrauchbar. Nötig ist ein kleiner Zustandsautomat, der mitführt, ob man sich gerade
innerhalb eines `<think>`-Blocks befindet, und die Deltas entsprechend auf `thinking`
oder `answer` routet. Randfall: das Tag kann über eine Delta-Grenze zerteilt ankommen
(`<thi` | `nk>`) — der Splitter muss ein unvollständiges Tag-Präfix zurückhalten.

### Bonus: Client-Abbruch soll den Loop stoppen

Bricht der Browser ab, läuft der Agenten-Loop sonst weiter und verbrennt LLM-Kontingent.
Zwischen den Iterationen `await request.is_disconnected()` prüfen und sauber abbrechen —
die bereits geschriebenen Steps bleiben persistiert, die Message wird als
`status = "aborted"` markiert.

---

## 7. Umbauschritte

Reihenfolge so gewählt, dass nach jedem Schritt ein lauffähiger Zustand existiert.

**P0 — Datenschicht neu**
`db/models.py` (drei Tabellen), `db/repository.py` (neu geschnitten: `create_session`,
`list_sessions`, `get_session`, `rename_session`, `delete_session`, `add_message`,
`append_step`, `finish_message`, `get_step_result`). Volume wegwerfen.

**P1 — Event-Typen**
`models/events.py`: `ChatEvent` als Pydantic-Union über die Event-Typen aus Abschnitt 3.
Reine Typdefinitionen, hängt an nichts.

**P2 — `ChatService` → Generator**
`process()` wird zu `run()`. Der Schleifenrumpf bleibt inhaltlich gleich, `return`-Pfade
werden zu `yield` + `return`. Repository wird pro Lauf übergeben statt im Konstruktor
gehalten. Steps werden beim Auftreten persistiert. **Der riskanteste Schritt** —
danach zuerst mit einem simplen Konsumenten prüfen, dass die Eventfolge stimmt.

**P3 — SSE-Route**
`api/v1/chat.py` neu: `StreamingResponse`, SSE-Encoding, Heartbeat, In-Band-Errors,
Disconnect-Check, Sessionmaker-statt-Session (6.1). `dependencies.py` entsprechend
anpassen.

**P4 — Session-Router**
`api/v1/sessions.py`: Liste, Detail, Rename, Delete, `steps/{id}/result`.
`session_service.py` neu; das alte `HistoryUpload`-Schema fliegt raus.

**P5 — Titelgenerierung**
`title_prompt.md`, `LLMService.generate_title()`, Task-Handling im Generator, neue
Config-Felder. Klein und isoliert, hängt nur an P2/P3.

**P6 — Token-Streaming**
`generate_answer()` auf `stream=True` (einfach, kein Tool-Parsing im Spiel), danach
`chat_with_tools()` nach dem Prinzip aus 6.3. Bewusst zuletzt: unabhängig vom Rest und
im Zweifel verzichtbar.

**P7 — Tests**
Siehe unten.

Deployment (`nginx.conf`, Compose) bleibt in diesem Umbau bewusst unangetastet — siehe
Abschnitt 9.

---

## 8. Tests

Der Umbau invalidiert `test_chat_service.py`, `test_session_service.py`,
`test_chat_router.py` und `test_session_router.py`. Unverändert bleiben können
`test_sparql_service.py`, `test_lucene_service.py`, `test_health_service.py`,
`test_sparql_utils.py`, `test_llm_utils.py`.

Neu abzudecken:

- **Eventfolge** — `run()` mit gemocktem LLM/SPARQL durchlaufen lassen und die Sequenz
  gegen Erwartungen prüfen. Ersetzt die alten `process()`-Tests weitgehend 1:1.
- **SSE-Encoding** — Framing, Heartbeat, `error`-Event bei geworfener Domain-Exception.
- **`<think>`-Splitter** — inklusive des über Delta-Grenzen zerteilten Tags (6.4).
- **Tool-Call-Recovery auf gepufferten Streams** — dass 6.3 tatsächlich hält.
- **Steps-Persistenz** — dass ein abgebrochener Lauf die bis dahin erzeugten Steps behält.
- **Titel-Fallback** — schlagender oder hängender Titel-Call darf den Turn nicht stören;
  `generate_session_titles = False` liefert die gekürzte Frage.
- **`persist_thinking`** — bei `False` kommen `thinking`-Events weiterhin im Stream an,
  `messages.thinking` bleibt aber leer.

---

## 9. Nicht-Ziele

Bewusst außen vor, um den Umbau endlich zu halten:

- **Deployment.** nginx-Config und Compose-Stack werden später ohnehin komplett neu
  gebaut und bleiben hier unangetastet. **Eine Sache muss dabei aber gesetzt sein, sonst
  ist das Streaming in Produktion unsichtbar:** nginx puffert Responses per Default, sammelt
  die SSE-Events und liefert sie am Ende auf einen Schlag aus. Lokal gegen uvicorn läuft
  alles perfekt — der klassische „läuft bei mir"-Fehler. Nötig sind dann
  `proxy_buffering off`, `proxy_cache off`, ein großzügiges `proxy_read_timeout`, und
  `text/event-stream` darf **nicht** in `gzip_types`. Ergänzend kann das Backend
  `X-Accel-Buffering: no` als Response-Header senden, was auch vorgelagerte Proxies
  abdeckt — das ist die einzige Zeile davon, die schon jetzt ins Backend gehört.
- **Stream-Resume nach Reload.** Wer während eines laufenden Turns neu lädt, verliert die
  Live-Ausgabe; der persistierte Stand ist danach lesbar. Die `steps`-Tabelle macht ein
  echtes Resume später möglich, ohne dass jetzt etwas dafür getan werden muss.
- **Alembic.** Erst wenn es Daten gibt, die einen Migrationspfad verdienen.
- **Auth / Nutzerbindung von Sessions.** Sessions bleiben unauthentifiziert; wer die ID
  kennt, sieht die Session. Das ist der Status quo, ändert sich durch den Umbau nicht —
  ist aber der Punkt, an dem ein öffentliches Deployment eine Entscheidung braucht.

---

## 10. Nebenbefunde (nicht Teil des Umbaus)

Beim Durchlesen aufgefallen, unabhängig vom Streaming — Aufwand jeweils Minuten:

- `validate_query()` (`util/sparql_utils.py:83`) prüft auf Teilstrings ohne Wortgrenzen.
  Eine legitime Query mit einer Variable `?insertion` oder einem Label „Constructa" wird
  abgelehnt. Wortgrenzen-Regex behebt das.
- `SparqlService.aclose()` (`sparql_service.py:109`) schließt den **geteilten**
  App-weiten httpx-Client. Wird aktuell nirgends aufgerufen; ein versehentlicher Aufruf
  würde den Client für alle Requests dichtmachen. Kandidat zum Löschen.
- Der httpx-Client hat `timeout=10.0` (`main.py:31`) und `SparqlService` nochmal
  separat 10 s. Für große Aggregat-Queries knapp — beim Streaming fällt es stärker auf,
  weil der Nutzer live zusieht.
