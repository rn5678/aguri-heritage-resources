"""Persist editorial update dates independently of rebuilds and shared page chrome.

The initial date is evidence from the relevant authored file's modification time,
not a claim about publication. Keep content/page-history.json with the sources:
after that baseline, only an editorial fingerprint change advances the date.
"""
from datetime import date, datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo
import json
import os
import re

INDIA = ZoneInfo('Asia/Kolkata')
ARCHIVE_ASSETS = {
    'en': ('assets/reading-notes.js', 'assets/ocr-data.js', 'assets/translation-links.js'),
    'bn': ('assets/reading-notes-bn.js', 'assets/ocr-data.js', 'assets/translation-links-bn.js'),
}
POLICY = ('Editorial update dates, not original publication dates. Initial dates '
          'use the latest modification time of the listed authored sources in '
          'Asia/Kolkata. Later editorial changes use the date detected by a build; '
          'unchanged content and shared template or style changes retain the date.')


def _today():
    return datetime.now(INDIA).date().isoformat()


class _EditorialHTML(HTMLParser):
    """Keep prose, semantics and source links; ignore CSS, scripts and comments."""
    CONTENT_ATTRS = {'href', 'src', 'srcset', 'alt', 'title', 'cite', 'data', 'lang'}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script'):
            self.ignored += 1
        if not self.ignored:
            self.parts.append([tag, sorted((k, v) for k, v in attrs
                                          if k in self.CONTENT_ATTRS)])

    def handle_endtag(self, tag):
        if tag in ('style', 'script'):
            self.ignored = max(0, self.ignored - 1)
        elif not self.ignored:
            self.parts.append(['/' + tag])

    def handle_data(self, data):
        if not self.ignored and (text := ' '.join(data.split())):
            self.parts.append(text)


def _fingerprint(title, desc, editorial_html):
    payload = [title, desc, _EditorialHTML(editorial_html).parts]
    return sha256(json.dumps(payload, ensure_ascii=False,
                             separators=(',', ':')).encode('utf-8')).hexdigest()


def _iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('expected an ISO date (YYYY-MM-DD)')
    return date.fromisoformat(value)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


class PageHistory:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / 'content/page-history.json'
        self.changed = False
        self.data = {'version': 1, 'policy': POLICY, 'pages': {}}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding='utf-8'),
                                       object_pairs_hook=_unique_keys)
                self._validate()
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                raise ValueError(f'Invalid page history {self.path}: {error}') from error

    def _validate(self):
        if self.data.get('version') != 1 or not isinstance(self.data.get('pages'), dict):
            raise ValueError('expected version 1 and a pages object')
        for page, entry in self.data['pages'].items():
            if not re.fullmatch(r'(en|bn)/[a-z0-9]+(?:-[a-z0-9]+)*', page):
                raise ValueError('invalid edition/page key: ' + page)
            updated = _iso_date(entry['updated'])
            if not re.fullmatch(r'[0-9a-f]{64}', entry['fingerprint']):
                raise ValueError('invalid SHA-256 fingerprint: ' + page)
            if entry['date_basis'] not in ('source-mtime-baseline', 'editorial-content-change'):
                raise ValueError('invalid date basis: ' + page)
            baseline = entry['baseline']
            if _iso_date(baseline['date']) > updated:
                raise ValueError('update precedes its baseline: ' + page)
            if not isinstance(baseline['sources'], list) or not baseline['sources']:
                raise ValueError('missing baseline source evidence: ' + page)
            for source in baseline['sources']:
                path = Path(source['path'])
                archive_asset = (page.endswith('/archives') and
                                 path.as_posix() in ARCHIVE_ASSETS[page.split('/')[0]])
                if (path.is_absolute() or '..' in path.parts or not path.parts or
                        (path.parts[0] != 'content' and not archive_asset)):
                    raise ValueError('invalid baseline source path: ' + page)
                modified = datetime.fromisoformat(source['modified'])
                if modified.tzinfo is None:
                    raise ValueError('source timestamp must include its timezone: ' + page)

    def _sources(self, key, lang):
        edition = self.root / 'content' / ('bn' if lang == 'bn' else '')
        if key == 'archives':
            return [edition / 'archives.html',
                    *(self.root / name for name in ARCHIVE_ASSETS[lang])]
        if key == 'people':
            suffix = '.summary.bn.html' if lang == 'bn' else '.summary.html'
            summary = self.root / ('content/profiles/k-d-paul' + suffix)
            return [edition / 'people.html'] + ([summary] if summary.is_file() else [])
        if key.startswith('person-'):
            override = self.root / 'content/profiles' / (key.removeprefix('person-') + '.' + lang + '.json')
            if override.is_file():
                return [override]
            return [edition / 'people.html']
        if key == 'translations' or key.startswith('translation-'):
            paths = sorted((self.root / 'content/translations').glob('*.json'))
            if key != 'translations':
                slug = key.removeprefix('translation-')
                paths = [path for path in paths
                         if json.loads(path.read_text(encoding='utf-8'))['slug'] == slug]
                if len(paths) != 1:
                    raise ValueError(f'Expected one translation source for {key}; found {len(paths)}')
            if not paths:
                raise ValueError('No authored translation sources found')
            if lang == 'bn':
                paths.append(edition / 'readings.json')
            return paths
        return [edition / (key + '.html')]

    def updated(self, key, lang, title, desc, editorial_html):
        """Return YYYY-MM-DD; pass editorial body + notes before adding page tools."""
        if lang not in ('en', 'bn') or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', key):
            raise ValueError(f'Invalid page history key: {lang}/{key}')
        page = f'{lang}/{key}'
        fingerprint = _fingerprint(title, desc, editorial_html)
        if key == 'people':
            suffix = '.summary.bn.html' if lang == 'bn' else '.summary.html'
            summary = self.root / ('content/profiles/k-d-paul' + suffix)
            if summary.is_file():
                fingerprint = sha256(json.dumps(
                    [fingerprint, _EditorialHTML(summary.read_text(encoding='utf-8')).parts],
                    ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
        if key == 'archives':
            # These editorial reader data are inserted by JavaScript, so they
            # are absent from the HTML fragment. Hash bytes, never timestamps.
            dependencies = [(name, sha256((self.root / name).read_bytes()).hexdigest())
                            for name in ARCHIVE_ASSETS[lang]]
            fingerprint = sha256(json.dumps([fingerprint, dependencies],
                                             separators=(',', ':')).encode('utf-8')).hexdigest()
        previous = self.data['pages'].get(page)
        if previous and previous['fingerprint'] == fingerprint:
            return previous['updated']
        if previous:
            updated = _today()
            if _iso_date(updated) < _iso_date(previous['updated']):
                raise ValueError(f'Current date precedes recorded update for {page}')
            entry = {**previous, 'updated': updated, 'fingerprint': fingerprint,
                     'date_basis': 'editorial-content-change'}
        else:
            sources = [{'path': str(path.relative_to(self.root)),
                        'modified': datetime.fromtimestamp(path.stat().st_mtime, INDIA).isoformat()}
                       for path in self._sources(key, lang)]
            updated = max(datetime.fromisoformat(source['modified']).date()
                          for source in sources).isoformat()
            entry = {'updated': updated, 'fingerprint': fingerprint,
                     'date_basis': 'source-mtime-baseline',
                     'baseline': {'date': updated, 'sources': sources}}
        self.data['pages'][page] = entry
        self.changed = True
        return entry['updated']

    def save(self):
        """Atomically save changed history. Rebuilds leave the registry untouched."""
        if not self.changed:
            return
        self._validate()
        temporary = None
        try:
            with NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent,
                                    prefix='.page-history-', suffix='.json', delete=False) as output:
                temporary = Path(output.name)
                json.dump(self.data, output, ensure_ascii=False, indent=2, sort_keys=True)
                output.write('\n')
            os.replace(temporary, self.path)
            self.changed = False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
