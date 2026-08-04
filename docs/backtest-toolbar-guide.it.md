# La Barra degli Strumenti Backtest — Guida in Parole Semplici

*Come usare il pannello sul lato destro della dashboard, perché esiste e cosa ci guadagni.*

> **Cos'è un backtest?** È una "macchina del tempo" per le idee di trading. Scegli un
> insieme di regole ("compra quando l'RSI è basso, vendi quando è alto"), poi l'app
> riproduce i prezzi storici reali e finge di aver fatto trading per te. Alla fine ti
> dice se avresti guadagnato o perso denaro — **senza rischiare un solo dollaro reale.**
>
> Solo per uso didattico/di ricerca. Un backtest mostra ciò che *sarebbe* successo, non
> ciò che *succederà*. I rendimenti passati non sono una promessa.

---

## 1. Perché dovresti usarlo

| Se tu… | La barra Backtest ti permette di… |
|---|---|
| Hai un'intuizione di trading | Testarla su anni di dati reali in pochi secondi |
| Ti chiedi "è davvero valida?" | Ottenere numeri concreti: rendimento, rischio, win rate |
| Vuoi evitare errori costosi | Fallire *sulla carta* invece che con soldi veri |
| Stai confrontando due idee | Eseguirle entrambe e mettere le pagelle a confronto |
| Dimentichi che il trading ha dei costi | Vedere esattamente quanto commissioni + slippage erodono i profitti |

Il vantaggio principale: **trasforma un'opinione vaga in prove concrete.** Invece di
"penso che comprare sui ribassi funzioni", ottieni "questa regola ha reso +34% con un
win rate del 58% e una perdita nel caso peggiore del 12% negli ultimi 3 anni".

---

## 2. L'unica regola prima di iniziare

**Carica prima i dati.** Il pannello Backtest testa *qualsiasi grafico sia attualmente
caricato*. Se non ci sono dati di prezzo caricati, il pannello ti avviserà con
*"Please load market data first"*.

Nella **sidebar a sinistra** (sezione Market Data) c'è una sola cosa da impostare:

1. **Symbol** — digita un ticker o il nome di un'azienda (es. `AAPL`, `Tesla`). Si carica
   automaticamente; non c'è nessun intervallo di date da compilare.

L'app scarica sempre **tutto lo storico disponibile** per quel symbol — fino alla data di
quotazione per le barre daily, o gli ultimi 728 giorni per 1H/4H (limite di Yahoo).
La scelta del periodo da *misurare* avviene nel pannello Backtest, sotto **Test Window**.

> Il pulsante **⟳** nell'header riscarica il symbol corrente, per quando sono uscite nuove
> barre da quando hai aperto la pagina. Non serve per cambiare il periodo di test —
> quello non riscarica mai nulla.

Ora il grafico mostra i prezzi e il pannello Backtest a destra è pronto.

---

## 3. Tour della barra (dall'alto verso il basso)

Il pannello ha tre tab in alto — **Backtest**, **Optimizer**, **Data**. Questa guida
riguarda il tab **Backtest** (quello predefinito). È composto da cinque sezioni
richiudibili più il grande pulsante arancione **RUN BACKTEST**.

> 💡 Vedi un piccolo **`?`** accanto a un'etichetta? Passaci sopra il mouse per un
> tooltip in linguaggio semplice. Ogni controllo del pannello ne ha uno.

### Sezione 0 — Test Window
*"Quale fetta di storico sto misurando, e con quanti soldi?"*

- **MAX / 5Y / 2Y / 1Y / YTD** — scorciatoie. Contano all'indietro dall'ultima barra dei
  dati, non da oggi, e si fermano alla data di quotazione (chiedere 5Y di un titolo
  quotato da due anni dà due anni).
- **From / To** — imposta a mano qualsiasi periodo.
- **Initial Capital** — il tuo capitale iniziale simulato (es. `10000`).

Due cose da sapere:

- Cambiare la finestra **sposta il grafico di conseguenza**: quello che vedi è quello che misuri.
- Sia **RUN BACKTEST** che **RUN OPTIMIZER** valutano esattamente questa finestra, e la
  stampano sopra i risultati. Se i due non coincidono, è un bug — leggono lo stesso controllo.

### Sezione A — Execution Type
*"Come deve investire e disinvestire il mio denaro l'app?"*

Questa è la scelta più importante: i tuoi indicatori decidono *quando* operare, ma
l'Execution Type decide *quanto*, e se un segnale di sell o uno stop venga perfino
ascoltato.

| Modalità | Che cosa fa davvero | Ideale per |
|---|---|---|
| **Trading — Signal In/Out** | Ogni segnale di buy apre o incrementa una fetta dimensionata con **Kelly**; ogni segnale di sell, trailing stop o take-profit la chiude. Tutti i controlli di rischio sono attivi. | Trading classico dentro/fuori. |
| **Accumulation — DCA** | Investe un **importo fisso in dollari** a ogni segnale di buy finché la liquidità si esaurisce. **I segnali di sell vengono ignorati** e non esistono stop né take-profit. | Investimento di lungo termine "continua a comprare sui ribassi". |
| **Rebalancing — Target Weight** | Ogni segnale scambia la stessa **percentuale del valore del portafoglio** — dentro su un buy, fuori su un sell. Uno stop o un take-profit liquida comunque il 100%. | Esposizione più graduale, meno tutto-o-niente. |

Tre cose che sorprendono quasi tutti, tutte verificate dai test del motore:

- **Trading non investe il 100%.** Il dimensionamento Kelly, con i valori predefiniti
  (win rate 0.50, rapporto win/loss 1.50), chiede circa il **16,7%** del capitale, e il
  cursore Scale-in lo moltiplica. La card mostra la cifra reale in dollari prima ancora
  di lanciare il backtest.
- **Scale-in è una rampa, non un obiettivo.** Al 25% i buy consecutivi valgono 0,25 /
  0,50 / 0,75 / 1,00 × Kelly e si *sommano*: al terzo acquisto la posizione ha già
  superato una dimensione Kelly e continua a crescere. Lascialo a 100% se non vuoi
  esplicitamente quella rampa.
- **Accumulation non ha alcuna uscita.** Se hai selezionato indicatori di sell, non fanno
  nulla (il pannello ti avvisa). Win rate e profit factor restano vuoti perché la
  posizione non viene mai chiusa: non è un bug, semplicemente non esiste un trade concluso.

> 💡 Clicca una **`?`** su una card di modalità, oppure il pulsante **HOW EXECUTION
> WORKS**, per aprire la spiegazione: una tabella comparativa delle meccaniche più una
> sandbox che esegue il motore reale su un tracciato fisso di 24 barre, così puoi vedere
> ogni modalità operare barra per barra.

La tua scelta qui cambia quali opzioni appaiono nella sezione successiva.

### Sezione B — Trade Setup
*"Le manopole di regolazione fine."* Appaiono solo le manopole rilevanti per il tuo
Execution Type:

**Mostrate in modalità Trading:**
- **Strategy Preset** — punti di partenza rapidi: `Swing`, `Position`, `Trend` (oppure `Custom`). Imposta per te periodi di mantenimento e stop ragionevoli.
- **Min Holding Period (bars)** — obbliga la posizione a restare aperta per almeno N barre prima di poter vendere. Evita l'entra-ed-esci nervoso.
- **Trailing Stop (%)** — vende automaticamente se il prezzo scende di questa % dal suo picco. La tua rete di sicurezza.
- **Take Profit (%)** — vende automaticamente quando sei in guadagno di questa %. Blocca i profitti. (`0` = disattivato.)
- **Scale-in (%)** — quale frazione della dimensione-obiettivo calcolata da Kelly viene
  acquistata a ogni segnale. `100` (predefinito) significa che un solo segnale compra
  l'intera entrata. Abbassalo per entrare in modo graduale — ma ricorda che quegli
  ordini continuano a sommarsi invece di fermarsi alla dimensione piena.
- **Kelly Criterion (Win Rate + Win/Loss Ratio)** — la formula che fissa la dimensione
  obiettivo dell'entrata: `win_rate − (1 − win_rate) / win_loss_ratio` del portafoglio.
  Con i valori predefiniti (0.50 / 1.50) è il **16,7%**. Non toccarlo se non la conosci.

**Mostrate in modalità Accumulation:**
- **Amount Per Buy ($)** — quanti dollari investire a ogni segnale di buy (es. `1000`).
  Non si applica nient'altro: questa modalità non ha vendite, né stop, né take-profit.

**Mostrate in modalità Rebalancing:**
- **Portfolio Weight (%)** — quale fetta del **valore totale del portafoglio** scambiare
  per segnale (es. `25`). Stesso peso in entrata su un buy e in uscita su un sell, quindi
  il terzo acquisto ha la stessa dimensione del primo.
- Più Min Holding Period, Trailing Stop e Take Profit.

**Sempre mostrata — Consecutive Signals:** controlla cosa succede quando lo stesso
segnale scatta più volte su barre consecutive:
- **Scale-in** (predefinito) — agisce ogni volta. *(I buy ripetuti si accumulano.)*
- **Edge trigger (0→1 only)** — agisce solo nel momento in cui un segnale si attiva per la prima volta. Evita di caricare troppo.
- **Cooldown** — dopo aver agito, aspetta N **barre** (la casella *Cooldown bars*) prima di agire di nuovo.
- **Reset + Cooldown** — più severo: il segnale deve spegnersi completamente *e* deve trascorrere il cooldown.

### Sezione C — Signals
*"Cosa fa scattare davvero un buy o un sell?"* Questo è il cervello della tua strategia.

- **Filtri Search / Category** — restringono la lunga lista di indicatori disponibili (RSI, MACD, Bollinger, ecc.).
- **La lista dei segnali** — spunta gli indicatori che vuoi come trigger di **buy** e di **sell**.
- **Toggle OR / AND:**
  - **OR** — scatta se *qualsiasi* segnale selezionato si attiva (più operazioni, più permissivo).
  - **AND** — scatta solo quando *tutti* i segnali selezionati concordano (meno operazioni, più severo/ad alta convinzione).
- **AND Window (slider)** — quando usi AND, quanto vicini (in barre) devono verificarsi i segnali per "contare come concordi". `0` significa stessa barra.

> ⚠️ **Devi selezionare almeno un segnale di buy.** In modalità **Trading** serve anche
> almeno un segnale di sell (altrimenti l'app non sa mai quando liquidare).

### Sezione D — Transaction Costs
*"Rendi onesta la simulazione."* Il trading reale non è gratis. Questi costi vengono
addebitati a ogni operazione:

- **FX Fee (%)** — commissione di conversione valutaria (predefinito `0.15`).
- **Slippage (%)** — il piccolo prezzo che perdi tra la decisione e l'esecuzione effettiva (predefinito `0.05`).
- **Commission (%)** — commissione del broker per operazione (predefinito `0.00`).

Il suggerimento *"Trading 212 UK: 0% commission, 0.15% FX fee"* è un preset di broker
reale che puoi copiare.

> Lasciare i costi ti dà la **verità**. Impostarli tutti a `0` ti dà la **fantasia** del
> caso migliore. Il pannello dei risultati ti mostra *entrambi*, così puoi vedere la
> differenza.

### Il pulsante — RUN BACKTEST
Premilo. I risultati appaiono subito sotto.

---

## 4. Leggere i risultati

Dopo un'esecuzione ottieni un banner verde *"Backtest completed successfully!"*, una
striscia riepilogativa del portafoglio e una griglia di sei **pagelle** (scorecard):

| Scorecard | Cosa significa | Segnale positivo |
|---|---|---|
| **Total Return** | Guadagno/perdita % complessivo. Mostra anche *"NO COSTS"* — quanto avresti guadagnato senza commissioni. | Positivo e vicino al valore no-costs. |
| **Sharpe** | Rendimento aggiustato per quanto è stato movimentato il percorso. | ≥ 1 (etichettato **ROBUST**). |
| **Max DD** (drawdown) | Il calo peggiore da picco a valle lungo il percorso — il test per lo stomaco. | Più contenuto di −20% (**CONTROLLED**). |
| **Trade Count** | Quante operazioni sono avvenute. | Abbastanza da essere significativo (non 2, non 2000). |
| **Win Rate** | % di operazioni che hanno guadagnato. | Sopra il 50%. |
| **Profit Factor** | Profitti totali ÷ perdite totali. | Sopra 1.00 — guadagni più di quanto perdi. |

La striscia del portafoglio mostra anche **COST DRAG** — esattamente quanto denaro ti
sono costati commissioni + slippage, sia in % che in dollari. È la prova di onestà: una
strategia che vince solo *prima* dei costi non è una strategia reale.

> **Consiglio di lettura:** un rendimento alto con un Max DD *terribile* o un win rate
> sotto il 40% è un avviso, non una vittoria — potrebbe essere stato fortunato su una o
> due operazioni. Guarda tutte e sei le schede insieme.

---

## 5. Esempi di workflow

### Workflow 1 — "Comprare i ribassi su RSI ipervenduto funziona su Apple?" (principiante)
1. Sidebar sinistra: Symbol `AAPL`. Poi nel pannello Backtest: **Test Window** → imposta
   From/To agli ultimi 3 anni, capitale `10000`.
2. Execution Type → **Trading**.
3. Signals → spunta un segnale **RSI oversold** per il **buy**, un segnale **RSI overbought** per il **sell**. Logica = **OR**.
4. Transaction Costs → lascia i predefiniti (onesto).
5. **RUN BACKTEST**. Leggi Total Return, Win Rate, Max DD.
6. Confronta **Total Return** con il suo valore **NO COSTS** — quanto hanno inciso le commissioni?

### Workflow 2 — "Voglio meno operazioni, ma ad alta convinzione" (intermedio)
1. Stessa configurazione, ma scegli **due** segnali di buy (es. RSI oversold **AND** MACD rialzista).
2. Logica Signals → **AND**, AND Window → `2` (devono concordare entro 2 barre).
3. Trade Setup → imposta un **Trailing Stop** dell'`8%` e un **Min Holding Period** di `5` barre.
4. Eseguilo. Vedrai il **Trade Count** scendere e (idealmente) il **Win Rate** salire.

### Workflow 3 — "Dollar-cost averaging da imposta-e-dimentica" (lungo termine)
1. Execution Type → **Accumulation**.
2. Trade Setup → **Amount Per Buy** = `500`.
3. Signals → un unico segnale di buy generico (in questa modalità non serve un segnale di sell).
4. Eseguilo per vedere come sarebbe cresciuto il capitale con acquisti costanti a goccia.

### Workflow 4 — "Verifica di realtà sui costi"
1. Esegui una strategia qualsiasi con **tutti i costi = 0**. Annota il Total Return.
2. Ripristina i costi realistici (FX `0.15`, Slippage `0.05`) ed esegui di nuovo.
3. La differenza è il tuo **COST DRAG** — la prova che il vantaggio sopravviva o meno all'attrito del mondo reale.

### Workflow 5 — "Non so quali segnali scegliere" → usa l'Optimizer
Passa al tab **Optimizer** (accanto a Backtest). Invece di tirare a indovinare, **prova
per te molte combinazioni di segnali** e le classifica in base alla metrica che scegli
(Return, Sharpe, Drawdown o Trades). Poi clicca **Apply Best Strategy** per inserire la
combinazione vincente direttamente nel pannello Backtest — e rieseguila lì per esaminare
la pagella completa.

---

## 6. Salva ciò che funziona

Hai trovato una configurazione che ti piace? Usa la sezione **Saved Configurations**
nella sidebar sinistra: digita un **Name**, clicca **Save**, e l'intera configurazione
della barra viene memorizzata. Ricaricala in qualsiasi momento dal menu a tendina
**Preset** — senza dover rimettere tutte le spunte.

---

## 7. Risoluzione rapida dei problemi

| Se vedi… | Significa che… | Soluzione |
|---|---|---|
| *"Please load market data first"* | Nessun prezzo caricato. | Scegli un symbol a sinistra; si carica da solo. Se non succede, premi **⟳** nell'header. |
| *"Select at least one buy signal"* | Nessun trigger di buy scelto. | Spunta un segnale di buy nella sezione Signals. |
| *"Trading mode requires at least one sell signal"* | La modalità Trading richiede una regola di uscita. | Spunta un segnale di sell, o passa alla modalità Accumulation. |
| Zero o pochissime operazioni | Le tue regole AND sono troppo severe. | Allenta su **OR**, o allarga l'**AND Window**. |
| Rendimento ottimo, Max DD spaventoso | Forse una singola operazione fortunata. | Controlla Trade Count + Win Rate prima di fidarti. |

---

## 8. Il modello mentale in 30 secondi

1. **Carica i dati** (sinistra) → 2. **Scegli uno stile** (Execution Type) → 3. **Regola
le manopole** (Trade Setup) → 4. **Scegli i trigger** (Signals) → 5. **Mantieni
l'onestà** (Costs) → 6. **RUN** → 7. **Leggi le sei schede** → 8. **Salva** se è buona,
oppure aggiusta e ripeti.

Quel ciclo — *idea → test → misura → affina* — è tutto il senso della barra. Ti permette
di sbagliare a poco prezzo e spesso, così le idee che sopravvivono sono quelle che
meritano davvero attenzione.

*Non è consulenza finanziaria. Solo per ricerca e apprendimento.*
