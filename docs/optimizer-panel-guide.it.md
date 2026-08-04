# Il Pannello Optimizer — Guida in Parole Semplici

*Come usare il tab **Optimizer** nel pannello di destra, perché esiste e cosa ci guadagni.*

> **Cos'è l'Optimizer?** Il tab Backtest testa **una** idea che hai scelto a mano.
> L'Optimizer testa **centinaia di idee al posto tuo** e le classifica: così, invece di
> tirare a indovinare "quali segnali dovrei combinare?", lasci che l'app provi le
> combinazioni e ti consegni una classifica delle migliori.
>
> Solo per uso didattico/di ricerca. Un buon piazzamento sui dati passati *non* è una
> garanzia di risultati futuri — vedi la nota di onestà nel §7.

---

## 1. Perché dovresti usarlo

| Se tu… | L'Optimizer ti permette di… |
|---|---|
| Non sai quali segnali scegliere | Provare molte combinazioni automaticamente e vedere cosa ha funzionato |
| Hai un segnale preferito ma nessuna regola di uscita | Scoprire quali segnali di sell si abbinano meglio |
| Vuoi il miglior Sharpe, non solo il miglior rendimento | Classificare in base alla metrica che ti interessa davvero |
| Sei sommerso dalle scelte di indicatori | Ottenere una breve lista ristretta e ordinata in pochi secondi |
| Hai trovato un vincitore | Portarlo direttamente nel tab Backtest con un clic |

Il vantaggio principale: **trasforma "quale di queste migliaia di combo è buona?" in una
top-10 ordinata.** È un motore di ricerca per idee di trading.

---

## 2. L'unica regola prima di iniziare

**Carica prima i dati.** Come il tab Backtest, l'Optimizer lavora su *qualsiasi grafico
sia attualmente caricato*. Nessun dato → mostra *"Please load market data first"*.

Nella **sidebar a sinistra** (Market Data): imposta il **Symbol** — carica da solo tutto
lo storico disponibile. Poi, nel tab **Backtest**, imposta **Test Window** e **Initial
Capital**. Una volta caricati i prezzi, passa al tab **Optimizer** in cima al pannello di
destra.

> L'Optimizer classifica le combinazioni sulla stessa Test Window, e la stampa mentre gira.
> Fare poi il backtest del vincitore misura esattamente lo stesso periodo.

---

## 3. Tour del pannello (dall'alto verso il basso)

### A — Signal Preview
*"Con cosa sto lavorando?"* Tre contatori in tempo reale che si aggiornano man mano che
carichi i dati e muovi gli slider:

- **BUY** — quanti segnali di buy sono disponibili sui dati caricati.
- **SELL** — quanti segnali di sell sono disponibili.
- **COMBOS** — il numero stimato di combinazioni che verranno effettivamente testate (già limitato dalla tua impostazione Max Combinations).

Usalo come verifica di buon senso *prima* di eseguire: se COMBOS dice `500`, è tutto il
lavoro che stai per richiedere.

### B — Max Signals per Side
*Slider, 1–5, predefinito `2`.*

Quanti segnali possono essere **impilati insieme** su ciascun lato (buy e sell).

- `1` = testa solo segnali singoli (veloce, semplice).
- `2` = consente coppie come "RSI oversold **+** MACD rialzista" (il punto ideale).
- `3`–`5` = combinazioni più ricche, ma il numero di possibilità esplode rapidamente.

> Più alto = più esaustivo ma più lento, e più incline all'**overfitting** (vedi §7). Parti da `2`.

### C — Max Combinations
*Casella numerica, 10–1000, predefinito `100`.*

Un **tetto** rigido su quante combinazioni testare effettivamente, per velocità. Anche se
Max Signals per Side potrebbe teoricamente produrre migliaia di combo, l'Optimizer si
ferma dopo questo numero.

- Scansione rapida: `50–100`.
- Sweep esaustivo: `300–1000` (più lento).

### C2 — Min Trades
*Casella numerica, predefinito `10`.*

La soglia di affidabilità. Ogni combinazione che ha fatto **meno** operazioni di questo
numero viene etichettata come **"low sample"** e spinta *sotto* quelle credibili nella
classifica — non viene eliminata, solo declassata. Uno Sharpe o un profit factor
splendidi costruiti su 3 operazioni sono fortuna, non vantaggio: così si evita che le
casualità dominino la classifica.

### D — Sort Results By
*Pulsanti segmentati.* Quale metrica ordina la classifica:

| Pulsante | Ordina per | Vuoi… |
|---|---|---|
| **SCORE** | Robustness Score (predefinito) | La scelta migliore a tutto tondo — rendimento aggiustato per il rischio con penalità per troppe poche operazioni |
| **RET** | Total Return % | Il guadagno grezzo maggiore |
| **SHARPE** | Sharpe Ratio | Il miglior rendimento *aggiustato per il rischio* (percorso più regolare) |
| **CALMAR** | Calmar Ratio | Il miglior rendimento rispetto al drawdown nel caso peggiore |
| **DD** | Max Drawdown % | La perdita nel caso peggiore più contenuta (ordinato con la meno grave in cima) |
| **TRADES** | Numero di operazioni | Il maggior (o minor) numero di operazioni |

> 💡 Puoi cambiare questa impostazione **dopo** un'esecuzione — la tabella si riordina
> istantaneamente senza ritestare nulla. Quindi esegui una volta, poi alterna tra SCORE /
> RET / SHARPE / CALMAR / DD per vedere il quadro da angolazioni diverse. Le combo
> low-sample restano sempre raggruppate sotto quelle credibili.

### Il pulsante — RUN OPTIMIZER
Premilo. Appare una barra di avanzamento e la ricerca comincia.

---

## 4. Cosa succede durante e dopo un'esecuzione

**Durante l'esecuzione:**
- Una **barra di avanzamento** mostra *"Testing 120/500 combinations…"*.
- Un conteggio in corso delle *"valid strategies found so far"* (strategie valide trovate finora).
- Non appena esistono almeno 5 risultati validi, una mini-tabella live **"Top strategies so far"** anteprima i leader del momento.
- Il pulsante RUN OPTIMIZER è disabilitato finché non finisce (la ricerca gira in background a piccoli lotti, così l'app resta reattiva).

**Quando finisce:**
- Un messaggio verde *"✓ Completed! Tested N combinations"*, seguito da una riga di
  onestà che ricorda che testare molte combo rende più probabile che il primo risultato
  sia fortuna.
- Una card **Best Strategy highlight** — il vincitore secondo la metrica scelta. Mostra
  Total Return, Sharpe, Max Drawdown, **Sortino, Calmar, Win Rate, Profit Factor**, numero
  di operazioni e una riga **"vs Buy & Hold" alpha**, così vedi subito se la strategia ha
  davvero battuto il semplice possesso del titolo. Un badge **"LOW SAMPLE"** compare se il
  vincitore ha fatto troppe poche operazioni.
- Una **tabella top-10** con le stesse metriche (più Alpha %). Le righe low-sample sono in grigio.
- In fondo appare un pulsante **Apply Best Strategy**.

### Apply Best Strategy
Cliccalo e l'Optimizer:
1. Copia i segnali di **buy** e **sell** vincenti nella sezione Signals del tab Backtest, e
2. Ti sposta automaticamente sul tab **Backtest**.

Da lì puoi eseguire un backtest **completo** sul vincitore — con le tue vere manopole di
Trade Setup e i Transaction Costs applicati (vedi §7 per il motivo per cui questo secondo
passaggio è importante).

---

## 5. Esempi di workflow

### Workflow 1 — "Non ho idea da dove iniziare" (principiante)
1. Scegli un symbol a sinistra, poi imposta una **Test Window** nel tab Backtest.
2. Tab Optimizer → lascia **Max Signals per Side** = `2`, **Max Combinations** = `100`.
3. Ordina per **RET**. Clicca **RUN OPTIMIZER**.
4. Leggi la card Best Strategy e la tabella top-10.
5. Clicca **Apply Best Strategy**, poi **RUN BACKTEST** sul tab Backtest per la pagella completa.

### Workflow 2 — "Mi interessa un percorso regolare, non solo il rendimento grezzo" (attento al rischio)
1. Esegui l'Optimizer come sopra.
2. Quando finisce, passa **Sort Results By** su **SHARPE** — la tabella si riordina all'istante.
3. Poi passa a **DD** per vedere quali combo hanno avuto la perdita nel caso peggiore più contenuta.
4. Scegli una strategia che si comporta bene in *tutte e tre* le viste, non solo in una.

### Workflow 3 — "Sweep esaustivo notturno" (avanzato)
1. Imposta **Max Signals per Side** = `3`, **Max Combinations** = `1000`.
2. Osserva il contatore COMBOS per confermare il carico di lavoro prima di eseguire.
3. **RUN OPTIMIZER** e lascialo macinare.
4. Tratta i risultati con sano scetticismo — più combo testi, più è probabile che il "vincitore" sia stato fortunato (§7).

### Workflow 4 — "Passaggio Optimizer → Backtest" (il ciclo consigliato)
1. L'Optimizer trova una combo promettente → **Apply Best Strategy**.
2. Sul tab Backtest, aggiungi i **Transaction Costs** realistici e il tuo **Trade Setup** (trailing stop, min holding, ecc.).
3. **RUN BACKTEST**. Verifica se il vantaggio sopravvive ai costi e ai tuoi controlli di rischio.
4. Se regge, **Save** come preset (sidebar sinistra → Saved Configurations).

---

## 6. Leggere la classifica

Ogni riga è una combinazione di segnali. Le colonne rispecchiano le scorecard del
Backtest — Total Return %, **Alpha %** (vs buy-and-hold), Sharpe, **Sortino, Calmar**,
Max Drawdown %, **Win Rate %, Profit Factor** e numero di operazioni. Regole di lettura rapide:

- **Guarda prima l'Alpha.** Un Total Return alto conta poco se il titolo stesso è raddoppiato. **Alpha %** è il rendimento della strategia *meno* quello del buy-and-hold — se è negativo, avresti fatto meglio a limitarti a tenere il titolo.
- **Non prendere semplicemente la riga #1.** Una differenza minima di rendimento tra la #1 e la #5 è rumore; preferisci la combo che ha anche uno Sharpe/Calmar decente e un drawdown controllato.
- **Diffida delle righe grigie (low-sample).** Una combo che ha "vinto" su 2 operazioni è fortuna, non vantaggio — per questo la soglia Min Trades le spinge in fondo alla classifica.
- **Incrocia le metriche.** Riordina per SHARPE, CALMAR e DD; una combo che si piazza bene in *tutte* è molto più affidabile di una che domina solo il RET. **SCORE** le combina già per te.

---

## 7. La nota di onestà (da leggere)

Due cose da tenere a mente affinché l'Optimizer aiuti invece di ingannare:

1. **L'Optimizer esegue un backtest *semplificato* e veloce.** Valuta ogni combinazione
   con le **impostazioni predefinite** — **non** applica le manopole di Trade Setup
   (trailing stop, take profit, min holding, position sizing) né i Transaction Costs del
   tab Backtest. Consideralo uno **screen veloce** per fare una lista ristretta di
   candidati. Riesegui sempre il vincitore sul tab **Backtest** con costi realistici e i
   tuoi controlli di rischio prima di fidartene.

2. **L'overfitting è reale.** Più combinazioni testi, più aumenta la probabilità che il
   risultato in cima abbia semplicemente adattato il *rumore* di questa specifica storia e
   non si ripeta. Difenditi: prediligi combo più semplici (meno segnali per lato), pretendi
   abbastanza operazioni, verifica le metriche in modo incrociato e — idealmente — riesegui
   il vincitore su un *diverso* intervallo di date per vedere se regge.

---

## 8. Il modello mentale in 30 secondi

1. **Carica i dati** (sinistra) → 2. **Imposta la dimensione della ricerca** (Max Signals
per Side + Max Combinations) → 3. **Scegli una metrica di ordinamento** (Sort Results By)
→ 4. **RUN OPTIMIZER** → 5. **Leggi la classifica**, riordinando per verifica incrociata →
6. **Apply Best Strategy** → 7. **Riesegui sul tab Backtest** con costi reali → 8. **Save**
i sopravvissuti.

Il compito dell'Optimizer è *restringere il campo*; il compito del tab Backtest è
*confermare onestamente il vincitore*. Usali insieme.

*Non è consulenza finanziaria. Solo per ricerca e apprendimento.*
