# SearchForAlpha Lab — Tab "Options" (optlib fork) — Piano di integrazione

> **Stato al 2026-08-21: piano NON eseguito.** Nessuno dei 10 file nuovi esiste — niente
> `lib/vendor/optlib/`, niente `lib/dash/callbacks/options_pricing.py`, niente `sfa options`.
> L'unico modulo presente e' [`lib/options/greeks.py`](../lib/options/greeks.py), scritto per i
> pannelli GEX/Vanna del Flow Scanner, non per il tab Options descritto qui.
> Stato aggiornato in [ROADMAP.md](../ROADMAP.md).

> Stato: **piano**. Nessuna modifica al codice o alla config fino ad approvazione.
> Scope concordato: **lite tab** (Pricer + Payoff + 4 strategie predefinite) + sorgente chain via `greeks-package` (MVP) con fallback esplicito a provider reale.
>
> Decisioni approvate:
> - Fork in account GitHub personale → submodule `lib/vendor/optlib/`
> - Sorgente chain default: `greeks-package` (PyPI, MIT)
> - Main page invariata: aggiunti **2 bottoni simmetrici** (header → Options · header Options → Back to Terminal) per la navigazione back-and-forth
> - Aggiunto comando CLI `sfa options price ...`

---

## TL;DR

1. Fork di [`dbrojas/optlib`](https://github.com/dbrojas/optlib) nella nostra org GitHub e clon in `lib/vendor/optlib/` come submodule.
2. Wrapper sottile in `lib/options/` che espone solo le funzioni closed-form di `optlib/gbs.py` (Black-Scholes, Merton, Black-76, Garman-Kohlhagen, Asian, Kirk, American) con validazione input.
3. Sorgente chain opzioni: `greeks-package` (PyPI, MIT) per l'MVP — scarica chain da Yahoo Finance, calcola i 13 Greeks localmente, dipendenza unica.
4. Due **bottoni simmetrici** per la navigazione back-and-forth (la main page resta invariata, `active-tab-store` default resta `backtest`):
   - Header main page → "OPEN OPTIONS" (accanto a theme toggle) → setta `active-tab-store = 'options'`
   - Header del pannello Options → "BACK TO TERMINAL" → setta `active-tab-store = 'backtest'`
5. Quattro strategie predefinite (Long Call, Long Put, Bull Call Spread, Iron Condor) con payoff diagram interattivo.
6. Test pytest per il wrapper pricing + smoke test del callback.
7. Comando CLI `sfa options price ...` (~30 righe in `lib/cli/options_cmd.py`).

---

## 1. Analisi di optlib (cosa c'è davvero, cosa usiamo)

### Repository

- URL: https://github.com/dbrojas/optlib
- Branch: `master`
- Lingua: Python, dipendenze: `numpy`, `scipy`, `pandas`, `requests`
- Licenza: **MIT** (Copyright 2017 Davis W. Edwards)
- Stato: 1,542 stelle, 225 fork, 0 issue, ultimo push 2022-11-18. **Repository dormiente** ma codice closed-form stabile.
- `setup.py` package name: `optlib`, version `0.5.1`.

### Cosa contiene

| File | Contenuto | Stato |
|------|-----------|-------|
| `optlib/gbs.py` (741 righe) | Formule closed-form: Black-Scholes, Merton, Black-76, Garman-Kohlhagen, Asian-76, Kirk-76, American (Bjerksund-Stensland 1993/2002), 4 implied-vol calculators. Restituiscono tuple `(value, delta, gamma, theta, vega, rho)`. | **Usiamo tutto** |
| `optlib/instruments.py` | Classi `Option`, `OptionChain`, `Pricehistory` per parsing risposte TD Ameritrade. | **Da non usare** — TD Ameritrade API deprecata |
| `optlib/api.py` | Client HTTP TD Ameritrade (`get_chain`, `get_pricehistory`, `get_quote`, `get_movers`). Richiede `TDA_API_KEY`. | **Da non usare** — endpoint morto |
| `optlib/__init__.py` | Esporta solo `Pricehistory` e `OptionChain`. | **Da sovrascrivere** — re-esporteremo le funzioni pricing |

### Funzioni pubbliche in `gbs.py` (firme esatte)

```python
# Europee
black_scholes(option_type, fs, x, t, r, v)        -> (value, delta, gamma, theta, vega, rho)
merton(option_type, fs, x, t, r, q, v)             -> (value, delta, gamma, theta, vega, rho)
black_76(option_type, fs, x, t, r, v)              -> (value, delta, gamma, theta, vega, rho)
garman_kohlhagen(option_type, fs, x, t, r, rf, v)  -> (value, delta, gamma, theta, vega, rho)
asian_76(option_type, fs, x, t, t_a, r, v)         -> (value, delta, gamma, theta, vega, rho)
kirks_76(option_type, fs, x, t, r, v, correlation, rate)  # Spread options

# Americane
american(option_type, fs, x, t, r, b, v)           -> (value, delta, gamma, theta, vega, rho)
american_76(option_type, fs, x, t, r, v)          -> (value, delta, gamma, theta, vega, rho)

# Implied volatility
euro_implied_vol(option_type, fs, x, t, r, b, cp, precision=.00001, max_steps=100)
euro_implied_vol_76(option_type, fs, x, t, r, cp, precision=.00001, max_steps=100)
amer_implied_vol(option_type, fs, x, t, r, b, cp, precision=.00001, max_steps=100)
amer_implied_vol_76(option_type, fs, x, t, r, cp, precision=.00001, max_steps=100)
```

Convenzioni: `option_type in {"c","p"}`, `fs` = prezzo spot/forward, `x` = strike, `t` = anni, `r` = risk-free decimale (0.05), `v` = IV decimale (0.25), `b` = cost-of-carry. Eccezioni: `GBS_InputError`, `GBS_CalculationError`.

### Licenza — compatibilità con il nostro progetto

optlib è **MIT** (file `LICENSE` contiene il testo integrale). SearchForAlpha Lab è anch'esso MIT (`pyproject.toml:11`). Combinabili senza restrizioni. **Obbligo**: mantenere l'header copyright + permission notice in tutte le copie. Il fork + inclusione come submodule + import in codice proprietario/closed sono tutti consentiti.

---

## 2. Sorgente dati chain opzioni — raccomandazione

`greeks-package` v1.2.2 (PyPI, MIT, 2026-04-20): una singola dipendenza che fa (a) download chain da Yahoo Finance via `yfinance` (già nel nostro `pyproject.toml`), (b) calcolo **13 Greeks** (Δ Γ V Θ ρ Vanna Volga Charm Veta Color Speed Ultima Zomma) con NumPy/SciPy, (c) American options via FDM. Le sue funzioni `download_options()` e `greeks()` coprono l'80% del tab "lite".

**Fallback gerarchico**:

1. **MVP** (oggi): `greeks-package` — zero nuove credenziali, funziona offline sui dati cached di yfinance, espone la stessa API delle chain TD Ameritrade ma con i Greeks pre-calcolati.
2. **Produzione 2026** (se servono dati live): **Tradier sandbox** (gratis, richiede account, rate-limit generoso, copertura US completa) — documentazione: https://documentation.tradier.com/.
3. **Analytics avanzate** (max pain, GEX, DEX, VEX, SVI surface, 0DTE): **FlashAlpha** free tier — 5 req/giorno, no carta di credito, endpoint REST `https://lab.flashalpha.com/v1/optionquote/{ticker}`.
4. **Storica + intraday** (backtest options): **Scalar Field** free — 5.000+ simboli US, intraday 1-min con Greeks dal 2020, daily EOD dal 2007.

Nessuna di queste tre fonti "serie" verrà cablata nel piano lite; saranno predisposti **adapter interfaces** in `lib/options/sources/` in modo che il passaggio da yfinance a Tradier richieda solo swap di classe.

---

## 3. Mappa: funzioni optlib → componenti dashboard

| Funzione optlib | Componente UI | File coinvolto |
|-----------------|---------------|----------------|
| `black_scholes(c, fs, x, t, r, v)` | KPI cell "Premium" + Greeks in tabella | `callbacks/options_pricing.py` |
| `euro_implied_vol(...)` / `amer_implied_vol(...)` | Reverse pricer: dato mid di mercato → σ | `callbacks/options_pricing.py` |
| `merton(..., q, v)` | Slider "Dividend yield q" (rilevante per SPX, NVDA) | `callbacks/options_pricing.py` |
| `garman_kohlhagen(..., r, rf, v)` | Hidden per ora; predispongo input `domestic_rate`/`foreign_rate` | `callbacks/options_pricing.py` |
| `asian_76(..., t_a, v)` | Hidden per ora; sarà usato se aggiungeremo Asian options | (futuro) |
| `kirks_76(...)` | Hidden per ora; spread su commodity | (futuro) |
| `american(...)` / `american_76(...)` | Bjerksund-Stensland 2002 per opzioni US equity | `callbacks/options_pricing.py` |
| Payoff atteso a scadenza | Grafico 2D interattivo (Plotly) | `chart_builder_options.py` |
| Greeks aggregati (ΣΔ, ΣΓ, max Θ) | Tabella Greeks nel summary panel | `callbacks/options_pricing.py` |
| Surface IV (call/put, strike × maturity) | Heatmap Plotly 2D | `chart_builder_options.py` |

### Pattern di rendering (riuso componenti esistenti)

- Pannelli: `bloomberg_section(title, children, theme=...)` da `lib/dash/components.py:26-80`
- KPI: `kpi_cell(label, value, delta, delta_color, theme=...)` da `lib/dash/components.py:82-121`
- Input densi: `dense_input(id, type='number', ...)` da `lib/dash/components.py:150-172`
- Pulsanti: `styles['button_primary']` / `styles['button_outline']` da `lib/dash/styles.py`
- Temi: 3 già definiti in `lib/dash/dash_config.py:16-149` (bloomberg/dark/light)

---

## 4. Schema del nuovo tab "Options" (layout ASCII)

```
+--------------------------------------------------------------------------------------+
| HEADER (main page)   SFA Terminal   [theme]  [OPEN OPTIONS >>>]                      |
+--------------------------------------------------------------------------------------+
| [Backtest] [Optimizer] [Data] |(Options)   < attivato cliccando "OPEN OPTIONS"      |
+--------------------------------------------------------------------------------------+
| HEADER (options page)  SFA Options  [<< BACK TO TERMINAL]  [theme]                   |
+--------------------------------------------------------------------------------------+
|  LEFT (sidebar)             |  CENTER (chart area)              |  RIGHT PANEL    |
|                             |                                    |  (Options tab)  |
|  Section: Underlying        |  +----------------------------+    |                 |
|   - Ticker       [AAPL]     |  |  PAYOFF DIAGRAM            |    |  P/L at expiry  |
|   - Spot price   [187.34]   |  |  (Plotly line chart)       |    |  2 rows         |
|   - Risk-free %  [  5.25]   |  |  - Long Call: blue         |    |                 |
|   - Dividend %   [  0.60]   |  |  - Long Put:  red          |    |  Max profit     |
|   - Date         [2026-06]  |  |  - Spread:    green        |    |  Max loss       |
|                             |  |  - Net:       amber bold   |    |  Breakeven(s)   |
|  Section: Strategy         |  +----------------------------+    |                 |
|   ( ) Long Call             |  +----------------------------+    |  Greeks summary |
|   ( ) Long Put              |  |  GREEKS TABLE (Σ pos)      |    |  Δ  +0.42       |
|   (•) Bull Call Spread      |  |  Δ  Γ  V  Θ  ρ  |  per leg |    |  Γ  +0.03       |
|   ( ) Iron Condor           |  +----------------------------+    |  V  +12.1       |
|                             |  +----------------------------+    |  Θ  -1.85       |
|  Section: Legs              |  |  IV SURFACE (heatmap)      |    |  ρ   +1.20      |
|  + Add leg + Remove leg     |  |  strike × expiry           |    |                 |
|  [QTY][TYPE][K][T][PREM]    |  +----------------------------+    |  [EXPORT CSV]   |
|  +1  CALL  185  28d  4.20   |                                    |  [EXPORT PNG]   |
|  +1  CALL  190  28d  2.10   |                                    |                 |
|  -1  CALL  200  28d  0.50   |                                    |                 |
|                             |                                    |                 |
|  [ COMPUTE ]   [ RESET ]    |                                    |                 |
+--------------------------------------------------------------------------------------+
| STATUS BAR: chain 142 calls / 98 puts | source: yfinance | computed in 47ms          |
+--------------------------------------------------------------------------------------+
```

### Comportamento interattivo

- Cambio ticker / spot / r / q → ricalcolo Greeks + payoff in <200ms (callback singolo, no `dcc.Interval`).
- Aggiunta/rimozione leg → ri-render tabella gambe + summary a destra + payoff.
- Cambio strategia preset → pre-popola 2-4 legs con strike ATM/OTM calcolati automaticamente.
- Click su heatmap IV → apre modal con payoff + Greeks per lo specifico strike/expiry.

---

## 5. Callback principale — firma precisa + nuovi dcc.Store

### `dcc.Store` da aggiungere (in `integrated_dashboard.py:55-82`)

```python
# In coda al blocco Store esistente, tutti session-scoped (no local):
dcc.Store(id='options-input-store',      data={},       storage_type='session'),
dcc.Store(id='options-legs-store',       data=[],       storage_type='session'),
dcc.Store(id='options-result-store',     data=None,     storage_type='session'),
dcc.Store(id='options-preset-store',     data=None,     storage_type='session'),
dcc.Store(id='options-source-store',     data='yfinance', storage_type='session'),
```

Naming convention: prefisso `options-*` (esattamente come esiste `optimization-*`, `presets-*`, `fundamentals-*` in `integrated_dashboard.py:55-82`). **Nessuna collisione** con gli store esistenti verificata.

### Callback principale: `compute_options_payoff`

```python
# In lib/dash/callbacks/options_pricing.py

@app.callback(
    Output('options-result-store', 'data'),
    Output('options-payoff-graph', 'figure'),
    Output('options-greeks-table', 'children'),
    Output('options-summary-panel', 'children'),
    Input('options-compute-button', 'n_clicks'),
    Input('options-legs-store',      'data'),
    Input('options-input-store',     'data'),
    prevent_initial_call=False,
)
def compute_options_payoff(
    n_clicks: int,
    legs: list[dict],          # [{qty, type:'c'|'p', strike, dte_years, premium?}, ...]
    inputs: dict,              # {spot, rate, dividend_yield, source}
) -> tuple[dict, go.Figure, html.Table, html.Div]:
    """Pricing + payoff + Greeks per la strategia corrente.

    Usa lib/options/wrapper.py (chiamata diretta a optlib.gbs) — NIENTE network.
    I legs provengono da input manuale o preset; il source 'yfinance' popola
    premium via greeks-package ma solo se l'utente clicca 'Fetch from chain'.
    """
```

### Callback secondari (uno per concern)

| ID | Trigger | Output | Responsabilità |
|----|---------|--------|----------------|
| `update_legs_table` | `options-legs-store.data` | `options-legs-table.children` | Renderizza tabella gambe editabile |
| `apply_strategy_preset` | `options-preset-store.data` | `options-legs-store.data` | Preset → gambe (Long Call, Long Put, Bull Call Spread, Iron Condor) |
| `fetch_from_chain` | `options-fetch-chain-button.n_clicks` | `options-legs-store.data` | yfinance/Tradier → popola gambe con mid prices |
| `update_payoff_chart` | `options-result-store.data` | `options-payoff-graph.figure` | Plot P/L a scadenza |
| `update_greeks_table` | `options-result-store.data` | `options-greeks-table.children` | Σ Greeks per strategia |
| `update_summary_panel` | `options-result-store.data` | `options-summary-panel.children` | Max profit, max loss, breakeven |
| `export_options_csv` | `options-export-csv-button.n_clicks` | `dcc.Download` | Dump leg + Greeks in CSV |
| `update_iv_surface` | `options-input-store.data` (source='yfinance') | `options-iv-heatmap.figure` | Heatmap strike × DTE |

### Registrazione

In `lib/dash/callbacks/__init__.py:19-32` aggiungere `from .options_pricing import register_options_callbacks` e chiamata `register_options_callbacks(app)` prima di `register_misc_callbacks(app)`.

### Modifica al tab switcher

In `lib/dash/callbacks/misc_ui.py:16-77` aggiungere `Output('panel-options', 'style')`, `Output('tab-options', 'style')`, `Input('tab-options', 'n_clicks')` e ramo `_styles_for_tab('options')` con `display: block` per il panel-options, `'options'` come valore finale di `active-tab-store`. Aggiungere in `lib/dash/integrated_dashboard.py:716-725` un quarto `html.Button("Options", id='tab-options', ...)` con separatore `│`.

### Callback per la navigazione back-and-forth (2 bottoni simmetrici)

```python
# In lib/dash/callbacks/options_pricing.py (continuazione)

@app.callback(
    Output('active-tab-store', 'data'),
    Input('open-options-button', 'n_clicks'),     # header main page
    Input('back-to-terminal-button', 'n_clicks'), # header options page
    State('active-tab-store', 'data'),
    prevent_initial_call=True,
)
def navigate_between_pages(open_clicks, back_clicks, current_tab):
    ctx = callback_context
    if not ctx.triggered:
        return current_tab
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if button_id == 'open-options-button':
        return 'options'
    if button_id == 'back-to-terminal-button':
        return 'backtest'
    return current_tab
```

ID dei bottoni e posizione:

- `open-options-button`: `html.Button("OPEN OPTIONS", id='open-options-button', n_clicks=0)` aggiunto in `lib/dash/integrated_dashboard.py:118-156` dentro `_create_header()`, accanto al theme toggle, stile `styles['button_primary']` con colore `accent_purple` per distinguerlo.
- `back-to-terminal-button`: stesso pattern, dentro `_create_options_panel_header()` (nuovo helper), stile `styles['button_outline']` con freccia `<<`.

`active-tab-store` resta `storage_type='local'` come già configurato in [lib/dash/integrated_dashboard.py:62](lib/dash/integrated_dashboard.py:62) → l'ultimo tab visitato viene ricordato al refresh del browser.

### Comando CLI aggiuntivo (`sfa options`)

Aggiunge un entry point non-UI: `python -m lib.cli.app options price --model bs --S 100 --K 100 --T 1 --r 0.05 --v 0.20`. Output JSON con `value, delta, gamma, theta, vega, rho`. Supporta anche `greeks` per il calcolo di tutti i 13 Greeks via `greeks-package`, e `iv` per l'inverse pricer. Sottocartella `lib/cli/options_cmd.py` (~80 righe) + registrazione in `lib/cli/app.py` come Typer sub-app.

---

## 6. File da creare / modificare

### Nuovi (10)

| Path | Righe stimate | Scopo |
|------|---------------|-------|
| `lib/vendor/optlib/.gitmodules` + clon | — | Submodule fork (post-`git submodule add`) |
| `lib/options/__init__.py` | 10 | Re-export pubblico `price_european`, `price_american`, `implied_vol` |
| `lib/options/wrapper.py` | ~180 | Funzione `price_european()`, `price_american()`, `implied_vol()` con normalizzazione parametri, validazione `_GBS_Limits`, gestione `GBS_InputError`/`GBS_CalculationError`, decoratore `lru_cache` per gli input discreti |
| `lib/options/payoff.py` | ~120 | Calcolo payoff a scadenza per lista legs; `max_profit`, `max_loss`, `breakevens` (root-finding su griglia + Newton) |
| `lib/options/strategies.py` | ~80 | 4 preset: `long_call`, `long_put`, `bull_call_spread`, `iron_condor` (generano lista legs dato spot/ATM_IV) |
| `lib/options/sources/yfinance_source.py` | ~70 | Adapter MVP: scarica chain via `greeks-package.download_options()`, normalizza formato |
| `lib/dash/callbacks/options_pricing.py` | ~280 | Le 8 callback di pricing + 2 bottoni navigazione back-and-forth |
| `lib/dash/chart_builder_options.py` | ~150 | `build_payoff_chart()`, `build_iv_surface()` |
| `lib/cli/options_cmd.py` | ~80 | Sotto-comando Typer `sfa options price / greeks / iv` |
| `lib/tests/test_options_wrapper.py` | ~150 | Unit test per `wrapper.py` (BS-Merton consistency, IV round-trip) |
| `lib/tests/test_options_payoff.py` | ~80 | Test per `payoff.py` (max profit/loss noti su strategie) |
| `lib/tests/test_options_cli.py` | ~40 | Smoke test del comando `sfa options price` via `typer.testing.CliRunner` |

### Modificati (6)

| Path | Cambio |
|------|--------|
| `pyproject.toml:14-34` | Aggiungere `"optlib @ file=./lib/vendor/optlib"` (submodule editable) e `"greeks-package>=1.2"` come dep |
| `lib/dash/integrated_dashboard.py:55-82` | Aggiungere 5 nuovi `dcc.Store` `options-*` |
| `lib/dash/integrated_dashboard.py:118-156` | Aggiungere `open-options-button` nell'header main page |
| `lib/dash/integrated_dashboard.py:716-741` | Aggiungere `tab-options` button + `panel-options` div wrapper |
| `lib/dash/callbacks/__init__.py:19-32` | Import + register `options_pricing` |
| `lib/dash/callbacks/misc_ui.py:16-77` | Estendere `switch_panel` per il quarto tab |
| `lib/cli/app.py` | Aggiungere `app.add_typer(options_cmd.app, name='options')` |

### Totale

- ~1.250 righe nuove (codice produzione) + ~270 righe test
- ~40 righe modificate su 7 file esistenti
- Zero rimozioni, zero rinominazioni pubbliche (rispetta la regola "preserve public APIs unless requested" in `model-routing.mdc`).

---

## 7. Sequenza di esecuzione (post-approvazione)

1. **Submodule**: `git submodule add git@github.com:<tuo-user>/optlib.git lib/vendor/optlib && cd lib/vendor/optlib && git remote add upstream https://github.com/dbrojas/optlib.git`
2. **Dep**: aggiungere `greeks-package>=1.2` a `pyproject.toml`; `pip install -e ./lib/vendor/optlib -e .`
3. **Wrapper pricing** (`lib/options/wrapper.py`): smoke test con `black_scholes('c', 100, 100, 1, 0.05, 0.20)` deve restituire ≈ `(10.45, 0.64, 0.02, -6.09, 37.52, 53.26)` (valore textbook).
4. **Unit test** prima della UI.
5. **UI shell** (tab + panel vuoto): verificare che `python main.py` carichi senza regressioni sul tab switcher esistente.
6. **Payoff chart** + callback base.
7. **Strategie preset** + tabella legs editabile.
8. **Source adapter** yfinance (popola premium da chain reale).
9. **Summary panel** + Greeks + export CSV.
10. **Smoke test E2E**: aprire dashboard, selezionare AAPL, scegliere "Bull Call Spread", verificare payoff coerente con Greeks.

---

## 8. Rischi e mitigazioni

| Rischio | Impatto | Mitigazione |
|---------|---------|-------------|
| `greeks-package` non installato o rotto | Tab Options non si carica | `try/except ImportError` in `chart_builder_options.py`, fallback a "Compute manually" con input S/K/T/r/σ diretti |
| yfinance 404 / rate limit | Chain vuota | Catch in `yfinance_source.py`, mostra banner "chain unavailable — use manual input" |
| Submodule non clonato | Import error all'avvio | Check in `lib/options/wrapper.py` con messaggio esplicito + istruzioni di install |
| Bjerksund-Stensland inaccurate near expiry | Greeks American approssimati | Documentare nel tooltip "American Greeks approximated (Bjerksund-Stensland 2002)" — TODO originale del repo optlib, accettato upstream |
| pyproject `optlib @ file=...` non risolto in CI | Build rotto | Aggiungere a `.github/workflows/` step `git submodule update --init --recursive` |

---

## 9. Cosa NON facciamo in questo piano

- ❌ Modificare `lib/cli/app.py` o aggiungere comandi `sfa options ...` (fuori scope "tab dashboard")
- ❌ Backtest di strategie options multi-day (richiede modelli stocastici tipo Heston — optlib non li ha, sono un altro progetto)
- ❌ Integrazione Interactive Brokers per paper-trading opzioni (esiste `ib_async` ma è una fase successiva)
- ❌ Refactor di `lib/strategy.py` per trattare opzioni come asset class
- ❌ Aggiornare `docs/openclaw-research.md` (research orchestrator, non codice)

---

## 10. Decisioni aperte da confermare prima dell'esecuzione

1. **Org GitHub per il fork**: `andre/optlib` o nome team? (10 secondi di scelta)
2. **Submodule path**: confermato `lib/vendor/optlib/`?
3. **`greeks-package` come default MVP**: ok o preferisci partire con input manuale (zero nuove dipendenze) e aggiungere `greeks-package` solo nella fase 2?
4. **Tab attivo di default all'apertura**: confermato `options` oppure restare su `backtest` per non spiazzare l'utente esistente?
5. **Esposizione nel CLI `sfa`**: aggiungere `sfa options price --model bs --S 100 --K 100 --T 1 --r 0.05 --v 0.20` come bonus a costo ~30 righe in `lib/cli/options_cmd.py`? (consigliato, sblocca uso da notebook/CI)

---

## Riferimenti file

- Dashboard init: [lib/dash/integrated_dashboard.py](lib/dash/integrated_dashboard.py) (~1761 righe)
- Callback registry: [lib/dash/callbacks/__init__.py](lib/dash/callbacks/__init__.py)
- Tab switcher: [lib/dash/callbacks/misc_ui.py](lib/dash/callbacks/misc_ui.py)
- Componenti riusabili: [lib/dash/components.py](lib/dash/components.py)
- Config: [lib/dash/dash_config.py](lib/dash/dash_config.py)
- Tema Bloomberg CSS: [lib/dash/assets/10-tokens.css](lib/dash/assets/10-tokens.css) (fogli `10-` … `90-`, vedi [docs/ui-architecture.md](ui-architecture.md))
- pyproject: [pyproject.toml](pyproject.toml)
- optlib upstream: https://github.com/dbrojas/optlib (branch `master`, MIT)
- greeks-package: https://pypi.org/project/greeks-package/ (v1.2.2, MIT)
- Regole progetto: [CLAUDE.md](CLAUDE.md) · [.cursor/rules/dash-callbacks.mdc](.cursor/rules/dash-callbacks.mdc) · [.cursor/rules/sfa-python.mdc](.cursor/rules/sfa-python.mdc)
