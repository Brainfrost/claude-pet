# claude-pet

Ein Desktop-Pet, das auf dem Text deiner Claude-Code-Sessions im Windows Terminal oder im Terminal von
VS Code/Cursor lebt:
jede sichtbare Textzeile ist eine Plattform, auf der es läuft, sitzt, schläft und herumspringt.

**Installieren:** siehe [ANLEITUNG.md](ANLEITUNG.md) – `git clone https://github.com/Brainfrost/claude-pet.git`,
dann `install.cmd` (Windows) bzw. `install.command` (Mac) doppelklicken, fertig.
(`update` aktualisiert, `uninstall` entfernt Autostart, Erweiterung und auf Wunsch die Daten;
Mac zusätzlich `start.command` und `diagnose.command`.)

> Inoffizielles Hobbyprojekt, nicht mit Anthropic verbunden. „Claude“ und „Claude Code“ sind Marken
> von Anthropic. Das Pet nutzt dein eigenes Claude Code (`claude -p`, Abo oder API-Key) und schickt nur maskierte
> Ausschnitte an Haiku. Lizenz: [MIT](LICENSE).

## Starten

`start.cmd` (oder `run.pyw` doppelklicken) – startet ohne Konsolenfenster; mit Autostart läuft es ab
dem Windows-Login automatisch. Beenden über das Tray-Symbol.

Einrichtung (einmalig):

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Aufbau

| Modul | Aufgabe |
|---|---|
| `terminal.py` | liest Windows Terminal per UI Automation (8×/s): Tabs (✳ = untätig, Spinner = arbeitet) und sichtbaren Text mit Pixel-Positionen; wählt die Quelle (zuletzt aktives Terminal-Programm) |
| `vscode.py` | VS Code/Cursor: Terminal-Flächen und Titel per UIA (`xterm-screen`, `xterm-helper-textarea`), Text aus `streams.py`, Ausrichtung am Cursor |
| `streams.py` / `emulator.py` | lokaler Kanal (Named Pipe/Unix-Socket) für die Begleit-Erweiterung, pyte-Emulator je Terminal |
| `vsix.py` + `vscode-extension/` | Begleit-Erweiterung: liest `claude`-Ausgabe per Shell-Integration; bauen/installieren ohne Node |
| `world.py` | Plattformen: Textstücke, Pane-Boden, Fensterkanten, Bildanalyse-Kanten; erkennt Scrollen |
| `vision.py` | Bildanalyse: waagrechte Kanten in beliebigen Fenstern (GDI-Aufnahme, eigener Hintergrund-Thread) |
| `pet.py` | Physik und Bewegung (laufen, springen, klettern, Tricks) |
| `brain.py` | Charakter: welche Session, Tab-Wechsel, Maus-Verhalten |
| `reactions.py` | erkennt Ereignisse im Text/Tab-Titel, liest laufend mit |
| `speech.py` / `personas.py` | Haiku-Sprüche + Aktionen, Grund- und individuelle Persönlichkeit |
| `growth.py` / `stats.py` | Entwicklung: XP aus den Transcripts, Stufen, Accessoires, Tricks, Bindung, Stimmung |
| `creatures.py` | rendert die Figuren aus `design/pet-data.json` |
| `windows.py` | Fenster: Pet, Sprechblase, Reiter-Effekt, Jahreszeiten, Traumwolke, Bug-Jagd, Entwickler-Ansicht |
| `seasons.py` | Laub/Schnee/Blüten fallen auf Textzeilen und bleiben liegen |
| `diary.py` / `book.py` | Tagebuch (Zähler, Haiku-Einträge, Wochenrückblick) und das Lesefenster |
| `dreams.py` | Traumbilder beim Schlafen |
| `treasure.py` | Schatzkiste: Futterwörter mit Seltenheitsstufen |
| `bughunt.py` | Mini-Spiel Bug-Jagd |
| `daily.py` | Tageszeit, Tagesmomente, Pausen-Messung |
| `tray.py` | Tray-Menü |
| `controller.py` | verbindet alles, Spielschleife |
| `settings.py` / `quiet.py` / `profile.py` | Einstellungen + Autostart (Registry bzw. LaunchAgent), Ruhemodus, Steckbrief |
| `osapi.py` → `winapi.py` / `macapi.py` | Betriebssystem-Schicht: Fensterliste, Vordergrund, Maus, Overlays, Leerlauf, Einzelinstanz |
| `macax.py` | Mac: Terminals in VS Code/Cursor über die Bedienungshilfen (AX) finden |
| `gdi.py` | Windows: Bildschirmaufnahme für `vision.py` (Mac: keine – bräuchte „Bildschirmaufnahme“) |
| `paths.py` / `diagnose.py` | Datenordner je System; Diagnose „was sieht das Pet?“ (`python -m claude_pet.diagnose`) |

Keine Hooks, keine Änderungen an Claude-Code-Einstellungen.

### VS Code / Cursor

xterm.js zeichnet auf ein Canvas, UIA sieht dort keinen Text. Deshalb:
- **Geometrie/Zustand per UIA:** `xterm-screen` = Textfläche, `xterm-helper-textarea` = Eingabefeld am
  Cursor; sein Name enthält den Terminal-Titel (✳/Spinner).
- **Text über die Begleit-Erweiterung** (`vscode-extension/`): `onDidStartTerminalShellExecution` +
  `execution.read()` für `claude`-Aufrufe, per Named Pipe `\\.\pipe\claude-pet-<user>` an `streams.py`;
  dort spielt ein pyte-Emulator je Terminal den Strom nach (Zellgröße = Fläche / Größe beim Start).
- **Ausrichtung:** Der Strom beginnt mitten auf dem Bildschirm; der Emulator wird an der Cursorzeile
  (Eingabefeld) ausgerichtet. Größenänderungen meldet die API nicht – die Größe kommt aus dem UIA-Rechteck.
- **Grenzen:** `claude`-Aufrufe vor dem Start der Erweiterung sind unsichtbar (die letzten 256 KB je
  Terminal werden aber nachgeliefert, wenn das Pet später startet); Hochscrollen wird nicht erkannt.
- Erweiterung bauen/installieren: `.venv\Scripts\python -m claude_pet.vsix` (`--remove` entfernt sie).

### macOS

- Nur VS Code/Cursor (kein Windows Terminal; Terminal.app/iTerm2 noch nicht). Text wie oben über die
  Erweiterung (Unix-Socket `$TMPDIR/claude-pet-<user>`).
- Geometrie über die **Bedienungshilfen** (`macax.py`): Electron per `AXManualAccessibility` einschalten,
  Eingabefelder per `AXUIElementsForSearchPredicate` (Notweg: Baumsuche), Fläche über `AXDOMClassList`.
  Fensterliste per `CGWindowListCopyWindowInfo` (keine Freigabe nötig).
- **Keine Bildschirmaufnahme** (monatliche Nachfrage von macOS): keine Bildanalyse-Ebenen.
- Gestartet wird immer über launchd (`com.claude-pet`), damit die Freigabe an Python hängt und nicht
  am Terminal, aus dem installiert wurde. Kein Dock-Symbol (Accessory), Menüleisten-Symbol.
- `tests/test_mac.py` prüft den Mac-Zweig mit nachgebautem macOS (läuft auch unter Windows).
- Nicht auf echter Hardware getestet: `diagnose.command` liefert die Infos dafür.

## Entwickeln

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest tests        # 104 Tests, ohne Terminal/Bildschirm (Qt offscreen)
.venv\Scripts\python -m pyflakes claude_pet tests
```

- Tests bauen Terminal-Snapshots künstlich (`tests/conftest.py: make_snapshot`) und simulieren Pet +
  Gehirn ohne Fenster, u.a. „verschwindet mit dem Tab und sitzt beim Zurückwechseln wieder dort“.
- **Entwickler-Ansicht** (Tray): zeigt über allen Bildschirmen die erkannten Ebenen (blau Terminal-Text,
  rot Pane-Boden, gelb Fensterkanten, grün Bildanalyse), die Tabs und Zustand/Ziel/Laune des Pets;
  schaltet das Log auf ausführlich.
- **Log:** `%LOCALAPPDATA%\claude-pet\pet.log`, rotiert (3 × 1 MB). Ausführliche Statuszeilen nur mit
  Entwickler-Ansicht oder `set CLAUDE_PET_DEBUG=1`.
- Daten: `%LOCALAPPDATA%\claude-pet\` – `profile.json` (Pet), `settings.json`, `stats_state.json`.

## Maus

- **Ziehen** = hochheben, **loslassen in Bewegung** = werfen
- **Klick** = anstupsen (weckt es auf)
- **Hin und her darüberfahren** = streicheln

## Adoption, Figur und Charakter

Beim ersten Start öffnet sich das **Adoptionsfenster** (`claude_pet/adoption.py`): alle Figuren aus
`design/pet-data.json` zur freien Auswahl. Jede bekommt beim Öffnen einen zufälligen Charakter und beim
Anschauen eine von Haiku erfundene Persönlichkeit – einfache Auswahl, trotzdem nie ganz gleiche Pets.
Namen vergeben, adoptieren. **Figur, Charakter, Persönlichkeit und Name bleiben danach für immer.** Jede Figur hat einen Lieblingscharakter (50 %), sonst einer der anderen.
Steckbrief: `%LOCALAPPDATA%\claude-pet\profile.json`; frühere Pets liegen in `…\claude-pet\archiv\`.
Fürs Entwickeln: mit `set CLAUDE_PET_DEV=1` gibt es im Tray „Pet archivieren und neu adoptieren“.

| Charakter | Verhalten |
|---|---|
| faul | langsam, schläft lange, zieht sich in untätige Sessions (✳) zurück |
| neugierig | folgt dir in jeden Tab und zum Mauszeiger, schaut sich die neueste Ausgabe an |
| verspielt | schnell, sprunghaft, versteckt sich zum Spaß in Tabs, hängt sich an die Maus |
| ängstlich | meidet arbeitende Sessions, flieht vor schnellen Mausbewegungen, schwitzt |

Tabs: Das Pet wohnt in einer Session. Wechselst du den Tab, springt es (außer neugierig) an den
Reiter seiner Session und schlüpft hinein; öffnest du seinen Tab, kommt es unter dem Reiter hervor.
Lässt du es auf einem Reiter los, zieht es in diese Session.

## Reaktionen und Sprechblasen

- **Session-Zustand** aus dem Tab-Titel: Claude fertig (✳) → freut sich; Claude fängt an → schaut.
- **Neuer Text** im sichtbaren Tab: Fehler (`Error:`, Traceback, `failed`, ✗), Erfolg (✓, `passed`,
  „erfolgreich“), Rückfrage/Freigabe („Do you want to…“, `❯ 1. Yes`). Zeilen aus Code-Listings werden ignoriert.
- **Sprechblasen** über Haiku (`claude -p --model haiku`, dein Abo oder API-Key) mit einem Ausschnitt des sichtbaren
  Texts; Tokens, Passwörter, lange Schlüssel und E-Mail-Adressen werden vorher maskiert. Aufruf ohne
  deine Einstellungen/Hooks, ohne Tools/MCP, ohne Session-Speicherung (`--setting-sources ""`,
  `--no-session-persistence`, `--tools ""`, `--strict-mcp-config`).
- **Laufend mitlesen:** Neuer Inhalt (ohne Claude-Code-Bedienelemente) wird gesammelt; ab ~500 Zeichen
  oder wenn Claude fertig ist, reagiert das Pet auf den Inhalt.
- Haiku antwortet mit JSON `{"sagen", "aktion", "ziel"}`. Aktionen: hüpfen, freuen, tanzen, erschrecken,
  verstecken (in einem anderen Tab), hinsetzen, einschlafen, umschauen, **hinlaufen** (zu einem Wort im Text).
- **Persönlichkeit:** Jede Figur hat eine feste Grundpersönlichkeit (`claude_pet/personas.py`). Beim
  Auswürfeln erfindet Haiku zusätzlich eine einmalige Persönlichkeit (Marotte, Lieblingsding, Abneigung,
  Ausruf), die im Steckbrief gespeichert wird – jedes Pet ist einzigartig. Tray-Tooltip zeigt sie an.
- Grenzen pro Stunde: faul 5, ängstlich 10, verspielt 18, neugierig 24 (plus Mindestabstand); neugierig
  und verspielt plaudern gelegentlich auch ohne Anlass. Anstupsen/Streicheln/Werfen → vorgefertigte Sprüche (gratis).
- Tray → „Was denkst du gerade?“ holt sofort einen Kommentar.

## Entwicklung (Etappe 4)

- **Fortschritt** aus deinen Claude-Code-Transcripts (`~/.claude/projects`, nur lokal gelesen, nur neue
  Zeilen, nur seit der Adoption). Maßstab sind **aktive Minuten** (jede Minute mit Claude-Aktivität zählt
  einmal, höchstens 8 h pro Tag) – robust gegen Automatisierungs-Tage. Subagents zählen nur als Zeit.
- **Wachstum** (kalibriert an echten Daten, ~4 aktive h pro Arbeitstag): Baby (im Ei) → jung nach 20 aktiven
  Stunden (~1–2 Wochen) → erwachsen nach 120 Stunden (~2 Monate). Die Figur wird größer.
- **Accessoires** nach Arbeitsart (nur eigene Sessions): Bauhelm ab 3000 Bash/PowerShell-Aufrufen,
  Brille ab 600 Web-Recherchen, Lupe ab 800 Lese-/Suchaufrufen – je ein bis drei Wochen. Im Tray unter
  „Accessoires“ an-/abschaltbar bzw. mit Fortschritt.
- **Tricks:** Doppelsprung (ab jung: springt höher, legt in der Luft nach), Purzelbaum (ab Bindung 40),
  Weitsprung (erwachsen: neugierige/verspielte Pets gehen auf Abenteuer zu anderen Fenstern).
- **Bindung** (0–100): wächst langsam – durch Streicheln, Anstupsen, Anhängen höchstens 8 Punkte pro Tag,
  dazu 0,5 pro aktiver Stunde gemeinsamer Arbeit. Werfen senkt sie (außer beim verspielten), lange
  Abwesenheit kostet etwas. Höhere Bindung → hängt sich öfter an die Maus; ab 40 gibt's den Purzelbaum.
- **Energie** (0–100): Laufen, Springen, Ballspielen, Ausflüge und Wachsein kosten Energie; Sitzen,
  Schlafen und Verstecken im Tab laden auf (abends/nachts wird man schneller müde). Unter 40 ist das Pet
  müde: langsamer, kaum Sprünge, setzt sich öfter, gähnt, jagt keinen Ball, schaut bei der Maus nur hin.
  Fast leer -> Nickerchen, bis es wieder fit ist. Verspielte toben ~½ Stunde, bevor sie müde werden.
  Die Energie wird gespeichert; Zeit, in der das Pet aus ist, gilt als Erholung.
- **Stimmung** (0–100): Erfolge und Streicheln heben, Fehler und Werfen senken; pendelt sich bei 60 ein.
  Schlechte Laune → sitzt mehr herum; gute Laune → springt mehr. Fließt auch in Haikus Sprüche ein.
- **Andere Fenster erkunden:** Oberkanten anderer Fenster sind Plattformen (verdeckte Stellen ausgenommen,
  maximierte Fenster ohne Platz darüber ausgenommen). Terminal minimiert → das Pet fällt heraus und
  erkundet; kommt das Terminal zurück, springt es je nach Charakter früher oder später heim.
- Tray → „Entwicklung“ zeigt Stufe, XP, Bindung, Stimmung, Statistik und Tricks.

## Spielereien

- **Ball** (Tray → „Ball werfen“): hüpft über Textzeilen, Fensterkanten und erkannte Ebenen, rollt über
  Kanten. Das Pet jagt ihm nach (verspielt immer, neugierig meist, ängstlich manchmal, faul selten),
  schnappt ihn und bringt ihn auf die Ebene unter deinem Mauszeiger. Du kannst den Ball greifen und werfen.
  Nach 3 Minuten ohne Beachtung wird er weggeräumt (oder Tray → „Ball wegräumen“).
- **Wörter fressen:** „bug“, „TODO“, „FIXME“, „error“, „Fehler“ (und die Schatzkisten-Wörter) im Text – das Pet läuft hin und knabbert
  das Wort an (der vordere Teil verschwindet kurz unter einem Biss mit Krümeln). Neues Futter im Text
  macht es schneller hungrig. Zähler im Tray unter „Entwicklung“.
- **Tag und Nacht:** abends gähnt es, nachts schläft es fest und lange, morgens (5–10 Uhr) begrüßt es
  dich einmal am Tag. Haiku weiß die Tageszeit.
- **Pausen-Erinnerung:** misst über die letzte Maus-/Tastatureingabe (`GetLastInputInfo`), wie lange du am
  Stück arbeitest (Pause = 5 Min. ohne Eingabe). Nach 2 Stunden (einstellbar: 1–2,5 h) stupst es dich an,
  danach alle 30 Min.; nach einer Pause begrüßt es dich. Im Ruhemodus still.
- **Git-Momente:** `git commit` / `git push` in einer Session (Befehl oder Ausgabe, nicht Fließtext) →
  Tänzchen mit Konfetti und ein Spruch.

## Ebenen in allen Fenstern (Bildanalyse)

- Ist das Pet außerhalb des Terminals unterwegs, wird ~3× pro Sekunde ein Ausschnitt (1100 × 900 px)
  rund ums Pet aufgenommen und auf waagrechte Kanten untersucht (`claude_pet/vision.py`): Textzeilen
  (bis zur Oberkante der Schrift hochgezogen), Rahmen, Eingabefelder, Buttons, Bildkanten. Fotos/Rauschen
  werden über den Kantenanteil ausgefiltert. Bilder bleiben im Speicher – nie gespeichert, nie verschickt.
- Das Pet geht je nach Charakter von selbst auf **Ausflüge** (verspielt am häufigsten, faul kaum; mit
  Weitsprung doppelt so oft): Es sucht per Bildanalyse eine Kante auf einem anderen Bildschirm und
  springt hin. Tray → „Ausflug machen!“ löst einen Ausflug sofort aus.
- Im sichtbaren Terminal gilt weiter die genaue Textwelt (UI Automation).

## Ressourcen

Gemessen: Pet ~74 MB RAM, ~8 % eines CPU-Kerns (adaptive Bildrate 60 → 10 fps je nach Zustand,
Terminal-Abfrage 8×/s bzw. 4×/s wenn versteckt/draußen). Haiku läuft bei Anthropic; lokal startet pro
Spruch kurz ein `claude`-Prozess (~330 MB für ~2,5 s).

## Tabs (überarbeitet nach Feedback)

- Das Pet gehört zum Inhalt seines Tabs: Wechselst du weg, ist es sofort mit verschwunden; kommst du
  zurück, sitzt es wieder genau dort (gleiche Zeile, gleicher Zustand). Ist der Platz inzwischen
  weggescrollt, klettert es stattdessen aus dem Reiter. Neugierige (und manchmal verspielte) Pets
  bleiben bei dir und fallen auf den Text des neuen Tabs.
- Geht es selbst in einen Tab: ducken → hochspringen → kurz am Reiter baumeln → hineinziehen (verschwindet
  hinter der Reiter-Kante); der Reiter wackelt, beim Verschwinden gibt's ein Staubwölkchen.

## Alltag

- **Autostart** über `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` → `run.pyw` (Tray → Einstellungen).
- **Ruhemodus:** Versteckt und stumm, solange ein Programm das Mikrofon benutzt (Teams/Zoom/Meet-Call)
  oder eine Vollbild-App/Präsentation läuft; „Bitte nicht stören“ im Tray schaltet ihn manuell.
- **Einstellungen** (Tray, gespeichert in `%LOCALAPPDATA%\claude-pet\settings.json`): Größe (klein/normal/
  groß), Redefreude (aus/wenig/normal/viel – skaliert Chance und Stundengrenze), Sprechblasen an/aus,
  Ruhemodus bei Calls / bei Vollbild, Mit Windows starten.

## Etappen

1. ✅ Overlay, Text als Boden, Physik, Maus
2. ✅ Charakter (faul, neugierig, verspielt, ängstlich) und Session-Wahl über die Tabs
3. ✅ Reaktionen auf Session-Zustand und Textinhalt, Sprechblasen über Haiku
4. ✅ Entwicklung (Wachstum, Accessoires, Tricks, Bindung, Stimmung), andere Fenster erkunden
5. ✅ Ideen-Paket: Bote, Tagesmomente, Jahreszeiten, Tagebuch, Träume, Schatzkiste, Bug-Jagd, Installer

## Ideen-Paket

- **Bote:** Ist eine Session nach mindestens 20 s Arbeit fertig und du bist in einem anderen Tab oder
  Fenster, fliegt das Pet zum Mauszeiger (auch auf andere Bildschirme), hängt sich an und sagt, welcher
  Tab fertig ist. Höchstens alle 30 s; abschaltbar.
- **Tagesmomente:** einmal am Tag Mittag (11:45–13:00), Feierabend (Mo–Fr 17:00–18:30) und
  Freitagnachmittag (14–17 Uhr), nur wenn du gerade am Rechner bist.
- **Jahreszeiten:** Herbst Laub, Winter (Dez–Feb) Schnee plus rote Mütze, Frühling Blüten, Sommer
  Pusteblumen-Samen. Teilchen landen auf Textzeilen, scrollen mit, verwelken/schmelzen nach 1–4 Min.,
  das Pet wirbelt sie beim Laufen auf. Höchstens 40 fallende Teilchen, eigenes klickdurchlässiges Overlay.
- **Tagebuch** (`%LOCALAPPDATA%\claude-pet\tagebuch.json`): zählt Minuten, fertige Antworten, Fehler,
  Commits, Pushes, Gefressenes, Ball, Streicheln, Nickerchen, Botengänge, Bug-Jagd-Käfer, Träume.
  Ab 18 Uhr schreibt Haiku den Tageseintrag in der Stimme des Pets (nur aus den Zählern, vergessene Tage
  der letzten Woche werden nachgeholt), freitags ab 16 Uhr den Wochenrückblick. Tray → Tagebuch.
- **Träume:** Schläft das Pet, steigt alle 15–30 s eine Gedankenwolke mit Pixelbild auf – gewichtet
  nach dem Tag (Ball, Käfer, Commits …), der Figur (Katze → Fisch) und dem Charakter.
- **Schatzkiste:** 23 Wörter in vier Stufen (gewöhnlich, selten, episch, legendär). Alle sind Futter;
  das Pet bevorzugt Seltenes, neue seltene Funde werden mit Konfetti gefeiert. Tray → Schatzkiste.
- **Bug-Jagd** (Tray): 30 s krabbeln Käfer über die Zeilen des Panes, springen zwischen Zeilen. Klick
  (mit großzügigem, unsichtbarem Trefferhof) zerquetscht sie, das Pet jagt mit (Tempo je Charakter,
  Jagdfieber: mindestens 60 Energie, Spiel kostet nur ¼ Energie). Punktestand oben rechts, Teamrekord.
- **Installer:** `install.ps1` prüft Windows Terminal, claude-CLI und Python ≥ 3.11 (bietet winget an),
  legt `.venv` an, installiert Pakete, startet das Pet (das trägt den Autostart selbst ein).
