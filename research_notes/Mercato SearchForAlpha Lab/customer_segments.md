# Domanda e segmenti clienti

## Quanto è osservabile la domanda per strumenti di ricerca algoritmica?

### Takeaway
Esiste un pubblico riconoscibile per trading e ricerca quantitativa, ma i numeri pubblici disponibili sono insiemi molto più ampi del mercato indirizzabile di SearchForAlpha. Nessuna fonte trovata quantifica quanti pagherebbero per questo prodotto.

### Cited Findings
- Nel sondaggio FCA Financial Lives 2024, 1,6 milioni di adulti UK (3%) usavano una trading app; 11% usava una piattaforma di investimento non assistita. Sono categorie ampie, non utenti di backtesting. — [FCA Financial Lives 2024, pp. 37–38](https://www.fca.org.uk/publication/financial-lives/financial-lives-survey-2024-key-findings.pdf)
- Interactive Brokers comunicava 5,678 milioni di account clienti a fine ottobre 2026. Il comunicato non scompone gli account per uso di API, paper trading o ricerca algoritmica. — [IBKR, metriche ottobre 2026](https://www.interactivebrokers.com/mkt/getFileNew.php?file=latestMetricPR)
- La pagina ufficiale della community di QuantConnect indica oltre 250.000 quant e investitori. La cifra non indica utenti attivi o paganti. — [QuantConnect, Community](https://www.quantconnect.com/docs/v2/cloud-platform/community)
- QuantConnect descrive esplicitamente il rischio di overfitting da molti backtest e raccomanda una metodologia robusta come walk-forward per l'ottimizzazione dei parametri. — [QuantConnect, Research Guide](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/research-guide)
- IBKR presenta l'uso API per trader retail, algoritmici e proprietari; le sue API e i paper account coprono un flusso reale di sviluppo e prova. — [IBKR API Solutions](https://www.interactivebrokers.com/en/trading/ib-api.php); [IBKR Paper Trading Account](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/)

### Inferences
- Il segmento esiste, ma non si può usare 1,6 milioni, 5,678 milioni o 250.000 come TAM del prodotto: sono al massimo indicatori di un bacino da filtrare.
- Il bisogno più credibile da verificare è ridurre il lavoro manuale fra idea, backtest, controllo dell'overfitting e paper trading, poiché il problema è riconosciuto anche dalla documentazione di un concorrente.

### Gaps
- Non ho trovato un conteggio affidabile di utenti UK/EU che eseguono regolarmente backtest quantitativi, né una stima del loro budget o della propensione a pagare per SearchForAlpha.
- Nessuna di queste fonti dimostra traffico, registrazioni, uso della demo o interesse commerciale per SearchForAlpha.

## Chi potrebbe pagare e con quali condizioni?

### Takeaway
L'ipotesi iniziale più stretta è il ricercatore quantitativo indipendente che scrive Python e usa un conto IBKR. Piccoli team di trading sono un secondo segmento da testare; studenti e curiosi possono provare la demo ma hanno un segnale di pagamento più debole.

### Cited Findings
- QuantConnect distingue piani Free, Quant Researcher, Team, Trading Firm e Institution, con risorse di ricerca, backtesting, ottimizzazione e collaborazione; questo documenta packaging commerciale per individui e team, non il prezzo che SearchForAlpha potrebbe ottenere. — [QuantConnect Pricing](https://www.quantconnect.com/pricing)
- QuantRocket offre una versione gratuita per apprendimento e valutazione con dati campione, mentre l'accesso completo a dati aggiornati e trading richiede una licenza. Distingue utenti professionali da non professionali e include team, imprese e persone che gestiscono denaro altrui nella categoria professionale. — [QuantRocket Pricing](https://www.quantrocket.com/pricing/)
- IBKR elenca fra i clienti individuali, professionisti dei trading desk, hedge fund, advisor e prop firm; l'esistenza di questi tipi di cliente presso il broker non prova che tutti siano target di SearchForAlpha. — [IBKR Form 10-K 2025](https://www.sec.gov/Archives/edgar/data/1381197/000138119726000062/ibkr-20251231.htm)
- IBKR elenca decine di software integrati, fra cui QuantConnect, QuantRocket, BackTrader, TradingView e piattaforme per opzioni. È prova di un ecosistema competitivo di strumenti collegati al broker. — [IBKR Available Integrations](https://www.interactivebrokers.com/docs/third-party-integrations/available-integrations)
- Per un vendor terzo che accede via Web API agli account IBKR di clienti non affiliati, IBKR richiede onboarding e approvazione Compliance, e descrive aspettative su registrazione presso autorità competenti. Questa fonte riguarda quel modello di integrazione, non necessariamente l'attuale paper runner locale di SearchForAlpha. — [IBKR Web API Access for Third Parties](https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/)

### Inferences
- Priorità 1: trader/ricercatore sistematico individuale con Python e IBKR, che già prova strategie ma fatica a mantenere esperimenti riproducibili. Proposta da testare: percorso guidato e verificabile da ipotesi a walk-forward e paper account.
- Priorità 2: piccolo team quant/prop che vuole standardizzare risultati e controlli. Potenziale budget più alto, ma servono prova di collaborazione, data quality, affidabilità e supporto prima di proporre un'offerta team.
- Priorità 3: insegnanti e studenti di finanza quantitativa come canale di scoperta; utili per utilizzo e feedback, ma budget istituzionale e procurement non sono dimostrati.
- Evitare per ora il posizionamento come servizio che opera conti altrui: la documentazione IBKR mostra una complessità di onboarding e compliance distinta dal software di ricerca autonomo.

### Gaps
- I piani a pagamento dei concorrenti mostrano una categoria monetizzabile, ma non dimostrano willingness to pay per SearchForAlpha né permettono di fissarne un prezzo.
- Non risultano prove pubbliche sui tempi risparmiati, sulla qualità dei backtest o sulla retention di un utente SearchForAlpha; senza questi dati il ranking dei segmenti resta un'ipotesi.

## Come verificare rapidamente il segmento e la disponibilità a pagare?

### Takeaway
La ricerca secondaria basta per formulare ipotesi, non per compilare i campi “buyer confermato” o “demo mostrata a potenziali clienti”. Servono conversazioni e comportamento osservato nel prodotto.

### Cited Findings
- La documentazione QuantConnect usa contatori di backtest, parametri e tempo investito per spiegare il rischio di overfitting; sono spunti concreti per domande su un flusso di ricerca reale. — [QuantConnect, Research Guide](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/research-guide)
- IBKR documenta alcune differenze tra paper e live, inclusi tipi di ordine non supportati e fill simulati. Le interviste devono verificare se l'utente capisce e accetta questi limiti. — [IBKR Paper Trading Account](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/)

### Inferences
- Esperimento iniziale: reclutare 12–15 persone che abbiano eseguito almeno un backtest negli ultimi 90 giorni, separate fra individui Python/IBKR e piccoli team. Mostrare un workflow completo, annotare problemi reali, attivazione autonoma, ritorno entro 7–14 giorni e richieste di accesso pagato. Le soglie sono proposte di test, non benchmark di mercato.
- Domande di discovery: (1) Quale strategia hai testato di recente e come? (2) Quanto tempo è passato dall'idea al primo backtest credibile? (3) Come registri dati, parametri e versioni? (4) Come controlli overfitting e fuori campione? (5) Quale strumento usi oggi e quanto paghi? (6) Quale passaggio ripeti più spesso a mano? (7) Hai mai collegato una strategia a IBKR paper; cosa si è rotto? (8) Chi approva un nuovo strumento nel tuo team? (9) Cosa dovrebbe fare il prodotto per sostituire il tuo flusso attuale? (10) Se questo passaggio fosse risolto, quale budget già speso potresti riallocare?
- Registrare in modo separato tre prove: interesse dichiarato durante l'intervista, uso ripetuto della demo e impegno economico concreto (preordine, pilota pagato o fattura). Solo la terza supporta la claim “cliente pagante”.

### Gaps
- Non sono disponibili qui analytics o CRM di SearchForAlpha. Non si può quindi affermare che la demo sia stata usata o mostrata a un potenziale cliente.
