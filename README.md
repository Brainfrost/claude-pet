# claude-pet

Ein Desktop-Pet, das auf dem Text deiner Claude-Code-Sessions im Windows Terminal lebt:
jede sichtbare Textzeile ist eine Plattform, auf der es läuft, sitzt, schläft und herumspringt.

## Starten

```
start.cmd
```

Beenden und Debug-Ansicht über das Tray-Symbol. Log: `%LOCALAPPDATA%\claude-pet\pet.log`.

Einrichtung (einmalig):

```
python -m venv .venv
.venv\Scripts\python -m pip install PyQt6 comtypes
```

## Wie es funktioniert

- `terminal.py` – liest Windows Terminal per UI Automation (~15x/s): Tabs inkl. Zustand aus dem
  Titel (✳ = untätig, Spinner = arbeitet) und den sichtbaren Text mit Pixel-Positionen.
- `world.py` – macht daraus Plattformen (Textstücke, Lücken ab 3 Leerzeichen sind Löcher) und
  erkennt Scrollen, damit das Pet mit seiner Zeile mitfährt.
- `pet.py` – Physik und Verhalten (laufen, springen, fallen, sitzen, schlafen, Reaktionen).
- `ui.py` – transparentes Pet-Fenster, Maus (hochheben/werfen, anstupsen, streicheln), Tray.

Keine Hooks, keine Änderungen an Claude-Code-Einstellungen.

## Maus

- **Ziehen** = hochheben, **loslassen in Bewegung** = werfen
- **Klick** = anstupsen (weckt es auf)
- **Hin und her darüberfahren** = streicheln

## Figur und Charakter

Beim ersten Start wird eine der 8 Figuren aus `design/pet-data.json` ausgewürfelt (Entwürfe:
`design/claude-pet-entwuerfe.html`). Jede Figur hat einen Lieblingscharakter (50 %), sonst einer der
anderen. Steckbrief: `%LOCALAPPDATA%\claude-pet\profile.json`. Tray → „Neues Pet auswürfeln“.

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
- **Sprechblasen** über Haiku (`claude -p --model haiku`, dein Abo) mit einem Ausschnitt des sichtbaren
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
  Zeilen, nur seit der Geburt des Pets): XP = Tool-Aufrufe + 3 × Eingaben + 10 × Sessions.
- **Wachstum:** Baby (im Ei) → jung ab 400 XP → erwachsen ab 2500 XP (Figur wird größer).
- **Accessoires** nach Arbeitsart: Bauhelm ab 150 Bash/PowerShell-Aufrufen, Brille ab 25 Web-Recherchen,
  Lupe ab 60 Suchen (Grep/Glob). Im Tray unter „Accessoires“ an-/abschaltbar.
- **Tricks:** Doppelsprung (ab jung: springt höher, legt in der Luft nach), Purzelbaum (ab Bindung 40),
  Weitsprung (erwachsen: neugierige/verspielte Pets gehen auf Abenteuer zu anderen Fenstern).
- **Bindung** (0–100): Streicheln, Anstupsen, Anhängen und gemeinsame Zeit erhöhen sie, Werfen senkt sie
  (außer beim verspielten), lange Abwesenheit kostet etwas. Höhere Bindung → hängt sich öfter an die Maus.
- **Stimmung** (0–100): Erfolge und Streicheln heben, Fehler und Werfen senken; pendelt sich bei 60 ein.
  Schlechte Laune → sitzt mehr herum; gute Laune → springt mehr. Fließt auch in Haikus Sprüche ein.
- **Andere Fenster erkunden:** Oberkanten anderer Fenster sind Plattformen (verdeckte Stellen ausgenommen,
  maximierte Fenster ohne Platz darüber ausgenommen). Terminal minimiert → das Pet fällt heraus und
  erkundet; kommt das Terminal zurück, springt es je nach Charakter früher oder später heim.
- Tray → „Entwicklung“ zeigt Stufe, XP, Bindung, Stimmung, Statistik und Tricks.

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
