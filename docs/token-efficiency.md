# Efficienza dei token â€” implementazione e rationale

Documentazione dell'architettura a livelli adottata in SearchForAlpha Lab per ridurre il consumo di token da parte degli agenti AI (Cursor, Claude Code, GitHub Copilot, OpenClaw), senza perdere le istruzioni operative necessarie.

---

## Il problema

Ogni sessione con un agente AI carica automaticamente file di contesto dal repository. Prima di questa implementazione, **~400+ righe** venivano iniettate a ogni turno:

| File | Righe (prima) | Contenuto |
|------|---------------|-----------|
| `CLAUDE.md` | ~108 | Architettura completa, convenzioni, esempi |
| `AGENTS.md` | ~245 | Orchestrazione OpenClaw / `sfa` CLI |
| `.cursorrules` | ~34 | Routing modelli |
| `PROJECT_INDEX.md` | ~106 | Indice moduli (sovrapposto a `CLAUDE.md`) |

**Conseguenze:**

1. **Duplicazione** â€” la stessa informazione (es. albero dei moduli, naming dei segnali) compariva in piÃ¹ file.
2. **Contesto irrilevante** â€” le regole OpenClaw per la ricerca quantitativa venivano caricate anche durante modifiche al dashboard Dash o ai segnali Python.
3. **Output shell verbose** â€” `git diff`, `pytest -v`, `sfa ... --json` producevano migliaia di token di output a ogni comando.

### Evidenza esterna

Studi recenti (ETH Zurich, *Evaluating AGENTS.md*, 2026; ricerche su *tiered injection*) indicano che:

- I file di contesto **non inferibili dal codice** aiutano (~4% successo in piÃ¹).
- Ogni token in un file always-on ha un **costo fisso per sessione** (~19â€“20% overhead se il file Ã¨ troppo lungo).
- Le regole **scoped** (caricate solo quando servono) riducono il contesto del 60â€“80% mantenendo l'accuratezza.
- Le istruzioni generate da LLM spesso **aumentano i costi del 20%+** senza migliorare i risultati â€” meglio regole umane, minimali, specifiche.

---

## La soluzione: tre leve

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  LIVELLO 1 â€” Always-on (poche righe, solo l'essenziale)     â”‚
â”‚  CLAUDE.md Â· token-efficiency.mdc Â· model-routing.mdc       â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                              â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  LIVELLO 2 â€” On-demand (.cursor/rules/*.mdc per glob)       â”‚
â”‚  sfa-python Â· dash-callbacks Â· sfa-cli-research             â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                              â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  LIVELLO 3 â€” Ricerca OpenClaw (lettura esplicita a sessione)â”‚
â”‚  AGENTS.md (slim) Â· docs/openclaw-research.md Â· RESEARCH.md â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                              â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  LIVELLO 0 â€” Output shell (rtk hook, trasparente)           â”‚
â”‚  .cursor/hooks.json Â· .github/copilot-instructions.md       â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## Livello 1 â€” Contesto always-on ridotto

### `CLAUDE.md` (~18 righe)

Prima conteneva l'intero albero dell'architettura, tutte le convenzioni e snippet di codice. Ora include solo:

- Comandi di avvio (`main.py`, pytest)
- Puntatori a indice e regole scoped
- Convenzioni **non ovvie** (naming segnali, `config_loader`, callback Dash)

**Rationale:** tutto ciÃ² che Ã¨ deducibile leggendo il codice o l'indice non deve stare in un file always-on.

### `.cursor/rules/token-efficiency.mdc`

Regola always-on con due discipline:

1. **Shell** â€” prefissare con `rtk` (vedi Livello 0).
2. **Contesto** â€” navigare via indice, leggere file grandi a chunk, citare con `startLine:endLine:path` invece di incollare file interi.

### `.cursor/rules/model-routing.mdc`

Policy Kimi-first / escalation Sonnet-Opus, migrata da `.cursorrules` (eliminato). Una sola responsabilitÃ  per file.

---

## Livello 2 â€” Regole scoped (on-demand)

Cursor carica i file `.mdc` in `.cursor/rules/` **solo quando** il glob corrisponde ai file aperti o modificati:

| Regola | Glob | Contenuto |
|--------|------|-----------|
| `sfa-python.mdc` | `lib/**/*.py` | Naming segnali, checklist nuovo indicatore, config, test |
| `dash-callbacks.mdc` | `lib/dash/**` | Pattern callback, `integrated_dashboard.py`, `chart_payload.py` |
| `sfa-cli-research.mdc` | `lib/cli/**` | Contratti JSON, `contracts.py`, test CLI |

**Rationale:** un agente che modifica `lib/dash/callbacks/fundamentals.py` non ha bisogno delle regole OpenClaw per `sfa promote`. Un agente che edita `lib/signals/signals_RSI.py` non ha bisogno delle convenzioni Dash.

Principio: **una preoccupazione per file**, sotto le 50 righe dove possibile.

---

## Livello 3 â€” Split di `AGENTS.md`

### Il problema specifico

`AGENTS.md` Ã¨ lo standard cross-tool ([agents.md](https://agents.md)) letto automaticamente da Cursor, Copilot, OpenClaw, ecc. Il contenuto originale (~245 righe) descriveva **solo** l'agente di ricerca OpenClaw che orchestra la CLI `sfa` via SSH â€” non la scrittura di codice.

Cursor lo caricava comunque durante sessioni di coding â†’ ~180 righe sprecate per turno.

### La soluzione: split slim + companion

| File | Righe | Ruolo |
|------|-------|-------|
| `AGENTS.md` | ~67 | Entry point always-on: invocazione, core loop, regole critiche di sicurezza |
| `docs/openclaw-research.md` | ~166 | Manuale completo: sweep multi-ticker, metriche per regime, promotion gates, escalation |

`AGENTS.md` inizia con:

```markdown
## Session start (required)
Before any research action, read:
1. docs/openclaw-research.md
2. RESEARCH.md
```

**Rationale dello split:**

- **Cursor (coding)** â€” carica solo le ~67 righe; non vede sweep ETF, research notes, pre-registration budget.
- **OpenClaw (research)** â€” carica `AGENTS.md` + legge esplicitamente il companion all'avvio sessione.
- **CompatibilitÃ ** â€” `AGENTS.md` resta alla root (richiesto dallo standard e dal deploy su `/opt/searchforalpha`).

> **Nota:** OpenClaw non ha un meccanismo nativo â€œcarica questo file solo per la ricercaâ€. Lo split funziona perchÃ© il file always-on Ã¨ sottile e l'agente research Ã¨ istruito a leggere il companion â€” non perchÃ© esista un loader separato.

---

## Livello 0 â€” `rtk` e hook shell

### Cos'Ã¨ `rtk`

CLI proxy che filtra e comprime l'output dei comandi shell. Risparmio tipico: **60â€“90%** sui token di output (git, pytest, diff).

Esempio:

```bash
# Output verbose (~800 token)
python -m pytest lib/tests/ -v

# Output compresso (~80 token)
rtk python -m pytest lib/tests/ -q
```

### Integrazione per tool

| Tool | Meccanismo | File |
|------|-----------|------|
| **Cursor** | Hook `preToolUse` â†’ `rtk hook cursor` | `.cursor/hooks.json` (progetto) + `~/.cursor/hooks.json` (globale) |
| **GitHub Copilot** | Hook PreToolUse | `.github/hooks/rtk-rewrite.json` |
| **Istruzioni manuali** | Tabella comandi | `.github/copilot-instructions.md` |

L'hook Cursor riscrive automaticamente i comandi Shell prima dell'esecuzione â€” l'agente non deve ricordarsi di prefissare `rtk` (la regola in `token-efficiency.mdc` resta come fallback).

Setup una tantum per macchina:

```powershell
rtk init -g --agent cursor --hook-only --no-patch
```

VS Code/Cursor auto-approva `rtk` via `.vscode/settings.json`:

```json
"chat.tools.terminal.autoApprove": { "rtk": true }
```

### Monitoraggio

```powershell
rtk gain              # dashboard risparmi globali
rtk gain --history    # storico per comando
rtk discover          # comandi ancora senza prefix rtk
```

Comandi ad alto impatto in questo repo: `git diff`, `git log`, `pytest`, `sfa ... --json`.

---

## Mappa file completa

```
SearchForAlpha_lab/
â”œâ”€â”€ CLAUDE.md                          # Always-on slim (~18 righe)
â”œâ”€â”€ AGENTS.md                          # Always-on slim OpenClaw (~67 righe)
â”œâ”€â”€ docs/
â”‚   â”œâ”€â”€ openclaw-research.md           # Manuale research completo
â”‚   â””â”€â”€ token-efficiency.md            # â† questo documento
â”œâ”€â”€ .claude/
â”‚   â””â”€â”€ PROJECT_INDEX.md               # Indice navigazione + tabella tier
â”œâ”€â”€ .cursor/
â”‚   â”œâ”€â”€ hooks.json                     # rtk hook Cursor (progetto)
â”‚   â””â”€â”€ rules/
â”‚       â”œâ”€â”€ token-efficiency.mdc       # Always-on
â”‚       â”œâ”€â”€ model-routing.mdc          # Always-on
â”‚       â”œâ”€â”€ sfa-python.mdc             # Glob: lib/**/*.py
â”‚       â”œâ”€â”€ dash-callbacks.mdc         # Glob: lib/dash/**
â”‚       â””â”€â”€ sfa-cli-research.mdc       # Glob: lib/cli/**
â””â”€â”€ .github/
    â”œâ”€â”€ copilot-instructions.md        # rtk per Copilot
    â””â”€â”€ hooks/rtk-rewrite.json         # Hook Copilot
```

---

## Impatto stimato

| Intervento | Risparmio |
|------------|-----------|
| `CLAUDE.md` 108 â†’ 18 righe | ~90 righe/tokens per sessione Cursor |
| `AGENTS.md` 245 â†’ 67 righe | ~178 righe/tokens per sessione Cursor |
| Regole scoped | Convenzioni Python/Dash/CLI solo quando servono |
| Hook `rtk` | 60â€“90% sui token di output shell |
| Context discipline | Meno read completi di file da 1800+ righe |

Trade-off accettato: l'agente OpenClaw **deve** leggere `docs/openclaw-research.md` all'inizio sessione. Se non lo fa, mancano regole di sweep e promotion. Mitigazione: istruzione esplicita in cima a `AGENTS.md`.

---

## Principi guida (checklist)

1. **Ogni token always-on deve guadagnarselo** â€” se il codice lo dice giÃ , non ripeterlo.
2. **Tiered injection** â€” essenziale sempre; dettaglio per glob o lettura on-demand.
3. **Una preoccupazione per file** â€” no monoliti da 500 righe.
4. **Referenzia path, non incollare codice** â€” evita staleness e spreco.
5. **Output shell compresso** â€” `rtk` + flag `-q`, `-10`, `--tb=short`.
6. **Regola dei tre** â€” codifica un pattern come regola solo dopo 3 fallimenti ripetuti dello stesso tipo.
7. **Non generare regole con LLM** â€” aumentano costi del 20%+ senza beneficio netto.

---

## Deploy server (OpenClaw)

Il deploy rsync dell'intero repo include giÃ  `docs/`. Se usi `scp` selettivo, aggiungi:

```bash
scp .../docs/openclaw-research.md root@server:/opt/searchforalpha/docs/
```

OpenClaw legge `AGENTS.md` da `/opt/searchforalpha/AGENTS.md`; il companion deve essere presente nello stesso percorso relativo.


---

## Phase 2 changelog (2026-06)

- **`.cursorignore`** — `AGENTS.md`, `RESEARCH.md`, `docs/token-efficiency.md`, `results/`, `export/`, `lib/WIP/`, bytecode; stops Cursor auto-loading OpenClaw rules during coding sessions.
- **`sfa-python.mdc` glob** — excludes `lib/dash/**` and `lib/cli/**` to avoid overlap with scoped Dash/CLI rules.
- **`dash-callbacks.mdc`** — refreshed for register/layout/routes/bootstrap architecture (post-refactor).
- **`PROJECT_INDEX` split** — slim hub + `PROJECT_INDEX_MODULES.md` on demand.
- **Claude artifacts** — `new-callback` command and `dashboard-dev` agent synced to register pattern.

Research in Cursor: `@docs/openclaw-research.md` (see `CLAUDE.md`).

---

## Riferimenti

- [AGENTS.md standard](https://agents.md) â€” formato cross-tool
- [Cursor Rules docs](https://docs.cursor.com/context/rules) â€” `.mdc` con glob e `alwaysApply`
- [rtk CLI](https://github.com/rtk-ai/rtk) â€” compressione output shell
- `.claude/PROJECT_INDEX.md` â€” tabella tier aggiornata
- `RESEARCH.md` â€” knowledge base mercato/ticker per OpenClaw
