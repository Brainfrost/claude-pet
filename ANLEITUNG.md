# claude-pet – Anleitung

Ein kleines Pixel-Haustier, das auf dem Text deiner Claude-Code-Sessions lebt: Jede Textzeile im
Windows Terminal ist für das Pet ein Boden. Es läuft darauf herum, schläft, frisst Bugs, kommentiert,
was Claude gerade macht, und holt dich, wenn eine Session fertig ist.

## Voraussetzungen

- Windows 10/11
- **Windows Terminal**, darin Claude Code (gern mehrere Sessions als Tabs)
- **Claude Code** (`claude` im PATH): Damit denkt sich das Pet über **Haiku** und dein Claude-Abo
  Sprüche aus. Ohne `claude` läuft es auch, sagt dann aber nur vorgefertigte Sprüche.
- Python 3.11 oder neuer. Fehlt es, bietet der Installer an, Python 3.12 per `winget` für deinen
  Benutzer zu installieren.

## Installation

1. Ordner holen, z. B. nach `C:\Users\<du>\claude-pet`:
   - mit git: `git clone <Repo-Link> claude-pet`
   - oder das ZIP herunterladen und entpacken
2. **`install.cmd` doppelklicken.** Der Installer prüft alles, richtet eine eigene Python-Umgebung
   (`.venv`) ein und startet das Pet. Am System wird sonst nichts verändert; Admin-Rechte braucht er nicht.
3. Das **Adoptionsfenster** geht auf: Figur aussuchen, Persönlichkeit lesen, Namen geben, adoptieren.
   Jede Figur bekommt einen zufälligen Charakter (faul, neugierig, verspielt, ängstlich) und eine
   eigene Persönlichkeit. **Figur, Charakter und Name bleiben für immer.** Also gut aussuchen 🙂

Ab jetzt startet das Pet automatisch mit Windows. Das Tray-Symbol (deine Figur) sitzt rechts unten
neben der Uhr, eventuell unter `^`.

## Mit dem Pet umgehen

| Maus | Was passiert |
|---|---|
| ziehen | hochheben und tragen, beim Loslassen in Bewegung wird es geworfen |
| klicken | anstupsen (weckt es auf) |
| hin und her darüberfahren | streicheln |
| auf einem Tab-Reiter loslassen | es zieht in diese Session um |
| Mauszeiger auf einem Wort ruhen lassen | je nach Charakter schaut es hin, läuft hin oder springt drauf |

**Tray-Menü (Rechtsklick auf das Symbol):**

- **Was denkst du gerade?** Sofort ein Kommentar zur aktuellen Session.
- **Ausflug machen!** Es springt auf ein anderes Fenster oder einen anderen Bildschirm.
- **Ball werfen**: Es jagt dem Ball nach und bringt ihn dir.
- **Bug-Jagd (30 Sekunden)!** Käfer krabbeln über den Text. Klick sie weg, bevor dein Pet sie schnappt.
- **Pet zu mir holen**
- **Tagebuch …**: Jeden Abend schreibt es einen Eintrag über euren Tag, freitags einen Wochenrückblick.
- **Schatzkiste …**: Jedes gefressene Wort wird gesammelt. Manche sind selten, manche legendär.
- **Bitte nicht stören**: Es versteckt sich und schweigt.
- **Einstellungen**: Größe, Redefreude, Pausen-Erinnerung, Bote, Jahreszeiten, Ruhemodus, Autostart.
- **Entwicklung / Accessoires**: Stufe, Bindung, Energie, Statistik.

## Was es so macht

- **Wohnt in einer Session.** Wechselst du den Tab, verschwindet es mit, beim Zurückwechseln sitzt
  es wieder da. Neugierige Pets laufen dir nach.
- **Reagiert** auf Fehler, Erfolge, Rückfragen, Commits und Pushes. Es liest laufend mit und
  kommentiert ab und zu, wie viel, hängt von Charakter und Einstellung ab.
- **Bote:** Ist eine längere Claude-Antwort fertig und du schaust gerade woanders hin, fliegt es zu
  deinem Mauszeiger und sagt dir Bescheid.
- **Frisst Wörter** wie bug, TODO, error, und seltene wie deadlock oder heisenbug.
- **Wird müde** vom Toben, schläft und träumt (Gedankenwolke). Abends gähnt es, nachts schläft es.
- **Wächst** mit eurer gemeinsamen Arbeitszeit: nach ca. 20 aktiven Stunden „jung“, nach ca. 120
  „erwachsen“. Je nach Arbeitsart bekommt es Accessoires (Bauhelm, Brille, Lupe).
- **Tagesmomente:** Mittag, Feierabend, Freitagnachmittag, dazu eine Pausen-Erinnerung nach 2 Stunden am Stück.
- **Jahreszeiten:** Herbstlaub, Schnee mit Wintermütze, Blüten und Pusteblumen fallen auf die Textzeilen.

## Datenschutz und Kosten

- Das Pet liest den **sichtbaren Text** im Windows Terminal (lokal, über die Windows-Bedienungshilfen).
  Dein **Eingabefeld liest es nie mit**.
- Für Sprechblasen schickt es einen **kurzen Ausschnitt** des sichtbaren Texts an **Haiku**, über
  `claude -p` mit deinem eigenen Abo. **Tokens, Passwörter, lange Schlüssel und E-Mail-Adressen werden
  vorher maskiert.** Der Aufruf läuft ohne deine Claude-Einstellungen, ohne Hooks, Tools oder MCP und
  ohne gespeicherte Session. Wie oft das passiert, bestimmst du über *Einstellungen → Redefreude*
  („Aus“ heißt: nur auf Wunsch). Dazu kommen ein Aufruf pro Tag fürs Tagebuch (nur Zähler wie
  „3 Commits, 2 Stunden“, kein Terminal-Text) und einmalige Aufrufe bei der Adoption.
- Für die Entwicklung zählt es lokal in deinen Claude-Code-Verläufen (`~/.claude/projects`) aktive
  Minuten, Werkzeug-Aufrufe und Prompts. Inhalte werden weder gespeichert noch verschickt.
- Ausflüge auf andere Fenster nutzen eine Bildanalyse rund um das Pet. Die Bilder bleiben im
  Arbeitsspeicher und werden nie gespeichert oder verschickt.
- **Ruhemodus:** Solange das Mikrofon benutzt wird (Teams/Zoom/Meet) oder eine Vollbild-App bzw.
  Präsentation läuft, ist das Pet unsichtbar und still. Auf Bildschirmfreigaben und Screenshots
  erscheint es nicht.

## Update und Deinstallation

- **Update:** `update.cmd` doppelklicken. Es holt die neue Version (`git pull`), zieht die Pakete nach
  und startet neu. Dein Pet bleibt erhalten.
- **Deinstallation:** `uninstall.cmd` beendet das Pet und entfernt den Autostart. Danach fragt es,
  ob auch dein Pet (mit Tagebuch und Schatzkiste) gelöscht werden soll. Dann den Ordner löschen.

Deine Daten liegen in `%LOCALAPPDATA%\claude-pet\` (Pet, Einstellungen, Tagebuch, Log).

## Probleme?

- **Pet nicht zu sehen:** Ist der Ruhemodus aktiv (Call, Vollbild, „Bitte nicht stören“)? Tray →
  „Pet zu mir holen“. Läuft Claude Code wirklich im **Windows Terminal** (nicht in VS Code o. Ä.)?
- **Kein Tray-Symbol:** `start.cmd` doppelklicken.
- **Keine Sprechblasen von Haiku:** Ist `claude` im PATH (`claude --version` in einem neuen Terminal)?
  Steht die Redefreude auf „Aus“?
- **Log:** `%LOCALAPPDATA%\claude-pet\pet.log`. Bei Fehlern bitte mitschicken.
