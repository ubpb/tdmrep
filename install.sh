#!/usr/bin/env bash
# Installs tdmrep: links bin/tdmrep into a directory on PATH and makes sure
# the Python libraries are available.
#
#   ./install.sh                 link into ~/.local/bin
#   ./install.sh DIRECTORY       link into DIRECTORY
#   ./install.sh --no-venv [DIR] do not create a virtual environment
#   ./install.sh --uninstall [DIRECTORY]
#
# The package stays where it is; move it first, then run this script again.

set -euo pipefail

here="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uninstall=0
use_venv=1
while [ $# -gt 0 ]; do
  case "$1" in
    --uninstall) uninstall=1; shift ;;
    --no-venv)   use_venv=0;  shift ;;
    *) break ;;
  esac
done
target_dir="${1:-$HOME/.local/bin}"
link="$target_dir/tdmrep"
venv="$here/share/tdmrep/venv"

if [ "$uninstall" = 1 ]; then
  if [ -L "$link" ]; then
    rm "$link"
    echo "Entfernt: $link"
  else
    echo "Kein Link gefunden: $link"
  fi
  if [ -d "$venv" ]; then
    rm -rf "$venv"
    echo "Entfernt: $venv"
  fi
  exit 0
fi

if [ -e "$link" ] && [ ! -L "$link" ]; then
  echo "Abbruch: $link existiert und ist kein Link." >&2
  exit 1
fi

# Python
py="${TDMREP_PYTHON:-$(command -v python3 || true)}"
if [ -z "$py" ]; then
  echo "Abbruch: python3 nicht gefunden. Installieren mit: brew install python" >&2
  exit 1
fi
echo "Python:  $("$py" --version 2>&1)"

# Bibliotheken: erst im System suchen, sonst in eine eigene Umgebung legen
if "$py" -c 'import pikepdf, lxml' >/dev/null 2>&1; then
  echo "Module:  pikepdf und lxml sind vorhanden"
elif [ "$use_venv" = 1 ]; then
  if [ ! -x "$venv/bin/python3" ]; then
    echo "Module fehlen. Lege eine eigene Umgebung an: $venv"
    "$py" -m venv "$venv"
  fi
  "$venv/bin/python3" -m pip install --quiet --upgrade pip
  "$venv/bin/python3" -m pip install --quiet -r "$here/requirements.txt"
  echo "Module:  in $venv installiert"
else
  echo "Module fehlen: pikepdf und lxml. Installieren mit:"
  echo "  $py -m pip install -r $here/requirements.txt"
fi

mkdir -p "$target_dir"
chmod +x "$here/bin/tdmrep"
ln -sfn "$here/bin/tdmrep" "$link"
echo "Installiert: $link -> $here/bin/tdmrep"

# Selbsttest an der Beispieldatei
if [ -f "$here/examples/beispiel.pdf" ]; then
  if "$here/bin/tdmrep" --dry-run --quiet "$here/examples/beispiel.pdf" >/dev/null 2>&1; then
    echo "Selbsttest: bestanden"
  else
    echo "Selbsttest: fehlgeschlagen. '$here/bin/tdmrep -n $here/examples/beispiel.pdf' zeigt warum."
  fi
fi

case ":$PATH:" in
  *":$target_dir:"*) echo "Fertig. Aufruf: tdmrep --help" ;;
  *)
    echo "$target_dir ist nicht im PATH. In ~/.zshrc ergänzen und die Shell neu starten:"
    echo "  export PATH=\"$target_dir:\$PATH\""
    ;;
esac
