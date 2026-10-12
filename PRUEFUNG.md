# Prüfung der ersten Version · 12. Oktober 2026

- 27 automatisierte Tests bestanden: Datenhaltung, Quellenvalidierung, transaktionaler Import, Bewertungen, Wiederholungen, lokale HTTP-/CLI-Schnittstelle, KI-Fehlerbehandlung und vollständige Backup-Wiederherstellung.
- JavaScript-Syntax und PowerShell-Startskripte geprüft. Der Windows-Start als Hintergrundprozess und der Beenden-Helfer wurden ausgeführt; der Beenden-Helfer wurde an einem getrennten Testprozess geprüft.
- Im Browser: Modul bearbeiten, Vorlesung anlegen, Material einer Einheit zuordnen, Datei hochladen, extrahierten Text lesen, Multiple-Choice-Frage mit Quelle erstellen, automatisch bewerten, Freitextfrage beantworten und selbst bewerten, Fortschritt und Wiederholungsdatum prüfen.
- PDF: Zwei Seiten mit korrekt getrennten Texten ausgelesen und im Materialdialog angezeigt. Das unveränderte Original ist zugänglich.
- Bildfrage: PNG gespeichert, Bildfrage angelegt, Darstellung des tatsächlichen Bildes im Browser bestätigt (600 × 260 Pixel).
- Mobile Ansicht bei 390 Pixel Breite: kein horizontaler Seitenüberlauf; Menü und Navigation geprüft.
- Produktiver Datenbestand separat geprüft: zwei leere Modulakten, keine Testmaterialien oder erfundenen Lernantworten. CLI als eigener Prozess geprüft. KI-Kontext enthält ausschließlich Antworten des gewählten Moduls bzw. der gewählten Einheit.

Die Tests für OpenAI und Ollama verwenden simulierte Anbieterantworten. Es wurden keine kostenpflichtigen KI-Anfragen ausgeführt. Direkte KI-Nutzung benötigt die Einrichtung gemäß README; Bilder und reine Scans benötigen eine manuelle Transkription oder das Lesen des Originals durch eine externe KI. Es ist kein OCR-Dienst eingebaut.

## Ergänzung: Freitextprüfung im Codex-Chat

- 46 automatisierte Tests bestanden, einschließlich der bisherigen 27 Tests. Neue Prüfungen decken offene Antworten ohne Bewertung, Übernahme bestehender Datenbanken, einmalige atomare Bewertung, verspätete Prüfungen ohne Überschreiben eines neueren Lernstands, Modul-/Einheitenfilter, Quellenzugriff, CLI und Backup-Wiederherstellung ab.
- Im Browser mit separater Testdatenbank: leere Eingabe abweisen, Freitext zur Prüfung speichern, Session abschließen, offenen Status ohne falsche Bewertung anzeigen, Antwort mit Quelle über die CLI lesen und bewerten, Rückmeldung unter „Geprüft“ anzeigen.
- Beispielprüfung: Eine richtige Risikowert-Berechnung ohne die zusätzlich geforderte Erklärung erhält „Teilweise richtig“ und begründetes Feedback. Offene Antworten bleiben außerhalb der Antwortsicherheit; bewertete Antworten verwenden die bestehenden Wiederholungsregeln.
- Die direkte API-Anbindung bleibt optional. Speichern startet keine automatische Prüfung und keine Verbindung zum ChatGPT-Konto. Die Prüfung erfolgt nach ausdrücklicher Anfrage im zugehörigen Codex-Chat.

## Ergänzung: Nachprüfung vorhandener Selbstbewertungen

- 52 automatisierte Tests bestanden. Die Nachprüfung bewahrt Versuchs-ID, Antwort, ursprüngliches Datum, Dauer und Anzahl der Lernversuche. Eine korrigierte Bewertung zählt keine zusätzliche Wiederholung; ältere Antworten überschreiben den Stand neuerer Versuche nicht.
- CLI- und HTTP-Integration der Nachprüfung getestet, einschließlich Schutz gegen doppelte Bewertung. Rückmeldungen vorhandener Antworten erscheinen in der geprüften Antwortliste; die Warteschlange enthält weiterhin ausschließlich ausdrücklich zur Prüfung gespeicherte Antworten.
- Speicherung und Anzeige einer vollständigen Rückmeldung in der laufenden App im Browser bestätigt.
