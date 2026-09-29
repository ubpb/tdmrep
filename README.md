# tdmrep

Writes a text and data mining rights reservation into PDF files, from anywhere on the command line:

```
$ tdmrep -p https://example.org/policies/tdm.json -i dissertation.pdf
{"tool":"tdmrep","version":"1.0.1","status":"written","sha256_before":"f5b51ea5…","sha256_after":"ec961f7f…", …}
```

The reservation goes into the document's XMP metadata, so it stays with the file even after it has been downloaded and passed on elsewhere. Pages, text, fonts and images remain unchanged.

`examples/beispiel.pdf` is a small file to try it out on.

## How it works

1. The file is opened with **pikepdf** (based on qpdf) and its XMP packet is read.
2. `tdm:reservation` and, if a policy URL is given, `tdm:policy` are **added** in the namespace `http://www.w3.org/ns/tdmrep/` — existing entries such as `dc:creator`, `xmp:CreateDate` or the PDF/A identification are preserved.
3. Because `tdm` is not a standard XMP schema, a **PDF/A Extension Schema Description** is added as well. Without it, a PDF/A validator flags the file.
4. The file is saved without new object streams, so a PDF/A-1 file stays conformant. After writing, the program checks that the metadata stream has remained uncompressed and records the result in the log.

It is based on the W3C [TDM Reservation Protocol](https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/).

## Requirements

- **Python** 3.9 or later: `brew install python`
- **pikepdf** and **lxml** — `install.sh` sets them up in a separate environment next to the program if needed, without touching the system Python
- Bash, as shipped with macOS (also runs on Linux)

## Installation

1. Put the `tdmrep` folder in its permanent location, e.g. `~/Code/Tools/tdmrep`. The script finds its files relative to itself, even when called through a link.
2. Run in the folder:

   ```
   $ ./install.sh
   ```

   This creates `~/.local/bin/tdmrep` as a link to `bin/tdmrep`, takes care of the Python modules, runs a self-test on the example file and, if `~/.local/bin` is not yet on your PATH, tells you which line to add to `~/.zshrc`. For a different target directory: `./install.sh /usr/local/bin`. If pikepdf and lxml are already installed on the system, no separate environment is created; `--no-venv` prevents it altogether.

**Uninstall:** `./install.sh --uninstall` removes the link and the environment; the folder can then be deleted.

**Move:** move the folder and run `./install.sh` again; the link is replaced.

## Usage

```
tdmrep [options] FILE.pdf [FILE.pdf ...]
```

| Option | Effect |
|---|---|
| `-o`, `--output PATH` | target PDF (for a single input file) or target directory |
| `-i`, `--in-place` | overwrite the source file |
| `-r`, `--reservation 0\|1` | value to set, default `1` |
| `-p`, `--policy URL` | URL of the rights policy, optional |
| `--on-conflict report\|overwrite` | behaviour when entries already exist, default `report` |
| `--no-pdfa-ext` | without the PDF/A Extension Schema Description |
| `-n`, `--dry-run` | check only, write nothing |
| `--log FILE` | also append the log line to this file |
| `-q`, `--quiet` | only print conflicts and errors |
| `-h`, `--help` / `-v`, `--version` | help / version |

Without `-o` or `-i` the program writes nothing — this is deliberate, so that an original file is not overwritten by accident.

Examples:

```
$ tdmrep -p https://…/tdm.json -o diss_with-reservation.pdf diss.pdf
$ tdmrep -i diss.pdf                        # reservation without policy URL
$ tdmrep -n diss.pdf                        # just see what would happen
$ tdmrep -p https://…/tdm.json -o output/ input/*.pdf
$ tdmrep -r 0 -i released.pdf               # explicit permission
```

### Policy URL

The policy URL is optional; there is no default. `tdm:policy` is written only if a URL is given, either

1. with `-p URL` on the command line, or
2. in the environment variable `TDMREP_POLICY`, e.g. set once in `~/.zshrc`.

`-p` beats `TDMREP_POLICY`, and `-p ""` ignores `TDMREP_POLICY` for a single call. A given policy URL is written with `-r 0` as well.

Without a policy URL, a policy already present in the file is kept. With one, a different policy already present is a conflict (see below).

Once PDF files carrying a policy URL have been delivered, the URL in them can no longer be changed, so that address should stay reachable.

**Environment variables:** `TDMREP_POLICY` sets the policy URL, `TDMREP_LOG` sets the log file, `TDMREP_PYTHON` selects a specific Python interpreter.

The older syntax `--in FILE` still works.

## Existing entries are reported, not overwritten

If a file already contains TDM entries, `tdmrep` changes nothing; it reports the situation and exits with code 3. A value already entered is a declaration of intent by the rights holder under Section 44b(3) of the German Copyright Act (UrhG); silently replacing it is worse than setting none at all.

A conflict is any of the following:

- the existing value differs from the requested one — even if it is a `0` that someone set deliberately to grant permission
- the value lies outside the permitted range `0` and `1`
- a policy URL is given and a different one is already present, e.g. a publisher's
- the reservation uses the EPUB namespace notation `tdmrep#` and would have to be rewritten for PDF
- the file contains several contradictory entries

`--on-conflict overwrite` overwrites deliberately; the log then lists what was replaced under `conflicts_overridden`.

Encrypted, password-protected, signed and certified files are skipped: any change would break a signature.

## Log and exit codes

Each file produces one JSON line with a timestamp, checksums before and after processing, the detected PDF/A level and the entries found. For `written` and `dry-run` it shows reservation and policy before and after (`reservation_before`/`reservation_after`, `policy_before`/`policy_after`); for `conflict` it shows the requested policy as `policy_requested`. It serves as evidence of when the reservation was present in machine-readable form — in a dispute, the rights holder has to prove this.

| Code | Meaning |
|---|---|
| 0 | written or already in the desired state (`written` / `unchanged`) |
| 2 | skipped: encrypted, password-protected, signed or certified |
| 3 | conflict, nothing was written |
| 1 | error, e.g. unreadable XMP or missing file |

With several files, the highest code encountered applies. A batch run can tell from it whether anything was left undone without parsing the output.

Running again on the same file changes neither content nor checksum and reports `unchanged`.

## Notes

- **Saving rewrites the file structure.** The content verifiably stays the same, the bytes do not — the file gets a new checksum. This is harmless for delivery copies, but not for archival packages with stored fixity values. For archival versions, consider an incremental update, which leaves the original bytes untouched.
- **A reservation, once delivered, cannot be revoked.** It cannot be withdrawn from copies that have already been downloaded. HTTP headers and statements on web pages, by contrast, can be changed at any time.
- **PDF/A files** should be validated with veraPDF against the same conformance level after processing; the log points this out when the source was PDF/A.

## Troubleshooting

The program's own messages are in German; they are quoted verbatim below.

| Message / problem | Remedy |
|---|---|
| „python3 nicht gefunden“ (python3 not found) | `brew install python`, or `TDMREP_PYTHON=/path/to/python3` |
| `ModuleNotFoundError: pikepdf` | run `./install.sh` again; it creates the environment |
| `"status":"conflict"` | file already contains entries — check them, then use `--on-conflict overwrite` if appropriate |
| `"status":"skipped"` | file is signed, certified or encrypted; it is deliberately left unchanged |
| „weder --output noch --in-place angegeben“ (neither --output nor --in-place given) | specify a target, or check first with `-n` |
| `"metadata_filter"` is not `None` | the metadata stream was compressed; a conformance problem for PDF/A, please report |

## Files

```
tdmrep/
├── bin/tdmrep                  launcher (Bash), selects the Python interpreter
├── share/tdmrep/tdmrep.py      the program
├── share/tdmrep/venv/          Python environment, created by install.sh
├── examples/beispiel.pdf       small file to try it out on
├── requirements.txt            pikepdf, lxml
├── install.sh                  creates the link on the PATH
└── README.md
```

Version 1.0.1
