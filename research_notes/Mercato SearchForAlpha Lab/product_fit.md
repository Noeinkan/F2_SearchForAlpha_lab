# Fit commerciale di SearchForAlpha Lab

## Quale problema risolve oggi il prodotto e per chi?

### Takeaway
La proposta più coerente è un ambiente di ricerca riproducibile per trader sistematici indipendenti: dalla formulazione di segnali al backtest, ottimizzazione, verifica fuori campione e osservazione su conto paper. Il prodotto non dimostra ancora che un segmento specifico abbia acquistato o richiesto questo flusso.

### Cited Findings
- Il brief descrive un flusso unico `list → backtest → optimise → trials → walkforward → promote → run`, CLI con JSON stabili e Dashboard Dash. I trial conservano seed, parametri, metriche e commit per la riproducibilità — [Source](../../product.md).
- Il problema dichiarato è la ricerca ad hoc non riproducibile, priva di passaggio coerente dall'idea a una strategia validata ed eseguibile — [Source](../../product.md).
- Il brief nomina come utenti **inferiti dalle funzioni**, non come persone validate: ricercatori di trading algoritmico, operatori con conto IB paper, agenti autonomi, trader che studiano opzioni e analisti fondamentali — [Source](../../product.md).
- I casi d'uso mostrano richieste concrete: testare RSI e trend, combinare segnali, confrontare fondamentali e valutazioni, esaminare attività nelle opzioni. Il testo definisce l'app come strumento educativo e di ricerca, non consulenza finanziaria — [Source](../../USE_CASES.md).
- L'esecuzione live è disabilitata; il percorso IB è paper. Questo riduce l'aderenza a chi cerca automazione di trading live immediata — [Source](../../product.md); [Source](../../README.md).

### Inferences
- **Prima ipotesi buyer (più forte):** trader sistematici individuali e piccoli gruppi di ricerca già capaci di usare Python o una dashboard complessa, che spendono tempo a ripetere test e a evitare overfitting. Il flusso CLI e la validazione fuori campione rispondono direttamente al problema dichiarato; la disponibilità a pagare resta da verificare.
- **Seconda ipotesi:** formatori e comunità di trading quantitativo che vogliono un laboratorio dimostrabile per insegnare il passaggio da backtest a verifica fuori campione. La licenza MIT e la finalità educativa potrebbero supportare servizi, hosting o formazione più di una semplice licenza software.
- **Ipotesi più debole:** piccoli team prop o desk professionali. Il motore paper e i dati Yahoo aiutano la prototipazione, ma limitano l'uso operativo professionale finché non vi sono dati affidabili, controlli multiutente e prove di affidabilità.
- **Non mettere al primo posto** trader discrezionali interessati soltanto a segnali o opzioni: Flow Scanner e valutazione fondamentale ampliano i casi d'uso, ma indeboliscono un posizionamento focalizzato e non costituiscono prova di domanda.

### Gaps
- Non ci sono interviste, dichiarazioni di buyer, richieste di prezzo, contratti, pagamenti o testimonianze nei documenti esaminati.
- Non è definita una specifica offerta a pagamento: self-hosting, abbonamento hosted, consulenza o formazione.
- Il brief contiene dettagli tecnici che possono essere superati da modifiche successive; per claim pubblici sul runner o sugli ordini va usato il codice corrente, non solo il brief.

## Che cosa offre la demo e che cosa prova sulla domanda?

### Takeaway
La demo pubblica è un esperimento di acquisizione misurabile, ma la sua esistenza non prova interesse, utilizzo o disponibilità a pagare. I dati di accesso esistono in un database privato e non sono riportati nella documentazione.

### Cited Findings
- La demo pubblica richiede email e concede una prova gratuita di sette giorni; offre dashboard, backtest, ottimizzazione e analisi su snapshot congelato, senza broker o paper execution — [Source](../../docs/DEMO.md).
- La documentazione distingue chiaramente demo e workspace hosted: il secondo è riservato al proprietario e agli invitati, usa dati Yahoo/SEC live e non include broker — [Source](../../docs/HOSTED.md).
- La demo registra iscritti, accessi, pagine e azioni nell'area amministrativa, con esportazione CSV. Sono quindi disponibili misure osservabili di attivazione e uso, ma la documentazione non ne fornisce i valori — [Source](../../docs/DEMO.md).
- `COMMERCIAL.md` classifica il livello di evidenza a 1/5 e indica `unknown` per le dimostrazioni a potenziali clienti; non nomina acquirenti confermati — [Source](../../COMMERCIAL.md).

### Inferences
- Il funnel minimo misurabile è **visita → richiesta codice → primo accesso → backtest/ottimizzazione → ritorno → richiesta di accesso hosted o conversazione commerciale**. Le prime cinque fasi possono essere in parte ricostruite dall'area admin; l'ultima richiede un processo commerciale esplicito.
- Una demo con snapshot congelato è adatta a mostrare la ricerca, ma può sottostimare l'interesse per l'uso quotidiano con dati aggiornati. Una sessione guidata del workspace hosted potrebbe testare meglio l'intento di acquisto.
- Per attribuire `demonstrated: yes` servono sessioni effettive con potenziali clienti documentate, non solo disponibilità pubblica della demo. Per alzare il livello di evidenza servono utenti/piloti osservati o pagamenti secondo la scala RepoRadar.

### Gaps
- Numero di iscritti unici, attivi, azioni completate, ritorni e conversioni: non presenti nei documenti. La ricerca non ha avuto accesso all'area admin e non deve inventarli.
- Non risulta una call to action che proponga un piano, un prezzo o una conversazione guidata dopo il trial.

## Quale promessa commerciale si può testare senza sovravendere?

### Takeaway
La promessa testabile è risparmiare tempo nel validare idee di trading e ridurre i passaggi manuali, mantenendo ogni risultato riproducibile. Non si deve promettere rendimento, miglioramento della performance o trading live.

### Cited Findings
- La documentazione mostra ottimizzazione con Optuna, walk-forward e gate di promozione basato su metriche fuori campione — [Source](../../product.md).
- Le istruzioni pubbliche avvertono che un backtest descrive il passato, non garantisce il futuro, e che il prodotto è per ricerca ed educazione — [Source](../../USE_CASES.md).
- La demo limita calcolo e accesso e usa prezzi congelati; il workspace hosted usa prezzi correnti ma resta ad accesso controllato — [Source](../../docs/DEMO.md); [Source](../../docs/HOSTED.md).

### Inferences
- Messaggio da testare con 5-10 persone del segmento principale: “Da un'idea di segnale a un esperimento riproducibile con verifica fuori campione, nello stesso ambiente.” Domande: quale passaggio richiede più tempo oggi, quale risultato renderebbe il tool indispensabile, e per quale accesso pagherebbero.
- Misura utile: completamento di un backtest e di un walk-forward nella prima sessione; non solo iscrizione. Un prezzo ipotizzato può essere testato con una pagina o un colloquio, senza presentarlo come ricavo dimostrato.

### Gaps
- Nessun benchmark osservato sul tempo risparmiato rispetto ai notebook o ai concorrenti; misurarlo con utenti reali.
- Non sono documentati NPS, retention, uso di strumenti concorrenti o budget dei potenziali buyer.
