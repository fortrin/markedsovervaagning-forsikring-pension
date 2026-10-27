# Markedsovervågning – erhvervsforsikring og pension

Et dashboard til forsikringsmæglere, der giver overblik over det danske marked for erhvervsforsikring og firmapension: prisudvikling, selskabernes lønsomhed, indeksregulering, pensionsomkostninger og et værktøj til at finde det umiddelbart bedste pensionsselskab for en kunde.

Siden er ren HTML, CSS og JavaScript uden byggetrin. Alle tal ligger som CSV- og JSON-filer i `data/`.

## Indhold

| Fane | Viser |
|---|---|
| Overblik | Danske og europæiske nøgletal samt markedshændelser, der påvirker priser og vilkår ved næste fornyelse |
| Markedspriser | Danske prissignaler fra selskaberne, arbejdsskade efter Højesterets dom, stormskader og faste satser – samt Marsh-indekset for Europa og globalt |
| Forsikringsselskaber | Finanstilsynets nøgletal for danske skadesselskaber og selskabernes seneste kvartalstal |
| Indeksregulering | Lønindeks, byggeomkostningsindeks og forbrugerpriser samt en beregner for præmiestigning |
| Pension | Sektorens afkast og omkostninger, ÅOP pr. produkt og ÅOP 5 år før pension |
| Find pensionsselskab | Vælg branche, overenskomst, alder, risiko og vægtning – og få en rangliste over de kommercielle selskaber |

## Kør siden lokalt

Browseren må ikke hente datafilerne, når `index.html` åbnes direkte som fil. Start derfor en lille webserver i mappen:

```bash
python3 -m http.server 8000
```

Åbn derefter <http://localhost:8000>.

Siden henter d3 v7 fra jsDelivr, så der skal være internetadgang.

## Struktur

```
index.html          Siden: markup, layout og diagrammer
css/tema.css        Farver, skrift og afstande (lys og mørk tilstand)
js/dash.js          Indlæser datafilerne og tegner siden, når data eller valg ændrer sig
data/datasets.json  Liste over datasæt med titel, beskrivelse, fil og opdateringsdato
data/*.csv, *.json  Selve tallene
```

## Opdatér tallene

1. Ret eller tilføj rækker i den relevante fil i `data/`. Behold kolonnenavnene, og sæt tekst med komma i anførselstegn (fx `"84,9 %"`), ellers bliver kolonnerne forskudt.
2. Opdatér `opdateret` (og evt. `beskrivelse`) for datasættet i `data/datasets.json`.
3. Genindlæs siden.

Når en ny periode tilføjes, skal de faste periodehenvisninger i `index.html` (fx `data-where="kvartal=Q3 2026"` på nøgletallene) rettes til den nye periode.

| Fil | Kilde | Opdateres |
|---|---|---|
| `dk_erhverv_puls.csv` | Gjensidige, Tryg, Alm. Brand og Sampo/If (præmievækst og combined ratio i danske og nordiske segmenter) | Kvartalsvis |
| `dk_arbejdsskade.csv` | Selskabernes hensættelser efter Højesterets arbejdsskadedom 28. april 2026 | Kvartalsvis |
| `dk_vejrskader.csv` | Forsikring & Pension (storm- og skybrudsskader) | Halvårligt |
| `dk_satser.csv` | Beskæftigelsesministeriet (arbejdsskadesatser) og Lov om visse naturskader | Årligt |
| `marsh_global.csv`, `marsh_europe.csv`, `marsh_regions.csv` | Marsh Global Insurance Market Index | Kvartalsvis |
| `dk_skade_sektor.csv`, `dk_skade_selskaber.csv` | Finanstilsynet, Sektoren i tal (skadesforsikring) | Årligt |
| `selskaber_kvartal.csv` | Tryg, Gjensidige, Sampo/If og Alm. Brand | Kvartalsvis |
| `loenindeks.csv`, `byggeomkostninger.csv`, `forbrugerpriser.csv` | Danmarks Statistik | Kvartalsvis / månedligt |
| `pension_sektor.csv` | Finanstilsynet, Sektoren i tal (liv og pension) | Årligt |
| `pension_produkter.csv` | Branchestatistikken via sammenligner.dk | Årligt |
| `aop_5aar.csv` | Analysehuset Nikolaj Holdt Mikkelsen via Faglig Senior | Årligt |
| `pension_selskaber.csv` | Finanstilsynet, BEDSTpension forsikringsmægler, EPSI Rating | Årligt |
| `brancher.csv` | Egen oversigt ud fra Industriens Pension, TEKNIQ og PensionDanmark | Ved overenskomstfornyelse |
| `haendelser.json` | Udvalgte markedshændelser med kildelink | Løbende |

## Automatisk opdatering

**GitHub Action – Danmarks Statistik.** `.github/workflows/opdater-dst.yml` kører hver mandag morgen (og kan startes manuelt under fanen *Actions*). Den kører `scripts/opdater_dst.py`, som henter lønindeks, byggeomkostningsindeks og forbrugerpriser fra Statistikbankens åbne API. Scriptet finder selv den nyeste aktive tabel, når Danmarks Statistik skifter basisår, og stopper uden at skrive noget, hvis tal for perioder, der allerede ligger i filerne, afviger fra API'et. Der committes kun, når der er nye tal. Fejl vises som annoteringer på kørslen.

**Ugentlig Claude-opgave – øvrige kilder.** En planlagt opgave i Claude gennemgår hver mandag Marsh, selskabernes regnskaber, Forsikring & Pension, Finanstilsynet og pensionstal, retter datafilerne og skubber ændringerne hertil med en beskrivende commit-besked.

Begge kører `scripts/tjek_data.py` før hver commit. Den fanger rækker med forkert antal felter og tal med komma som decimaltegn.

Nøgletallene på siden viser altid den seneste række i hver fil, så nye perioder kommer frem uden ændringer i `index.html`.

## Sådan beregnes "Find pensionsselskab"

- **ÅOP:** selskabets billigste markedsrenteprodukt for en typisk kunde (40–55 år, 30–80.000 kr. årligt, 500.000 kr. opsparet). Vælges "tæt på pension", eller kræves en bæredygtig profil, bruges ÅOP 5 år før pension ved den valgte risiko.
- **Afkast:** gennemsnitligt årligt afkast 2016–november 2025, eller afkast januar–november 2025, for en kunde 20 år før pension ved middel risiko.
- **Score:** det bedste selskab på hvert parameter får 100 point og det dårligste 0. De to vægtes efter skyderen.
- Norli er udeladt, da der kun er tal for gennemsnitsrente. Arbejdsmarkedspensioner vises kun til sammenligning, fordi de som regel kræver overenskomst eller medlemskab.
- Forsikringsdækninger, rådgivning og kundetilfredshed indgår ikke i scoren.

Branche-oversigten er en tommelfingerregel. Den konkrete overenskomst afgør, hvilket pensionsselskab medarbejderne skal i.

## Forbehold

Tallene er indsamlet manuelt fra offentlige kilder og kan indeholde fejl eller være forældede. Værktøjet er et udgangspunkt for rådgivning og ikke en anbefaling i sig selv.
