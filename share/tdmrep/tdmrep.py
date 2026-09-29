#!/usr/bin/env python3
"""
tdmrep - schreibt einen TDM-Rechtevorbehalt (W3C TDM Reservation Protocol)
in die XMP-Metadaten von PDF-Dateien.

Universitaetsbibliothek Paderborn, Publikationsservice.
Aufruf ueber bin/tdmrep; Dokumentation in README.md.
"""
import argparse, hashlib, json, os, re, sys, datetime
from pathlib import Path
import pikepdf
from lxml import etree

VERSION = '2.1.0'

# Vorgabe fuer --policy. Reihenfolge: -p vor TDMREP_POLICY vor dieser Konstante.
DEFAULT_POLICY = 'https://data.ub.uni-paderborn.de/policies/digital.ub/tdm.json'

TDM_SLASH = 'http://www.w3.org/ns/tdmrep/'      # Schreibweise laut PDF-Abschnitt der Spec
TDM_HASH  = 'http://www.w3.org/ns/tdmrep#'      # Schreibweise laut EPUB-Abschnitt der Spec
NS = {'x':'adobe:ns:meta/','rdf':'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
      'tdm':TDM_SLASH,
      'pdfaExtension':'http://www.aiim.org/pdfa/ns/extension/',
      'pdfaSchema':'http://www.aiim.org/pdfa/ns/schema#',
      'pdfaProperty':'http://www.aiim.org/pdfa/ns/property#',
      'pdfaid':'http://www.aiim.org/pdfa/ns/id/'}
Q = lambda p,l: '{%s}%s' % (NS[p], l)

EMPTY = ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
         '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="%s"/></x:xmpmeta>'
         '<?xpacket end="w"?>' % NS['rdf'])
PROPS = [('reservation','Integer','TDM rights reservation (1 = reserved, 0 = not reserved)'),
         ('policy','URI','URL of the TDM policy document')]
HINT_RE = re.compile(r'(text[\s-]?and[\s-]?data[\s-]?mining|ki[\s-]?training|'
                     r'ai[\s-]?training|machine[\s-]?learning|no\s?ai|vorbehalt)', re.I)
URL_RE = re.compile(r'\bhttps?://\S+')


# ---------------------------------------------------------------- Hilfsfunktionen
def sha256(path):
    h = hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
    return h.hexdigest()


def local(tag):
    """Lokaler Name ohne Namensraum, kleingeschrieben."""
    return etree.QName(tag).localname.lower() if isinstance(tag, str) and tag.startswith('{') else str(tag).lower()


def is_tdm(tag, name):
    """Erkennt tdm:<name> in beiden Namensraum-Schreibweisen und unabhängig von Groß-/Kleinschreibung."""
    if not isinstance(tag, str) or not tag.startswith('{'):
        return False
    q = etree.QName(tag)
    return q.namespace in (TDM_SLASH, TDM_HASH) and q.localname.lower() == name


# ---------------------------------------------------------------- Schutzregeln (Punkt 8)
def guard(pdf):
    problems = []
    if pdf.is_encrypted:
        problems.append('verschluesselt')
    acro = pdf.Root.get('/AcroForm')
    if acro is not None:
        try:
            for fld in acro.get('/Fields', []):
                if fld.get('/FT') == '/Sig' and fld.get('/V') is not None:
                    problems.append('digitale Signatur'); break
        except Exception:
            problems.append('AcroForm nicht auswertbar')
    if '/Perms' in pdf.Root:
        problems.append('Perms/DocMDP (zertifiziert)')
    return problems


# ---------------------------------------------------------------- XMP lesen (Punkt 1)
def load_xmp(pdf):
    if '/Metadata' in pdf.Root:
        raw = bytes(pdf.Root.Metadata.read_bytes())
    else:
        raw = EMPTY.encode('utf-8')
    txt = raw.decode('utf-8', 'replace')
    s = txt.find('<x:xmpmeta')
    if s != -1:
        e = txt.rfind('</x:xmpmeta>'); core = txt[s:e+len('</x:xmpmeta>')]
    else:
        s = txt.find('<rdf:RDF'); e = txt.rfind('</rdf:RDF>')
        if s == -1: raise ValueError('XMP-Paket enthaelt kein rdf:RDF')
        core = txt[s:e+len('</rdf:RDF>')]
    tree = etree.fromstring(core.encode('utf-8'))
    rdf = tree if local(tree.tag) == 'rdf' else tree.find(Q('rdf','RDF'))
    if rdf is None: raise ValueError('kein rdf:RDF im XMP-Paket')
    return tree, rdf, txt


def read_state(rdf, raw_txt):
    """Liest den vorhandenen Zustand - beide Namensraeume, beide Schreibweisen (Punkt 5, 7)."""
    found = []
    for el in rdf.iter():
        for name in ('reservation','policy'):
            if is_tdm(el.tag, name):
                found.append((name, etree.QName(el.tag).namespace, (el.text or '').strip()))
    st = {'reservation': None, 'policy': None, 'namespaces': sorted({n for _,n,_ in found}),
          'duplicates': False, 'value_valid': True}
    for name, _, val in found:
        if st[name] is not None and st[name] != val: st['duplicates'] = True
        if st[name] is None: st[name] = val
    if st['reservation'] is not None and st['reservation'] not in ('0','1'):
        st['value_valid'] = False
    # Nur Fliesstext betrachten: Markup und URLs (auch unsere eigene Policy-URL)
    # wuerden sonst als Treffer gezaehlt.
    plain = URL_RE.sub(' ', re.sub(r'<[^>]+>', ' ', raw_txt))
    st['hints'] = sorted({m.group(0).lower() for m in HINT_RE.finditer(plain)})
    return st


def read_pdfa(rdf):
    part = conf = None
    for el in rdf.iter():
        if isinstance(el.tag, str) and el.tag.startswith('{' + NS['pdfaid']):
            n = etree.QName(el.tag).localname.lower()
            if n == 'part': part = (el.text or '').strip()
            if n == 'conformance': conf = (el.text or '').strip()
    for desc in rdf.iter():
        for k, v in desc.attrib.items():
            if k.startswith('{' + NS['pdfaid']):
                n = etree.QName(k).localname.lower()
                if n == 'part': part = v
                if n == 'conformance': conf = v
    return (part + (conf or '')).upper() if part else None


# ---------------------------------------------------------------- XMP schreiben
def write_tdm(rdf, reservation, policy):
    for parent in list(rdf.iter()):
        for el in list(parent):
            if is_tdm(el.tag, 'reservation') or is_tdm(el.tag, 'policy'):
                parent.remove(el)
    d = etree.SubElement(rdf, Q('rdf','Description'), nsmap={'tdm': TDM_SLASH})
    d.set(Q('rdf','about'), '')
    etree.SubElement(d, Q('tdm','reservation')).text = str(reservation)
    if policy:
        etree.SubElement(d, Q('tdm','policy')).text = policy


def ensure_extension_schema(rdf):
    """Punkt 4: an vorhandenen rdf:Bag anhaengen, notfalls Bag im vorhandenen
    schemas-Element anlegen - niemals einen zweiten schemas-Block erzeugen."""
    schemas = None
    for el in rdf.iter(Q('pdfaExtension','schemas')):
        schemas = el; break
    if schemas is not None:
        bag = schemas.find(Q('rdf','Bag'))
        if bag is None:
            bag = etree.SubElement(schemas, Q('rdf','Bag'))
        for li in bag.findall(Q('rdf','li')):
            u = li.find(Q('pdfaSchema','namespaceURI'))
            if u is not None and (u.text or '').strip() in (TDM_SLASH, TDM_HASH):
                return 'bereits vorhanden'
    else:
        d = etree.SubElement(rdf, Q('rdf','Description'),
                             nsmap={'pdfaExtension': NS['pdfaExtension'],
                                    'pdfaSchema': NS['pdfaSchema'],
                                    'pdfaProperty': NS['pdfaProperty']})
        d.set(Q('rdf','about'), '')
        bag = etree.SubElement(etree.SubElement(d, Q('pdfaExtension','schemas')), Q('rdf','Bag'))

    li = etree.SubElement(bag, Q('rdf','li')); li.set(Q('rdf','parseType'), 'Resource')
    etree.SubElement(li, Q('pdfaSchema','schema')).text = 'TDM Reservation Protocol'
    etree.SubElement(li, Q('pdfaSchema','namespaceURI')).text = TDM_SLASH
    etree.SubElement(li, Q('pdfaSchema','prefix')).text = 'tdm'
    seq = etree.SubElement(etree.SubElement(li, Q('pdfaSchema','property')), Q('rdf','Seq'))
    for name, vtype, descr in PROPS:
        p = etree.SubElement(seq, Q('rdf','li')); p.set(Q('rdf','parseType'), 'Resource')
        etree.SubElement(p, Q('pdfaProperty','name')).text = name
        etree.SubElement(p, Q('pdfaProperty','valueType')).text = vtype
        etree.SubElement(p, Q('pdfaProperty','category')).text = 'external'
        etree.SubElement(p, Q('pdfaProperty','description')).text = descr
    return 'ergaenzt'


def serialize(tree):
    return (b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            + etree.tostring(tree, encoding='utf-8', pretty_print=True)
            + b'\n' + b' ' * 2048 + b'\n<?xpacket end="w"?>')


# ---------------------------------------------------------------- Hauptablauf
def process(src, dst, a):
    """Bearbeitet eine Datei. Liefert (Protokolldatensatz, Exit-Code)."""
    rec = {'tool': 'tdmrep', 'version': VERSION,
           'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'src': str(src), 'sha256_before': sha256(src)}

    try:
        pdf = pikepdf.open(src, allow_overwriting_input=True)
    except pikepdf.PasswordError:
        rec.update(status='skipped', reason='passwortgeschuetzt'); return rec, 2
    except Exception as e:
        rec.update(status='error', reason=f'{type(e).__name__}: {e}'); return rec, 1

    with pdf:
        blockers = guard(pdf)
        if blockers:
            rec.update(status='skipped', reason='; '.join(blockers)); return rec, 2

        try:
            tree, rdf, raw = load_xmp(pdf)
        except Exception as e:
            rec.update(status='error', reason=f'XMP nicht lesbar: {e}'); return rec, 1

        st = read_state(rdf, raw)
        rec['pdfa'] = read_pdfa(rdf)
        rec['found'] = {k: st[k] for k in
                        ('reservation', 'policy', 'namespaces', 'duplicates', 'value_valid')}
        if st['hints']:
            rec['found']['hinweise_im_text'] = st['hints']

        desired_pol = a.policy
        conflicts = []
        if st['reservation'] is not None:
            if not st['value_valid']:
                conflicts.append(f"ungueltiger Wert {st['reservation']!r} "
                                 f"(zulaessig sind 0 und 1)")
            elif st['reservation'] != a.reservation:
                conflicts.append(f"vorhandener Wert {st['reservation']} weicht von der "
                                 f"Vorgabe {a.reservation} ab")
            if st['duplicates']:
                conflicts.append('mehrere abweichende tdm-Angaben in der Datei')
            if TDM_HASH in st['namespaces']:
                conflicts.append('Vorbehalt in der EPUB-Namensraum-Schreibweise (tdmrep#)')
            if st['policy'] and desired_pol and st['policy'] != desired_pol:
                conflicts.append(f"vorhandene Policy {st['policy']} weicht ab")
        if conflicts and a.on_conflict == 'report':
            rec.update(status='conflict', conflicts=conflicts,
                       hinweis='redaktionell klaeren; mit --on-conflict overwrite '
                               'bewusst ueberschreiben')
            return rec, 3
        rec['conflicts_overridden'] = conflicts or None

        pol_ok = (desired_pol is None) or (st['policy'] == desired_pol)
        if (st['reservation'] == a.reservation and pol_ok and st['value_valid']
                and not st['duplicates'] and TDM_HASH not in st['namespaces']):
            ext_needed = (not a.no_pdfa_ext) and not any(
                (u.text or '').strip() in (TDM_SLASH, TDM_HASH)
                for u in rdf.iter(Q('pdfaSchema', 'namespaceURI')))
            if not ext_needed:
                rec.update(status='unchanged', reservation=st['reservation'])
                return rec, 0

        write_tdm(rdf, a.reservation, desired_pol)
        rec['pdfa_extension'] = ('uebersprungen' if a.no_pdfa_ext
                                 else ensure_extension_schema(rdf))

        if a.dry_run:
            rec.update(status='dry-run', reservation_before=st['reservation'],
                       reservation_after=a.reservation)
            return rec, 0

        pdf.Root.Metadata = pdf.make_stream(serialize(tree))
        pdf.Root.Metadata[pikepdf.Name('/Type')] = pikepdf.Name('/Metadata')
        pdf.Root.Metadata[pikepdf.Name('/Subtype')] = pikepdf.Name('/XML')
        pdf.save(dst, object_stream_mode=pikepdf.ObjectStreamMode.preserve)

    with pikepdf.open(dst) as chk:
        rec['metadata_filter'] = str(chk.Root.Metadata.get('/Filter'))
    rec.update(status='written', dst=str(dst), reservation_before=st['reservation'],
               reservation_after=a.reservation, policy=desired_pol,
               sha256_after=sha256(dst))
    if rec.get('pdfa'):
        rec['hinweis'] = (f"Quelle ist PDF/A-{rec['pdfa']} - Ergebnis mit veraPDF "
                          f"gegen dieselbe Stufe pruefen")
    return rec, 0


HELP = f"""tdmrep - TDM-Rechtevorbehalt in PDF-Dateien schreiben

  tdmrep [Optionen] DATEI.pdf [DATEI.pdf ...]

  -o, --output PFAD        Ziel-PDF oder Zielverzeichnis
  -i, --in-place           Quelldatei ueberschreiben
  -r, --reservation 0|1    zu setzender Wert (Vorgabe 1)
  -p, --policy URL         URL der Rechte-Policy; -p "" laesst sie weg
                           Vorgabe: {DEFAULT_POLICY}
      --on-conflict WIE    report (Vorgabe) oder overwrite
      --no-pdfa-ext        ohne PDF/A Extension Schema Description
  -n, --dry-run            nur pruefen, nichts schreiben
      --log DATEI          Protokollzeilen zusaetzlich anhaengen
  -q, --quiet              nur Konflikte und Fehler ausgeben
  -h, --help               diese Hilfe
  -v, --version            Version

Exit-Codes: 0 geschrieben oder unveraendert, 2 uebersprungen,
3 Konflikt (nichts geschrieben), 1 Fehler. Bei mehreren Dateien
gilt der hoechste aufgetretene Code.

Umgebungsvariablen: TDMREP_POLICY, TDMREP_LOG, TDMREP_PYTHON.
"""


def main():
    ap = argparse.ArgumentParser(prog='tdmrep', add_help=False)
    ap.add_argument('dateien', nargs='*', metavar='DATEI.pdf')
    ap.add_argument('--in', dest='alt_in', metavar='DATEI.pdf')   # aeltere Schreibweise
    ap.add_argument('-o', '--out', '--output', dest='dst', metavar='PFAD')
    ap.add_argument('-i', '--in-place', action='store_true')
    ap.add_argument('-r', '--reservation', default='1', choices=['0', '1'])
    ap.add_argument('-p', '--policy',
                    default=os.environ.get('TDMREP_POLICY', DEFAULT_POLICY))
    ap.add_argument('--on-conflict', default='report', choices=['report', 'overwrite'])
    ap.add_argument('--no-pdfa-ext', action='store_true')
    ap.add_argument('-n', '--dry-run', action='store_true')
    ap.add_argument('--log', default=os.environ.get('TDMREP_LOG'), metavar='DATEI')
    ap.add_argument('-q', '--quiet', action='store_true')
    ap.add_argument('-h', '--help', action='store_true')
    ap.add_argument('-v', '--version', action='version', version=f'tdmrep {VERSION}')
    a = ap.parse_args()

    if a.policy == '':          # -p "" laesst tdm:policy bewusst weg
        a.policy = None

    if a.help:
        print(HELP, end=''); return 0

    files = ([a.alt_in] if a.alt_in else []) + list(a.dateien)
    if not files:
        print(HELP, end=''); return 1

    if a.dst and len(files) > 1 and not Path(a.dst).is_dir():
        print('tdmrep: bei mehreren Dateien muss --output ein Verzeichnis sein.',
              file=sys.stderr)
        return 1
    if not a.dst and not a.in_place and not a.dry_run:
        print('tdmrep: weder --output noch --in-place angegeben. '
              'Mit --dry-run laesst sich pruefen, ohne zu schreiben.', file=sys.stderr)
        return 1

    worst = 0
    for name in files:
        src = Path(name)
        if not src.is_file():
            rec, code = {'tool': 'tdmrep', 'version': VERSION, 'src': str(src),
                         'status': 'error', 'reason': 'Datei nicht gefunden'}, 1
        else:
            if a.dst and Path(a.dst).is_dir():
                dst = Path(a.dst) / src.name
            elif a.dst:
                dst = Path(a.dst)
            else:
                dst = src
            rec, code = process(src, dst, a)

        line = json.dumps(rec, ensure_ascii=False)
        if not a.quiet or code not in (0, 2):
            print(line)
        if a.log:
            with open(a.log, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        worst = max(worst, code)

    return worst


if __name__ == '__main__':
    sys.exit(main())
