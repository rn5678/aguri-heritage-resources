"""Open linked files in browser tabs while retaining source destinations."""
from html import escape
from html.parser import HTMLParser
from pathlib import PurePosixPath
import re
from urllib.parse import unquote, urlsplit, urlunsplit

FILE_EXTENSIONS = frozenset({
    '.pdf', '.txt', '.csv', '.json', '.xml', '.jpg', '.jpeg', '.png', '.gif',
    '.webp', '.svg', '.avif', '.bmp', '.ico', '.mp3', '.m4a', '.wav', '.ogg',
    '.mp4', '.webm', '.mov', '.doc', '.docx', '.odt', '.xls', '.xlsx', '.ods',
    '.ppt', '.pptx', '.odp', '.zip', '.gz', '.epub',
})
JOURNAL_FILES = frozenset(f'Ugrakshatriya_Pratinidhi_Vol_{n:02}.pdf' for n in (1, 2))
JOURNAL_ROUTES = frozenset('/api/documents/' + name for name in JOURNAL_FILES)
OPENING = r'<a\b(?:(?:"[^"]*")|(?:\x27[^\x27]*\x27)|[^\x27">])*>'
ANCHOR = re.compile(OPENING + r'.*?</a\s*>', re.I | re.S)

class _Anchor(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attrs = attrs

def is_file_link(href):
    url = urlsplit(href)
    if url.scheme not in ('', 'http', 'https'):
        return False
    if url.hostname == 'commons.wikimedia.org' and url.path.startswith('/wiki/'):
        return False  # A file-description page is a source citation, not the file.
    if url.hostname == 'ir.nbu.ac.in' and re.fullmatch(r'/bitstreams/[a-f0-9-]+/download', url.path):
        return True
    return PurePosixPath(unquote(url.path)).suffix.lower() in FILE_EXTENSIONS

def inline_file_url(href):
    url = urlsplit(href)
    path = unquote(url.path)
    if url.hostname not in (None, 'aguri-heritage.in', 'www.aguri-heritage.in'):
        return href
    name = PurePosixPath(path).name
    if name in JOURNAL_FILES and path.lstrip('./') == 'assets/documents/' + name:
        return urlunsplit(('', '', '/api/documents/' + name, url.query, url.fragment))
    return href

def _open_label(text):
    text = re.sub(r'\bDownload\b', 'Open', text)
    text = re.sub(r'\bdownload\b', 'open', text)
    text = text.replace('ডাউনলোড করুন', 'খুলুন').replace('ডাউনলোড', 'খুলুন')
    return text.replace('↓', '↗')

def open_file_links(html):
    def update(match):
        anchor = match.group()
        end = re.match(OPENING, anchor, re.I | re.S).end()
        parser = _Anchor()
        parser.feed(anchor[:end])
        attrs = dict(parser.attrs)
        href = attrs.get('href', '')
        if not is_file_link(href) and 'download' not in attrs:
            return anchor
        attrs.pop('download', None)
        attrs['href'] = inline_file_url(href)
        attrs['target'] = '_blank'
        attrs['rel'] = ' '.join(dict.fromkeys([*attrs.get('rel', '').split(), 'noopener']))
        for key in ('aria-label', 'title'):
            if key in attrs:
                attrs[key] = _open_label(attrs[key])
        opening = '<a' + ''.join(' ' + key + ('' if value is None else '="' + escape(value, quote=True) + '"') for key, value in attrs.items()) + '>'
        parts = re.split(r'(<[^>]*>)', anchor[end:])
        content = ''.join(part if i % 2 else _open_label(part) for i, part in enumerate(parts))
        return opening + content
    return ANCHOR.sub(update, html)
