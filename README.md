# Stimmen Fryslân

Eigen, kleine site die laat zien hoe elke fractie in Provinciale Staten
Fryslân stemde — gebouwd op dezelfde open data als het origineel
(Notubiz), maar met eigen code, alleen voor Fryslân, en wekelijks ververst
via GitHub Actions. Geen server nodig, geen Python op je eigen computer.

## In gebruik nemen (eenmalig, ~10 minuten)

1. Maak op github.com een **nieuw, leeg repository** aan (bijv. `stimmen-fryslan`).
2. Upload de inhoud van deze map naar dat repository. Kan via de
   webinterface: "Add file" → "Upload files", sleep alle bestanden
   (inclusief de verborgen map `.github` en het bestand `.nojekyll`) erin
   en commit.
3. Ga naar **Settings → Pages**. Zet bij "Build and deployment" de
   **Source** op "Deploy from a branch", branch **main**, map **/ (root)**.
   Na een minuut of twee staat de site op
   `https://JOUW-GEBRUIKERSNAAM.github.io/stimmen-fryslan/`.
4. Ga naar het tabblad **Actions**. Als Actions nog uitstaat voor forks/nieuwe
   repos, zet ze aan. Klik de workflow **"Ververs stemdata"** open en druk
   op **"Run workflow"** om de eerste, echte dataset op te halen (dat
   vervangt het voorbeeldbestand dat er nu in staat).
5. Klaar. Daarna draait de workflow vanzelf **elke maandag 04:00 UTC**
   opnieuw en ververst `data/fryslan.json` automatisch.

## Lokaal bekijken

```
python3 -m http.server 8000
```
en open `http://localhost:8000`. Niet `index.html` dubbelklikken — browsers
blokkeren dan het inladen van `data/fryslan.json`.

## Zelf de data verversen

```
python3 collector.py
```
Alleen standaardbibliotheek, geen `pip install` nodig.

## Bron

Open data van de Steategriffy Fryslân via Notubiz
(fryslan.notubiz.nl). Dit is een hergebruik-project van een particulier,
geen officiële uitgave van de provincie.
