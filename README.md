# Lernraum

Lernraum ist eine lokale Lern-App für deine Module. Jede Modulakte bündelt Vorlesungen, Praktika, Dateien, Fragen und Lernfortschritt. Die Browseroberfläche und die Kommandozeile greifen auf denselben lokalen Server und dieselben Daten zu.

## Starten

Voraussetzung ist Python 3.12 oder neuer. Starte den Server aus dem Ordner `lernraum`:

```powershell
git clone https://github.com/Yasin-Erguen99/lernraum.git
cd lernraum
python -m pip install -r requirements.txt
python app.py --open
```

Unter Windows kannst du `Lernraum starten.cmd` doppelklicken oder das Startskript verwenden:

```powershell
.\start.ps1
```

Die App läuft unter <http://127.0.0.1:8765>. Beim normalen Start bleibt das Serverfenster geöffnet, während du die Browser-App oder CLI nutzt; Strg+C beendet es. Optional startet `.\start.ps1 -Background` einen Hintergrundserver, den du mit `Lernraum beenden.cmd` beenden kannst. Ein erneuter Start öffnet eine bereits laufende App. Die CLI erwartet standardmäßig genau diese lokale Adresse. Bei Bedarf kann sie über `--url` oder die Umgebungsvariable `LERNRAUM_URL` geändert werden.

## Daten und KI-Konfiguration

Lernraum speichert seine SQLite-Datenbank und die unveränderten Originaldateien im lokalen Ordner `.data/`. Erstelle regelmäßig ein Backup über die App oder speichere es mit `python cli.py backup download --output lernraum-backup.zip`.

Die KI-Anbindung ist optional. Sie wird serverseitig über eine lokale `.env`-Datei oder Umgebungsvariablen eingerichtet. Es wird kein Modell und kein Schlüssel vorausgesetzt. Trage das Modell ein, das du selbst verwenden möchtest.

Für OpenAI:

```dotenv
LERNRAUM_AI_PROVIDER=openai
LERNRAUM_AI_MODEL=<dein-modellname>
OPENAI_API_KEY=<dein-api-schluessel>
```

Für einen lokalen Ollama-Server:

```dotenv
LERNRAUM_AI_PROVIDER=ollama
LERNRAUM_AI_MODEL=<dein-installiertes-modell>
LERNRAUM_OLLAMA_URL=http://127.0.0.1:11434
```

Halte `.env` lokal und teile API-Schlüssel nicht in Fragen, Materialien oder exportierten Kontexten. Ohne vollständige KI-Konfiguration zeigt die App den Status als nicht konfiguriert an und führt keine vorgetäuschten KI-Antworten aus.

PDF-Text wird nur extrahiert, wenn das optionale Paket `pypdf` installiert ist:

```powershell
python -m pip install pypdf
```

Ein Scan ohne eingebetteten Text braucht OCR oder eine manuelle Transkription. Lernraum behauptet nicht, OCR auszuführen. Originalbilder und PDFs bleiben erhalten und können von einer separat verfügbaren KI gelesen werden.

## CLI

Die CLI ist Python-Standardbibliothek und benötigt keine zusätzlichen Pakete. Starte sie ebenfalls aus dem Ordner `lernraum`:

```powershell
python cli.py --help
```

Die Ausgabe ist standardmäßig JSON und eignet sich damit für Skripte und KI-Agenten. `--pretty` rückt JSON zur besseren Lesbarkeit ein. Fehler erscheinen auf stderr und liefern einen Fehlerstatus.

```powershell
python cli.py modules list
python cli.py modules add --name "Lineare Algebra" --code LA --semester "Wintersemester"
python cli.py units add --module <MODUL_UUID> --title "Vorlesung 1" --kind lecture --date 2026-10-12
python cli.py materials upload --module <MODUL_UUID> --unit <EINHEIT_UUID> --file "C:\Uni\Folien.pdf"
python cli.py materials list --module <MODUL_UUID>
python cli.py materials show <MATERIAL_UUID>
python cli.py materials download <MATERIAL_UUID> --output "C:\Uni\Folien.pdf"
python cli.py questions list --module <MODUL_UUID>
python cli.py progress --module <MODUL_UUID>
python cli.py backup download --output lernraum-backup.zip
```

Weitere Optionen zeigt `python cli.py <Befehl> --help`, zum Beispiel `python cli.py questions add --help`. Bei Freitext- und Bildfragen braucht `practice record` eine Selbsteinschätzung (`--rating 0`, `1` oder `2`). Bei Multiple Choice genügt der Optionsindex ab 0 oder der exakte Optionstext; der Server berechnet die Korrektheit.

## Freitext im Chat prüfen lassen

Bei Freitext- und Bildfragen kannst du deine Antwort in der Lernansicht über **Zur Prüfung speichern** einreichen. Sie bleibt zunächst offen und beeinflusst deinen Lernstand noch nicht. Danach kannst du im zugehörigen Codex-Chat **„Prüf meine offenen Antworten“** schreiben. Lernraum enthält selbst keinen Chat und startet beim Speichern keine automatische Prüfung: Die Prüfung beginnt erst, wenn du sie im Chat anfragst. Codex liest dann die offenen Antworten mit Frage, Musterlösung und verfügbarem Quellenmaterial und speichert eine begründete Rückmeldung. Dabei zählt der fachliche Sinn, nicht der genaue Wortlaut; passende Paraphrasen gelten. Fehlende Kernpunkte werden im Feedback benannt. Wenn die Quelle eine sichere Bewertung nicht trägt, wird die Unsicherheit kenntlich gemacht. Die Skala ist `0` = falsch, `1` = teilweise richtig und `2` = richtig. Danach fließt die Bewertung in den normalen Lernfortschritt ein. Die optionale KI-Anbindung der App bleibt ein eigener Weg.

Das lässt sich auch über die CLI erledigen. Antworten und Feedback aus Dateien werden als UTF-8 gelesen, auch wenn die Datei eine BOM enthält:

```powershell
python cli.py answers list --module <MODUL_UUID>
python cli.py answers show <ANTWORT_UUID>
python cli.py answers submit --question <FRAGE_UUID> --answer-file antwort.txt --duration 85
python cli.py answers review <ANTWORT_UUID> --rating 1 --feedback-file feedback.txt
python cli.py answers list --module <MODUL_UUID> --status reviewed
```

`answers list` zeigt standardmäßig nur offene Antworten. Mit `--unit <EINHEIT_UUID>` kannst du nach Vorlesung oder Praktikum filtern, und `--status all` zeigt offene sowie geprüfte Antworten. `answers show` liefert die Antwort, die Frage und die zugehörige Quelle. Nach der Prüfung kannst du mit `--feedback "..."` kurzen Text direkt übergeben; längeres Feedback passt in eine Datei. `answers review` kann jede Antwort nur einmal abschließen.

Bereits selbstbewertete Freitext- oder Bildantworten können ebenfalls im Chat nachgeprüft werden. Ihre Versuch-IDs stehen im Modulkontext. Mit `python cli.py answers review-attempt <VERSUCH_UUID> --rating 2 --feedback-file feedback.txt` wird die vorhandene Bewertung aktualisiert und die Rückmeldung unter **Antwortprüfungen → Geprüft** gespeichert. Es entsteht kein zusätzlicher Lernversuch. Ein späterer bewerteter Versuch derselben Frage behält seinen aktuellen Lernstand und Wiederholungstermin.

## KI mit Kontext und Originalen verwenden

Die CLI exportiert den App-Kontext inklusive Modul, Einheit, Fragen, deiner gespeicherten Lernantworten und Materialauszügen. Die Quell-IDs und Seitenangaben darin ermöglichen, erzeugte Fragen auf das konkrete Material zurückzuführen.

1. Exportiere den Kontext einer Einheit. Ohne `--unit` wird das ganze Modul verwendet.

   ```powershell
   python cli.py context --module <MODUL_UUID> --unit <EINHEIT_UUID> --output kontext.json
   ```

2. Wenn die Extraktion nicht reicht, lade über `materials list` die Material-ID nach und hole das Original mit `materials download <MATERIAL_UUID> --output <DATEIPFAD>`. Gib der externen KI `kontext.json` und die benötigten Originale. Bitte sie, nur belegte Inhalte zu verwenden und bei jeder Frage `source_material_id` sowie `source_page` aus dem Kontext zu übernehmen. IDs dürfen nicht erfunden werden.

3. Lass die KI eine JSON-Datei mit einem `questions`-Array erzeugen. Die Struktur in [`examples/questions.json`](examples/questions.json) zeigt Multiple Choice und Freitext. Ersetze die Modul- und Einheit-Platzhalter sowie alle `REPLACE_WITH_SOURCE_MATERIAL_UUID`-Platzhalter durch echte IDs aus dem Kontext und passe die Antworten an das Material an. Bei `questions import` setzt die CLI das Zielmodul aus `--module` und die Zieleinheit aus `--unit`; diese Werte ersetzen die Modul- und Einheit-Platzhalter beim Import.

4. Prüfe vor dem Import jede Frage, Lösung, Erklärung und Quellenangabe am Original. Danach importiere:

   ```powershell
   python cli.py questions import fragen.json --module <MODUL_UUID> --unit <EINHEIT_UUID> --reviewed
   ```

   `--reviewed` bestätigt, dass die Prüfung stattgefunden hat. Ohne diese Bestätigung bricht die CLI ab. Der Import wird als Ganzes validiert; ungültige Quell-IDs müssen anhand des Kontexts korrigiert werden.

5. Kontrolliere das Ergebnis mit `questions list --module <MODUL_UUID>`. Mit `questions export --module <MODUL_UUID> --output fragen-export.json` kannst du Fragen wieder als JSON sichern.

Die App kann außerdem selbst Fragen als Vorschlag erzeugen, wenn eine KI eingerichtet ist. Vorschläge werden erst gespeichert, nachdem du sie geprüft und importiert hast.


## Backup wiederherstellen

Beende den Server mit Strg+C. Entpacke das Backup-ZIP in einen neuen, leeren Ordner; darin liegen `lernraum.sqlite3` und `materials/`. Starte diesen Datenbestand mit `python app.py --data-dir "C:\Uni\WiederhergestellterLernraum" --open`. So bleibt der aktuelle Datenordner als zusätzliche Sicherung erhalten. API-Schlüssel sind nicht im Backup enthalten.

## Verhalten und Grenzen

Die App beginnt mit zwei leeren, umbenennbaren Modulakten. Sie enthält keine erfundenen Lernstände. Multiple Choice wird automatisch bewertet; Freitext und Bildfragen bekommen eine Musterantwort und werden durch deine Selbsteinschätzung oder eine von dir bestätigte KI-Rückmeldung bewertet. Lernfortschritt und Wiederholungszeitpunkte werden dauerhaft gespeichert.

PNG, JPEG, WebP und GIF können direkt in Bildfragen verwendet werden. Andere Originaldateien können gespeichert und heruntergeladen werden. Bei manuell ersetzten Materialtexten müssen dazugehörige Fragen erneut geprüft werden. Eine Datei, die als Bild einer Frage verwendet wird, kann erst nach Änderung oder Löschung dieser Frage entfernt werden.

Die optionale direkte KI-Anbindung verwendet [OpenAI Responses mit Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses) oder die [Ollama Generate API](https://docs.ollama.com/api/generate). Die ausgewählten Texte werden an den eingerichteten Dienst gesendet. Für OpenAI benötigst du deinen eigenen API-Schlüssel. Das Modell wird von dir festgelegt. Für große Unterlagen kann der externe CLI-Workflow genutzt werden; die direkte KI-Generierung begrenzt den Quellkontext auf 50.000 Zeichen.

## Entwicklung und Prüfung

Frontend ohne Build-Schritt, lokaler Python-HTTP-Server, SQLite. Tests aus dem übergeordneten Projektordner: `python -B -m unittest discover -s lernraum/tests -v`. Die KI-Tests simulieren Anbieterantworten und führen keine kostenpflichtigen Aufrufe aus. Manuelle Browsertests verwenden einen separaten Datenordner und Port, beispielsweise `python app.py --port 8766 --data-dir .test-data/ui`.
