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

Conta le **operazioni complete** (un'entrata e l'uscita che l'ha chiusa), non i singoli
eseguiti: una combo che scala dentro ogni posizione supera questa soglia molto meno
facilmente di quanto sembri.

### D — Sort Results By
*Pulsanti segmentati.* Quale metrica ordina la classifica:

| Pulsante | Ordina per | Vuoi… |
|---|---|---|
| **SCORE** | Robustness Score (predefinito) | La scelta migliore a tutto tondo — rendimento aggiustato per il rischio con penalità per troppe poche operazioni |
| **DSR** | Deflated Sharpe Ratio | Il risultato più credibile *una volta corretto* per quante combo hai provato (vedi §7) |
| **RET** | Total Return % | Il guadagno grezzo maggiore |
| **SHARPE** | Sharpe Ratio | Il miglior rendimento *aggiustato per il rischio* (percorso più regolare) |
| **ALPHA** | Alpha di Jensen annualizzato | Il rendimento che il beta verso il buy-and-hold **non** spiega |
| **INFO RATIO** | Information Ratio | Il miglior rendimento attivo per unità di scostamento dal buy-and-hold |
| **CALMAR** | Calmar Ratio | Il miglior rendimento rispetto al drawdown nel caso peggiore |
| **DD** | Max Drawdown % | La perdita nel caso peggiore più contenuta (ordinato con la meno grave in cima) |
| **TRADES** | Numero di operazioni | Il maggior (o minor) numero di operazioni |

> 💡 Puoi cambiare questa impostazione **dopo** un'esecuzione — la tabella si riordina
> istantaneamente senza ritestare nulla. Quindi esegui una volta, poi alterna tra SCORE /
> DSR / RET / SHARPE / CALMAR / DD per vedere il quadro da angolazioni diverse. Le combo
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
- Un messaggio verde *"✓ Completed! Tested N combinations"*, seguito dal **Deflated
  Sharpe** della ricerca — una probabilità misurata che il vincitore sia reale, dato
  quante combo sono state provate (vedi §7), colorata verde / arancio / rossa.
- Una card **Best Strategy highlight** — il vincitore secondo la metrica scelta. Mostra
  Total Return, Sharpe, Max Drawdown, **Sortino, Calmar, Win Rate, Profit Factor**, numero
  di operazioni e una riga **"vs Buy & Hold"** con l'**excess return** e l'**alpha**, così
  vedi subito se la strategia ha davvero battuto il semplice possesso del titolo. Un badge **"LOW SAMPLE"** compare se il
  vincitore ha fatto troppe poche operazioni.
- Una **tabella top-10** con le stesse metriche (più Excess Return %, Alpha %, Beta e DSR %). Le righe low-sample sono in grigio.
- In fondo appare un pulsante **Apply Best Strategy**.
- Accanto, **REGIMES** esegue il backtest del vincitore separatamente in ogni regime di
  mercato dal 2019 e dice se supera la regola dei regimi di RESEARCH.md.

### Apply Best Strategy
Cliccalo e l'Optimizer:
1. Copia i segnali di **buy** e **sell** vincenti nella sezione Signals del tab Backtest, e
2. Ti sposta automaticamente sul tab **Backtest**.

Da lì puoi eseguire un backtest **completo** sul vincitore — con le tue vere manopole di
Trade Setup e i Transaction Costs applicati (vedi §7 per il motivo per cui questo secondo
passaggio è importante).

### Regimes (analisi per regime di mercato)
Il walk-forward chiede "regge su dati su cui non è stata ottimizzata?". **REGIMES** fa
un'altra domanda: "funziona solo in un tipo di mercato?". Dopo una ricerca combinatoria,
clicca **REGIMES** accanto a VALIDATE OOS. Si apre la sezione **Regime slicing** e, dopo
qualche secondo, compare una riga per ogni periodo del calendario dei regimi: il toro a
bassa volatilità del 2019, il crollo COVID, il toro del QE, l'orso del 2022, la ripresa
del 2023, il rally dell'AI e il mercato misto attuale.

Ogni riga è un backtest a sé: parte senza posizioni e con il capitale iniziale, così
un'operazione aperta nel 2021 non viene mai conteggiata nel 2022. Per ogni regime vedi
Sortino, rendimento, rendimento **buy & hold** sulle stesse date, max drawdown e numero
di operazioni. Un −3% nell'orso del 2022, mentre il buy & hold perdeva il 18%, si legge
in modo molto diverso da un −3% in un mercato al rialzo.

Il verdetto in alto applica la regola di RESEARCH.md: **Sortino positivo in almeno 3 dei
7 regimi, e uno dei tre deve essere l'orso del 2022**.

- **PASSES REGIME RULE** (verde) — la regola è rispettata.
- **FAILS REGIME RULE** (rosso) — l'orso del 2022 è stato testato ed è andato male,
  oppure i regimi superati sono troppo pochi.
- **INCONCLUSIVE** (arancio) — alcuni regimi non hanno dati completi e potrebbero
  ancora cambiare la risposta.

La colonna Data dice se i prezzi coprono tutto il regime: `full`, `partial` o `none`.
Solo le righe `full` contano per il verdetto. **Con barre 1h o 4h quasi tutte le righe
risultano `none`**, perché Yahoo conserva solo circa due anni di storico intraday: il
verdetto sarà quasi sempre INCONCLUSIVE. Passa all'intervallo 1d per una risposta vera.
Un titolo giovane (quotato dopo il 2019) mostra lo stesso effetto sui regimi iniziali.

Vengono usati le stesse colonne di segnale, le stesse impostazioni degli indicatori e
(con Realistic ranking) gli stessi costi/stop del vincitore. Clicca di nuovo mentre gira
per **STOP REGIMES**. Calendario e regola stanno in `config/regimes.yaml`; l'equivalente
da CLI per i bundle degli agenti è `sfa regimes --name <bundle>`.

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
Backtest — Total Return %, **Excess Return %** e **Alpha %** (entrambi vs buy-and-hold),
**Beta**, Sharpe, **DSR %**, **Sortino, Calmar**, Max Drawdown %, **Info Ratio**,
**Win Rate %, Profit Factor** e numero di operazioni. Regole di lettura rapide:

- **Guarda prima l'Excess Return.** Un Total Return alto conta poco se il titolo stesso è raddoppiato. **Excess Return %** è il rendimento della strategia *meno* quello del buy-and-hold — se è negativo, avresti fatto meglio a limitarti a tenere il titolo.
- **Poi guarda l'Alpha.** **Alpha %** è l'**alpha di Jensen** annualizzato: la parte di quell'excess che il **Beta** verso il buy-and-hold *non* spiega. Una combo che sta semplicemente lunga più a lungo guadagna excess return con un alpha vicino a zero — quella è leva, non abilità. L'excess dice *quanto in più hai guadagnato*; l'alpha dice *se te lo sei meritato*.
- **Poi guarda il DSR.** Vedi §7 — è l'unica colonna che sa quante combo sono state provate.
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

2. **L'overfitting è reale, e adesso è misurato.** Più combinazioni testi, più aumenta la
   probabilità che il risultato in cima abbia semplicemente adattato il *rumore* di questa
   specifica storia. La colonna **DSR %** — il **Deflated Sharpe Ratio** — gli mette un
   numero sopra, e lo stesso numero compare sotto il messaggio "Completed!" per la riga
   vincente.

   Leggilo come la probabilità che lo Sharpe di quella riga sia davvero positivo, misurata
   non contro zero ma contro lo Sharpe che *il migliore di N tentativi raggiungerebbe per
   solo rumore*. Tiene dentro quattro cose insieme: quanto è lungo il campione, quanto sono
   asimmetrici i rendimenti, quanto sono spesse le loro code e quante combinazioni ha
   guardato la ricerca.

   | DSR % | Cosa significa |
   |---|---|
   | **≥ 95%** | Sopravvive alla correzione. La soglia usuale per dire che un risultato è significativo. |
   | **50–95%** | Meglio di un lancio di moneta, sotto la soglia. Conferma fuori campione. |
   | **< 50%** | Non distinguibile dal migliore di N ricerche sul rumore. |

   Due conseguenze da interiorizzare. Alzare **Max Combinations** alza l'asticella che il
   vincitore deve superare — una ricerca più ampia non è un pasto gratis, e il DSR è dove
   ne vedi il prezzo. E anche una finestra più *corta* costa fiducia: lo stesso Sharpe su
   500 barre vale molto più che su 60.

   Il DSR non sostituisce le vecchie difese, le prezza: prediligi combo più semplici (meno
   segnali per lato), pretendi abbastanza operazioni, verifica le metriche in modo
   incrociato e — idealmente — riesegui il vincitore su un *diverso* intervallo di date per
   vedere se regge.

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
