# Dataset: cosa entra nella pagina

Un file per riga: da dove viene, come viene trasformato e quale parte della pagina muove. Unità: medie orarie in GW per potenze e flussi, €/MWh per i prezzi.

## Domanda e produzione

- **A65_IT_NORD**: domanda NORD. Media oraria in GW; muove il cursore “Domanda NORD”.
- **A75_IT_NORD**: solare. Media oraria in GW; muove il cursore “Solare”.
- **A75_IT_NORD**: eolico. Somma di eolico a terra e in mare, media oraria in GW; muove il cursore “Eolico”.
- **A75_IT_NORD**: idro fluente. Media oraria in GW; muove il cursore “Idro fluente”.
- **A75_IT_NORD**: altre must-run. Somma di biomasse, rifiuti, geotermia e altre fonti minori, media oraria in GW; muove il cursore “Altre must-run”.
- **A75_IT_NORD**: carico residuo. Domanda meno solare meno eolico, in GW; è il grafico sotto i prezzi nella sezione 9.

## Frontiere: flussi fisici (A11), cioè l’energia passata davvero sulla linea

- **A11_CH-IT_NORD**: flusso dalla Svizzera al NORD. Orario, in GW; entra nel “Flusso netto” Svizzera della sezione 3 e nel “Saldo estero reale” del pannello.
- **A11_IT_NORD-CH**: flusso dal NORD alla Svizzera. Orario; viene sottratto al precedente per avere il flusso netto Svizzera.
- **A11_FR-IT_NORD**: flusso dalla Francia al NORD. Media oraria in GW; entra nel flusso netto Francia (sezione 3) e nel saldo estero.
- **A11_IT_NORD-FR**: flusso dal NORD alla Francia. Viene sottratto al precedente.
- **A11_AT-IT_NORD**: flusso dall’Austria al NORD. Media oraria in GW; entra nel flusso netto Austria e nel saldo estero.
- **A11_IT_NORD-AT**: flusso dal NORD all’Austria. Viene sottratto al precedente.
- **A11_SI-IT_NORD**: flusso dalla Slovenia al NORD. Media oraria in GW; entra nel flusso netto Slovenia e nel saldo estero.
- **A11_IT_NORD-SI**: flusso dal NORD alla Slovenia. Viene sottratto al precedente.
- **A11_IT_CNOR-IT_NORD**: flusso dalla zona Centro-Nord al NORD. Media oraria in GW; serve a calcolare lo scambio netto con il Centro-Nord.
- **A11_IT_NORD-IT_CNOR**: flusso dal NORD al Centro-Nord. Questo meno il precedente muove il cursore “Export verso il Centro-Nord”, che si somma alla domanda.

## Frontiere: scambi programmati day-ahead (A09_DA), cioè l’energia programmata sulla frontiera dopo il day-ahead

- **A09_DA_CH-IT_NORD**: scambio programmato dalla Svizzera al NORD. È nell’export ma il tool non lo usa.
- **A09_DA_IT_NORD-CH**: scambio programmato dal NORD alla Svizzera. Non usato.
- **A09_DA_FR-IT_NORD**: scambio programmato dalla Francia al NORD. Non usato.
- **A09_DA_IT_NORD-FR**: scambio programmato dal NORD alla Francia. Non usato.
- **A09_DA_AT-IT_NORD**: scambio programmato dall’Austria al NORD. Non usato.
- **A09_DA_IT_NORD-AT**: scambio programmato dal NORD all’Austria. Non usato.
- **A09_DA_SI-IT_NORD**: scambio programmato dalla Slovenia al NORD. Non usato.
- **A09_DA_IT_NORD-SI**: scambio programmato dal NORD alla Slovenia. Non usato.
- **A09_DA_IT_CNOR-IT_NORD**: scambio programmato dal Centro-Nord al NORD. Non usato.
- **A09_DA_IT_NORD-IT_CNOR**: scambio programmato dal NORD al Centro-Nord. Non usato.

## Frontiere: capacità di scambio day-ahead (A61), cioè la capacità prevista messa a disposizione del day-ahead

- **A61_CH-IT_NORD**: capacità di import dalla Svizzera. Oraria, in GW; colonna “Capacità di import” della sezione 3 e parte del cursore “Capacità di import”.
- **A61_IT_NORD-CH**: capacità di export verso la Svizzera. Oraria; parte del cursore “Capacità di export”.
- **A61_FR-IT_NORD**: capacità di import dalla Francia. Come la Svizzera: sezione 3 e cursore “Capacità di import”.
- **A61_IT_NORD-FR**: capacità di export verso la Francia. Parte del cursore “Capacità di export”.
- **A61_AT-IT_NORD**: capacità di import dall’Austria. Sezione 3 e cursore “Capacità di import”.
- **A61_IT_NORD-AT**: capacità di export verso l’Austria. Parte del cursore “Capacità di export”.
- **A61_SI-IT_NORD**: capacità di import dalla Slovenia. Sezione 3 e cursore “Capacità di import”.
- **A61_IT_NORD-SI**: capacità di export verso la Slovenia. Parte del cursore “Capacità di export”.
- **A61_IT_CNOR-IT_NORD**: capacità dal Centro-Nord al NORD. Non usata: lo scambio con il Centro-Nord viene preso dai flussi reali.
- **A61_IT_NORD-IT_CNOR**: capacità dal NORD al Centro-Nord. Non usata, per lo stesso motivo.

## Prezzi dei vicini

- **A44_FR**: prezzo day-ahead Francia (asta SDAC), a quarti d’ora. Media semplice dei 4 quarti d’ora; entra nella media “Prezzo dei vicini”.
- **A44_CH**: prezzo day-ahead Svizzera, asta svizzera oraria. Preso così com’è; entra nella media “Prezzo dei vicini” (media semplice Francia–Svizzera).

## Combustibili

- **TV_PSV**: gas italiano al PSV, prezzo di chiusura del front-month da TradingView, in €/MWh. Vale la chiusura dell’ultimo giorno di borsa fino all’ora caricata; muove il cursore “PSV”. Le 22 righe sono i giorni di borsa di ottobre.
- **TV_EUA**: quote di CO₂, prezzo di chiusura del front-month da TradingView, in €/t. Stessa regola del PSV; muove il cursore “EUA”.

## Gli altri file

- **GME_MGP_NORD**: prezzo MGP della zona NORD, a quarti d’ora. Media semplice dei 4 quarti d’ora; è la linea magenta della sezione 9, il prezzo reale con cui si confronta il modello.
- **GME_MI1_NORD, GME_MI2_NORD, GME_MI3_NORD**: prezzi delle aste intraday MI-A1, MI-A2 e MI-A3 per NORD. Sono nell’export ma il tool non li usa.
- **A71_IT_NORD**: capacità installata a inizio anno di ogni unità di produzione da 100 MW in su (esportata dal sito ENTSO-E e convertita con `scripts/importa_a71.py`). La somma per tecnologia è il punto di partenza di gas, idro a bacino con pompaggi e carbone disponibili; la tecnologia di ogni unità serve anche a classificare le fermate A80. ENTSO-E non pubblica A68 (capacità per tecnologia) per il NORD.
- **A80_IT_NORD**: indisponibilità REMIT degli impianti NORD. Si sottraggono alla capacità A71 ora per ora, con la tecnologia presa da A71 tramite il codice EIC; muove i cursori “Gas disponibile”, “Idro a bacino e pompaggi” e “Carbone disponibile”.
