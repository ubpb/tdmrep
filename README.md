# tdmrep

Schreibt einen Rechtevorbehalt für Text and Data Mining in PDF-Dateien, von überall auf der Kommandozeile:

```
$ tdmrep -p https://digital.ub.uni-paderborn.de/policies/tdm.json -i dissertation.pdf
{"tool":"tdmrep","version":"2.1.0","status":"written","sha256_before":"f5b51ea5…","sha256_after":"ec961f7f…", …}
```

Der Vorbehalt landet in den XMP-Metadaten des Dokuments und begleitet die Datei damit auch dann, wenn sie heruntergeladen und andernorts weitergegeben wird. Seiten, Text, Schriften und Abbildungen bleiben unverändert.

`examples/beispiel.pdf` ist eine kleine Datei zum Ausprobieren.

## So funktioniert es

1. Die Datei wird mit **pikepdf** (auf Basis von qpdf) geöffnet und ihr XMP-Paket gelesen.
2. `tdm:reservation` und `tdm:policy` werden im Namensraum `http://www.w3.org/ns/tdmrep/` **ergänzt** — vorhandene Angaben wie `dc:creator`, `xmp:CreateDate` oder die PDF/A-Kennzeichnung bleiben erhalten.
3. Weil `tdm` kein Standard-XMP-Schema ist, kommt eine **PDF/A Extension Schema Description** dazu. Ohne sie beanstandet ein PDF/A-Validator die Datei.
4. Gespeichert wird ohne neue Objektströme, damit eine PDF/A-1-Datei konform bleibt. Nach dem Schreiben prüft das Programm, ob der Metadatenstrom unkomprimiert geblieben ist, und schreibt das Ergebnis ins Protokoll.

Grundlage ist das [TDM Reservation Protocol](https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/) des W3C.

## Voraussetzungen

- **Python** ab 3.9: `brew install python`
- **pikepdf** und **lxml** — legt `install.sh` bei Bedarf in einer eigenen Umgebung neben dem Programm an, ohne das System-Python zu verändern
- Bash, wie sie macOS mitbringt (auch unter Linux lauffähig)

## Installation

1. Den Ordner `tdmrep` an seinen festen Platz legen, etwa `~/Code/Tools/tdmrep`. Das Skript findet seine Dateien relativ zu sich selbst, auch über einen Link.
2. Im Ordner aufrufen:

   ```
   $ ./install.sh
   ```

   Das legt `~/.local/bin/tdmrep` als Link auf `bin/tdmrep` an, sorgt für die Python-Module, führt einen Selbsttest an der Beispieldatei aus und sagt, falls `~/.local/bin` noch nicht im PATH liegt, welche Zeile in `~/.zshrc` gehört. Ein anderes Zielverzeichnis: `./install.sh /usr/local/bin`. Sind pikepdf und lxml schon im System vorhanden, wird keine eigene Umgebung angelegt; `--no-venv` unterbindet sie ganz.

**Deinstallieren:** `./install.sh --uninstall` entfernt den Link und die Umgebung; danach kann der Ordner gelöscht werden.

**Verschieben:** Ordner verschieben und `./install.sh` erneut aufrufen, der Link wird ersetzt.

## Aufruf

```
tdmrep [Optionen] DATEI.pdf [DATEI.pdf ...]
```

| Option | Wirkung |
|---|---|
| `-o`, `--output PFAD` | Ziel-PDF (bei einer Eingabedatei) oder Zielverzeichnis |
| `-i`, `--in-place` | Quelldatei überschreiben |
| `-r`, `--reservation 0\|1` | zu setzender Wert, Standard `1` |
| `-p`, `--policy URL` | URL der Rechte-Policy; `-p ""` lässt sie weg |
| `--on-conflict report\|overwrite` | Verhalten bei vorhandenen Angaben, Standard `report` |
| `--no-pdfa-ext` | ohne PDF/A Extension Schema Description |
| `-n`, `--dry-run` | nur prüfen, nichts schreiben |
| `--log DATEI` | Protokollzeile zusätzlich an diese Datei anhängen |
| `-q`, `--quiet` | nur Konflikte und Fehler ausgeben |
| `-h`, `--help` / `-v`, `--version` | Hilfe / Version |

Ohne `-o` oder `-i` schreibt das Programm nichts — das ist Absicht, damit eine Originaldatei nicht versehentlich überschrieben wird.

Beispiele:

```
$ tdmrep -p https://…/tdm.json -o diss_mit-vorbehalt.pdf diss.pdf
$ tdmrep -i diss.pdf                        # Policy aus der Voreinstellung
$ tdmrep -n diss.pdf                        # nur ansehen, was geschähe
$ tdmrep -p https://…/tdm.json -o ausgabe/ eingang/*.pdf
$ tdmrep -r 0 -i freigegeben.pdf            # ausdrückliche Freigabe
```

Die Policy-URL ist voreingestellt auf
`https://data.ub.uni-paderborn.de/policies/digital.ub/tdm.json`. Es gilt: `-p` schlägt `TDMREP_POLICY`, und `TDMREP_POLICY` schlägt die Voreinstellung. `-p ""` schreibt den Vorbehalt ohne Verweis auf eine Policy. Die Voreinstellung steht als `DEFAULT_POLICY` am Anfang von `share/tdmrep/tdmrep.py` und ist dort zu ändern, wenn sich die Adresse einmal ändert — sie steckt dann allerdings schon in ausgelieferten PDF-Dateien.

**Umgebungsvariablen:** `TDMREP_POLICY` überschreibt die voreingestellte Policy-URL, `TDMREP_LOG` setzt die Protokolldatei, `TDMREP_PYTHON` wählt einen bestimmten Python-Interpreter.

Die ältere Schreibweise `--in DATEI` funktioniert weiterhin.

## Vorhandene Angaben werden gemeldet, nicht überschrieben

Enthält eine Datei bereits TDM-Angaben, ändert `tdmrep` nichts, sondern meldet den Sachverhalt und beendet sich mit Code 3. Ein bereits eingetragener Wert ist eine Willenserklärung der rechteinhabenden Person nach § 44b Abs. 3 UrhG; ihn stillschweigend zu ersetzen wiegt schwerer, als gar keinen zu setzen.

Als Konflikt gilt:

- der vorhandene Wert weicht von der Vorgabe ab — auch dann, wenn dort eine `0` steht, mit der jemand bewusst freigegeben hat
- der Wert liegt außerhalb des zulässigen Bereichs `0` und `1`
- es ist bereits eine abweichende Policy-URL eingetragen, etwa die eines Verlags
- der Vorbehalt steht in der EPUB-Namensraum-Schreibweise `tdmrep#` und müsste für PDF umgeschrieben werden
- die Datei enthält mehrere, einander widersprechende Angaben

Mit `--on-conflict overwrite` wird bewusst überschrieben; das Protokoll führt dann unter `conflicts_overridden` auf, was ersetzt wurde.

Übersprungen werden verschlüsselte, passwortgeschützte, signierte und zertifizierte Dateien: Jede Änderung würde eine Signatur brechen.

## Protokoll und Exit-Codes

Je Datei entsteht eine JSON-Zeile mit Zeitstempel, Prüfsummen vor und nach der Bearbeitung, erkannter PDF/A-Stufe und den vorgefundenen Angaben. Sie dient als Nachweis, ab wann der Vorbehalt in maschinenlesbarer Form vorlag — im Streitfall muss das die rechteinhabende Person belegen.

| Code | Bedeutung |
|---|---|
| 0 | geschrieben oder bereits im Sollzustand (`written` / `unchanged`) |
| 2 | übersprungen: verschlüsselt, passwortgeschützt, signiert oder zertifiziert |
| 3 | Konflikt, es wurde nichts geschrieben |
| 1 | Fehler, etwa nicht lesbares XMP oder fehlende Datei |

Bei mehreren Dateien gilt der höchste aufgetretene Code. Ein Stapellauf kann daran ohne Auswertung der Ausgabe erkennen, ob etwas liegengeblieben ist.

Ein wiederholter Lauf über dieselbe Datei ändert weder Inhalt noch Prüfsumme und meldet `unchanged`.

## Hinweise

- **Das Speichern schreibt die Dateistruktur neu.** Der Inhalt bleibt nachweislich identisch, die Bytes nicht — es entsteht eine neue Prüfsumme. Für Auslieferungskopien ist das unproblematisch, für Archivpakete mit hinterlegten Fixity-Werten nicht. Für Archivfassungen ist ein inkrementelles Update zu prüfen, bei dem die Originalbytes unverändert bleiben.
- **Ein einmal ausgelieferter Vorbehalt ist nicht widerrufbar.** Für Kopien, die bereits heruntergeladen wurden, lässt er sich nicht mehr zurücknehmen. HTTP-Header und Angaben auf Webseiten sind dagegen jederzeit änderbar.
- **PDF/A-Dateien** sollten nach der Bearbeitung mit veraPDF gegen dieselbe Konformitätsstufe geprüft werden; das Protokoll weist darauf hin, wenn die Quelle PDF/A war.

## Fehlersuche

| Meldung / Problem | Abhilfe |
|---|---|
| „python3 nicht gefunden“ | `brew install python`, oder `TDMREP_PYTHON=/pfad/zu/python3` |
| `ModuleNotFoundError: pikepdf` | `./install.sh` erneut aufrufen; legt die Umgebung an |
| `"status":"conflict"` | Datei enthält bereits Angaben — prüfen, dann ggf. `--on-conflict overwrite` |
| `"status":"skipped"` | Datei ist signiert, zertifiziert oder verschlüsselt; sie wird bewusst nicht verändert |
| „weder --output noch --in-place angegeben“ | Ziel angeben, oder mit `-n` erst einmal nur prüfen |
| `"metadata_filter"` ist nicht `None` | der Metadatenstrom wurde komprimiert; bei PDF/A ein Konformitätsproblem, bitte melden |

## Dateien

```
tdmrep/
├── bin/tdmrep                  Starter (Bash), wählt den Python-Interpreter
├── share/tdmrep/tdmrep.py      das Programm
├── share/tdmrep/venv/          Python-Umgebung, von install.sh angelegt
├── examples/beispiel.pdf       kleine Datei zum Ausprobieren
├── requirements.txt            pikepdf, lxml
├── install.sh                  legt den Link im PATH an
└── README.md
```

Version 2.1.0
