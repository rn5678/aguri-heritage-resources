#!/usr/bin/env python3
"""Local visual authoring for the existing site; no hosted services or dependencies."""
from __future__ import annotations
import argparse
import ast
import base64
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import threading
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import authored_pages
from asset_paths import is_local_asset

TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
PUBLISHER = None
PUBLISHER_LOCK = threading.Lock()
TRANSLATOR = None
TRANSLATOR_LOCK = threading.Lock()
PAGE_CREATOR = None

def page_creator():
    global PAGE_CREATOR
    if PAGE_CREATOR is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location('aguri_editor_page_creation', Path(__file__).with_name('editor_page_creation.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        PAGE_CREATOR = module
    return PAGE_CREATOR

def create_page(payload):
    return page_creator().create_page(sys.modules[__name__], payload)

def create_type(payload):
    return page_creator().create_type(sys.modules[__name__], payload)

def translator():
    global TRANSLATOR
    with TRANSLATOR_LOCK:
        if TRANSLATOR is None:
            import importlib.util
            spec = importlib.util.spec_from_file_location('aguri_editor_translation', Path(__file__).with_name('editor_translation.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            TRANSLATOR = module.Translator(ROOT, LOCK, authored, clean_block,
                                          lambda: PUBLISHER is not None and PUBLISHER.busy())
    return TRANSLATOR

def publisher():
    global PUBLISHER
    with PUBLISHER_LOCK:
        if PUBLISHER is None:
            # Import lazily so document tools and existing isolated tests stay independent.
            import importlib.util
            spec = importlib.util.spec_from_file_location('aguri_editor_github', Path(__file__).with_name('editor_github.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            PUBLISHER = module.Publisher(ROOT, LOCK)
    return PUBLISHER
CITE = re.compile(r'\[cite:([\w-]+)\]')
VOID = {'img','br','hr','input','meta','link','source','wbr','area','base','embed','param','col'}
BLOCK = {'p','h1','h2','h3','h4','h5','h6','li','td','th','figcaption','caption','blockquote','summary','dt','dd'}
INLINE = {'a','span','strong','b','em','i','u','s','small','sup','sub','br','abbr','q','cite','time','mark'}
ATTRS = {'href','title','lang','dir','class','id','aria-label','aria-hidden','target','rel','download','datetime','name'}
FLOW_CONTAINERS = {'body','div','article','section','blockquote','aside','main'}
STRUCTURE_EXCLUDED = {'figure','figcaption','caption','table','thead','tbody','tfoot','tr','td','th',
                      'ul','ol','li','dl','dt','dd','a','p','form','button','nav','script','style'}

class EditError(ValueError):
    pass

@dataclass
class Node:
    tag: str
    attrs: dict
    start: int
    opening: int
    close: int = 0
    end: int = 0
    parent: object = None
    children: list = field(default_factory=list)

class Tree(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.text, self.nodes, self.stack = text, [], []
        self.lines = [0]
        self.lines.extend(m.end() for m in re.finditer('\n', text))
        self.feed(text)
        self.close()
    def pos(self):
        row, col = self.getpos()
        return self.lines[row-1] + col
    def handle_starttag(self, tag, attrs):
        start = self.pos()
        n = Node(tag, dict(attrs), start, start+len(self.get_starttag_text()))
        if self.stack:
            n.parent = self.stack[-1]
            n.parent.children.append(n)
        self.nodes.append(n)
        if tag in VOID:
            n.close = n.end = n.opening
        else:
            self.stack.append(n)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            n = self.stack.pop()
            n.close = n.end = n.opening
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i].tag == tag:
                n = self.stack[i]
                n.close = self.pos()
                n.end = self.text.find('>', n.close)+1
                del self.stack[i:]
                break

def plain(value):
    return ' '.join(unescape(re.sub('<[^>]+>', '', CITE.sub('', value))).split())

def page_specs():
    tree = ast.parse((ROOT/'build.py').read_text())
    fixed = next(ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PAGES' for t in n.targets))
    return fixed + authored_pages.descriptors(ROOT, 'en')

def source_path(doc_id, lang):
    if lang not in ('en','bn'):
        raise EditError('Choose English or Bengali.')
    allowed = {p[0] for p in page_specs()} - {'review','contribute'}
    if doc_id.startswith('person-'):
        name = 'people'
    elif doc_id in allowed:
        name = doc_id
    else:
        raise EditError('This page is not available in the content editor.')
    path = ROOT/'content'/('bn' if lang == 'bn' else '')/(name+'.html')
    if not path.is_file():
        raise EditError('This generated page is not available in the content editor.')
    return path

def pages():
    text = source_path('people','en').read_text()
    profiles = []
    for article in Tree(text).nodes:
        if article.tag != 'article' or 'person-profile' not in article.attrs.get('class','').split():
            continue
        slug = article.attrs.get('aria-labelledby')
        if not slug: continue
        profiles.append({'id':'person-'+slug, 'title':profile_title(text,article), 'kind':'profile'})
    custom = authored_pages.page_map(ROOT)
    types = authored_pages.page_types(ROOT)
    type_names = {entry['id']:entry['name'] for entry in types}
    page_list = []
    for key,label,*_ in page_specs():
        if key in ('review','contribute') or not all((ROOT/'content'/folder/(key+'.html')).is_file() for folder in ('','bn')):
            continue
        entry = {'id':key,'title':label,'kind':'page'}
        if key in custom:
            entry.update(type=custom[key]['type'], typeName=type_names[custom[key]['type']], section=custom[key]['section'])
        page_list.append(entry)
    return {'pages':profiles + page_list, 'types':types, 'sections':authored_pages.SECTIONS}

def descendants(node):
    for child in node.children:
        yield child
        yield from descendants(child)

def profile_title(text, article):
    slug=article.attrs.get('aria-labelledby','')
    headings=[node for node in descendants(article) if node.tag=='h2']
    primary=next((node for node in headings if node.attrs.get('id')==slug),None)
    if primary: return plain(text[primary.opening:primary.close])
    if article.attrs.get('data-editor-title'): return article.attrs['data-editor-title']
    return plain(text[headings[0].opening:headings[0].close]) if headings else slug.replace('-',' ').title()


def authored(doc_id, lang):
    path = source_path(doc_id, lang)
    text = path.read_text()
    tree = Tree(text)
    selected = None
    if doc_id.startswith('person-'):
        selected = next((n for n in tree.nodes if n.tag == 'article' and n.attrs.get('aria-labelledby') == doc_id[7:]), None)
        if selected is None:
            raise EditError('This biography is no longer available. Refresh the page list.')
    def eligible(n):
        if n.attrs.get('data-editor-anchor') == 'true' or not n.end or (selected and not selected.opening <= n.start < selected.close):
            return False
        parent = n.parent
        while parent:
            if parent.attrs.get('data-editor-anchor') == 'true' or parent.tag in {'script','style','form','button','select','nav'}:
                return False
            if doc_id == 'people' and parent.tag == 'article' and parent.attrs.get('class') == 'person-profile':
                return False
            parent = parent.parent
        return True
    candidates = []
    images = []
    for n in tree.nodes:
        if not eligible(n):
            continue
        if n.tag == 'img' and n.attrs.get('src','').lstrip('./').startswith('assets/'):
            images.append(n)
        if n.tag in BLOCK and all(d.tag in INLINE for d in descendants(n)):
            body=text[n.opening:n.close]
            if n.tag=='p' or plain(body) or '{{' in body or CITE.search(body): candidates.append(n)
    # Standalone labels and links are also editable without exposing their wrappers.
    occupied = [(n.start,n.end) for n in candidates]
    for n in tree.nodes:
        if not eligible(n) or n.tag not in {'a','span','strong'}:
            continue
        if any(a <= n.start < b for a,b in occupied) or not all(d.tag in INLINE for d in descendants(n)):
            continue
        if plain(text[n.opening:n.close]) and '{{' not in text[n.opening:n.close]:
            candidates.append(n)
            occupied.append((n.start,n.end))
    return path, text, sorted(candidates,key=lambda n:n.start), images

def block_capabilities(text, node):
    """Every offered content block can be removed; structural wrappers stay managed."""
    flow = node.parent is None or node.parent.tag in FLOW_CONTAINERS
    ancestor = node.parent
    while ancestor:
        if ancestor.tag in STRUCTURE_EXCLUDED: flow = False
        ancestor = ancestor.parent
    insert = bool(flow and node.tag in BLOCK and node.end)
    return {'canDelete': bool(node.end), 'canInsertBefore': insert, 'canInsertAfter': insert,
            'deleteReason': '' if node.end else 'This block has incomplete formatting. Repair it before removing it.'}


def block_format(node):
    align = ''
    for declaration in node.attrs.get('style','').split(';'):
        key, separator, value = declaration.partition(':')
        if separator and key.strip().lower() == 'text-align' and value.strip().lower() in {'left','center','right','justify'}:
            align = value.strip().lower()
    return {'align': align}


def clean_format(value):
    if not isinstance(value,dict) or set(value) != {'align'} or value['align'] not in ('','left','center','right','justify'):
        raise EditError('Choose left, centre, right, justified or default alignment.')
    return value['align']


def formatted_opening(node, align):
    attrs = dict(node.attrs)
    declarations = [entry.strip() for entry in attrs.get('style','').split(';')
                    if entry.strip() and entry.partition(':')[0].strip().lower() != 'text-align']
    if align: declarations.append('text-align: '+align)
    if declarations: attrs['style'] = '; '.join(declarations)
    else: attrs.pop('style',None)
    return '<'+node.tag+''.join(' '+key+(f'="{escape(str(value),quote=True)}"' if value is not None else '') for key,value in attrs.items())+'>'


def image_removal_node(image):
    ancestor = image.parent
    while ancestor:
        if ancestor.tag == 'figure':
            if sum(node.tag=='img' for node in descendants(ancestor)) == 1:
                return ancestor
            break
        ancestor = ancestor.parent
    parent = image.parent
    if parent and parent.tag=='a' and sum(node.tag=='img' for node in descendants(parent))==1 and all(node.tag in {'img','span'} for node in descendants(parent)):
        return parent
    return image


def insertion_offset(doc_id, text):
    if doc_id.startswith('person-'):
        article = next((node for node in Tree(text).nodes if node.tag=='article' and node.attrs.get('aria-labelledby')==doc_id[7:]),None)
        if article is None: raise EditError('This biography is no longer available.')
        copy = next((node for node in descendants(article) if node.tag=='div' and 'person-copy' in node.attrs.get('class','').split()),None)
        return copy.close if copy and copy.end else article.close
    roots = [node for node in Tree(text).nodes if node.parent is None and node.tag in FLOW_CONTAINERS and node.end]
    return roots[-1].close if roots and not text[roots[-1].end:].strip() else len(text)


def removal_patches(text, nodes):
    """Remove visible content, retaining only inert link targets and identity metadata."""
    selected=[]
    for node in sorted({node.start:node for node in nodes}.values(),key=lambda node:(node.start,-node.end)):
        if not any(parent.start<=node.start and node.end<=parent.end for parent in selected): selected.append(node)
    patches=[]; identity={}
    for node in selected:
        identifiers=[]
        for child in (node,*descendants(node)):
            targets=[value for value in (child.attrs.get('id'),child.attrs.get('name') if child.tag=='a' else None) if value]
            if not targets and child.tag=='h2':
                targets=[re.sub(r'[^a-z0-9]+','-',plain(text[child.opening:child.close]).lower()).strip('-')]
            for target in targets:
                if target and target not in identifiers: identifiers.append(target)
            if child.tag=='h2':
                article=child.parent
                while article and not (article.tag=='article' and 'person-profile' in article.attrs.get('class','').split()): article=article.parent
                if article:
                    first=next((desc for desc in descendants(article) if desc.tag=='h2'),None)
                    if child.attrs.get('id')==article.attrs.get('aria-labelledby') or (first is child and not article.attrs.get('data-editor-title')):
                        identity[article.start]=(article.start,article.opening,opening_tag(article,{'data-editor-title':plain(text[child.opening:child.close])}))
        replacement=''.join(f'<span id="{escape(value,quote=True)}" data-editor-anchor="true" data-editor-tag="{node.tag}" hidden></span>' for value in identifiers)
        if not replacement and re.fullmatch(r'h[1-6]',node.tag): replacement=f'<span data-editor-anchor="true" data-editor-tag="{node.tag}" hidden></span>'
        if replacement and node.tag in {'li','td','th','dt','dd'}:
            replacement=f'<{node.tag} data-editor-anchor="true" hidden>'+replacement+f'</{node.tag}>'
        if node.tag=='summary':
            replacement='<summary data-editor-anchor="true" hidden>'+replacement+'</summary>'
            if node.parent and node.parent.tag=='details':
                parent=node.parent
                identity[parent.start]=(parent.start,parent.opening,opening_tag(parent,{'open':None}))
        patches.append((node.start,node.end,replacement))
    return patches+list(identity.values())


def document(doc_id, lang):
    path, text, blocks, images = authored(doc_id,lang)
    sources = json.loads((ROOT/'content/sources.json').read_text())
    if lang == 'bn':
        for key, value in json.loads((ROOT/'content/bn/sources.json').read_text()).items():
            sources[key] = {**sources[key],**value}
    numbering = {}
    def chip(m):
        key = m[1]
        numbering.setdefault(key,len(numbering)+1)
        return f'<span class="editor-citation" contenteditable="false" data-cite="{escape(key)}" title="{escape(sources.get(key,{}).get("title",key),quote=True)}">[{numbering[key]}]</span>'
    result_blocks = [{'id':str(n.start),'tag':n.tag,'html':CITE.sub(chip,text[n.opening:n.close]),
                      'format':block_format(n), **block_capabilities(text,n)} for n in blocks]
    result_images = [{'id':str(n.start),'src':'/'+n.attrs['src'].lstrip('./'),'alt':n.attrs.get('alt',''), 'canDelete':True,
                      'deleteBlockIds':[str(block.start) for block in blocks if image_removal_node(n).start<=block.start and block.end<=image_removal_node(n).end]} for n in images]
    names = {p['id']:p['title'] for p in pages()['pages']}
    title = names.get(doc_id,doc_id)
    custom = authored_pages.page_map(ROOT).get(doc_id)
    if custom:
        title = custom[lang]['title']
    if doc_id.startswith('person-'):
        article=next((node for node in Tree(text).nodes if node.tag=='article' and node.attrs.get('aria-labelledby')==doc_id[7:]),None)
        if article: title=profile_title(text,article)
    editing_notice = 'You are editing this person’s collection entry. The separate detailed biography is managed outside this editor.' if doc_id.startswith('person-') and (ROOT/'content/profiles'/(doc_id[7:]+'.'+lang+'.json')).is_file() else ''
    return {'id':doc_id,'lang':lang,'title':title,'editingNotice':editing_notice,'version':hashlib.sha256(text.encode()).hexdigest(),
            'preview':'/preview/'+('bn/' if lang == 'bn' else '')+doc_id+'.html',
            'blocks':result_blocks,'images':result_images, 'insertionTarget':{'id':'document-end','position':'after'},
            'order':[{'type':'image' if n.tag == 'img' else 'block','id':str(n.start)} for n in sorted(blocks+images,key=lambda n:n.start)]}

def safe_link(value):
    cleaned = ''.join(c for c in unescape(value) if ord(c)>32)
    parsed = urlsplit(cleaned)
    if parsed.scheme.lower() not in ('','https','http','mailto','tel') or cleaned.startswith('//'):
        raise EditError('Use a website address, email address or a link within the site.')
    return value

class InlineCleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.stack = [], []
        self.chip_depth = 0
    def handle_starttag(self, tag, attrs):
        tag = {'strike':'s','del':'s'}.get(tag,tag)
        attrs = dict(attrs)
        if self.chip_depth:
            if tag not in VOID: self.chip_depth += 1
            return
        if tag == 'span' and 'data-cite' in attrs:
            key = attrs['data-cite']
            if not re.fullmatch(r'[\w-]+',key): raise EditError('A source reference is invalid.')
            self.parts.append('[cite:'+key+']')
            self.chip_depth = 1
            return
        if tag in {'div','p'}:
            if self.parts and self.parts[-1] != '<br>': self.parts.append('<br>')
            return
        if tag not in INLINE:
            raise EditError('Paste text using the editor’s normal paste command; embedded objects are not supported.')
        cleaned = []
        for key,value in attrs.items():
            if key in ATTRS and value is not None:
                if key == 'name' and tag != 'a': continue
                if key == 'href': safe_link(value)
                cleaned.append(f' {key}="{escape(value,quote=True)}"')
        self.parts.append('<'+tag+''.join(cleaned)+'>')
        if tag != 'br': self.stack.append(tag)
        if tag == 'span':
            decoration=' '.join(value.strip().lower() for item in attrs.get('style','').split(';') for key,separator,value in [item.partition(':')] if separator and key.strip().lower() in {'text-decoration','text-decoration-line'})
            for marker in ('underline','line-through'):
                if marker in decoration.split():
                    wrapper='u' if marker=='underline' else 's'
                    self.parts.append('<'+wrapper+'>'); self.stack.append(wrapper)
    def handle_endtag(self, tag):
        tag = {'strike':'s','del':'s'}.get(tag,tag)
        if self.chip_depth:
            self.chip_depth -= 1
            return
        if tag in {'div','p'}: return
        if tag in self.stack:
            while self.stack:
                last = self.stack.pop()
                self.parts.append('</'+last+'>')
                if last == tag: break
    def handle_data(self,data):
        if not self.chip_depth: self.parts.append(escape(data,quote=False))
    def finish(self, html):
        self.feed(html)
        self.close()
        if self.chip_depth: raise EditError('A source reference is incomplete. Reload this page.')
        while self.stack: self.parts.append('</'+self.stack.pop()+'>')
        return ''.join(self.parts)

def clean_block(value, original):
    if not isinstance(value,str) or len(value)>150000:
        raise EditError('That paragraph is too large.')
    result = InlineCleaner().finish(value)
    # Authors may remove citations with the text they support. Retained markers
    # must still come from this block; do not accept fabricated or extra copies.
    if Counter(CITE.findall(result)) - Counter(CITE.findall(original)):
        raise EditError('Use only the existing source references in this paragraph; new or duplicated references cannot be added here.')
    if Counter(re.findall(r'\{\{.*?\}\}',result)) != Counter(re.findall(r'\{\{.*?\}\}',original)):
        raise EditError('This paragraph contains a generated field. Keep that field in place.')
    old_ids = Counter(n.attrs['id'] for n in Tree(original).nodes if 'id' in n.attrs)
    new_ids = Counter(n.attrs['id'] for n in Tree(result).nodes if 'id' in n.attrs)
    old_names=Counter(n.attrs['name'] for n in Tree(original).nodes if n.tag=='a' and 'name' in n.attrs)
    new_names=Counter(n.attrs['name'] for n in Tree(result).nodes if n.tag=='a' and 'name' in n.attrs)
    if old_ids != new_ids or old_names != new_names:
        raise EditError('Keep existing linked text in place so other pages can still find it.')
    return result

def clean_inserted_block(value, known_sources):
    if not isinstance(value,str) or len(value)>150000:
        raise EditError('That paragraph is too large.')
    # New paragraphs may carry existing citations but cannot create link targets
    # or build-template fields. Their one stable outer marker is assigned below.
    tree = Tree(value)
    if any('id' in node.attrs or 'name' in node.attrs or 'data-editor-block' in node.attrs for node in tree.nodes):
        raise EditError('New paragraphs cannot add linked identifiers. Paste just the text and formatting.')
    cleaned = InlineCleaner().finish(value)
    if '{{' in cleaned or '}}' in cleaned:
        raise EditError('New paragraphs cannot add generated fields.')
    if set(CITE.findall(cleaned)) - known_sources:
        raise EditError('Use only source references already present in the site’s source catalogue.')
    if not plain(CITE.sub('',cleaned)).strip():
        raise EditError('Add some text to the new paragraph before saving it.')
    return cleaned

def structural_changes(payload, text, block_map, *, end_offset=None):
    deletions = payload.get('deleteBlocks',[])
    additions = payload.get('insertBlocks',[])
    if (not isinstance(deletions,list) or not isinstance(additions,list)
            or len(deletions)+len(additions)>200):
        raise EditError('Reload this page before adding or removing paragraphs.')
    if any(not isinstance(key,str) for key in deletions) or len(set(deletions))!=len(deletions):
        raise EditError('Reload this page before removing paragraphs.')
    delete_nodes=[]
    for key in deletions:
        if key not in block_map: raise EditError('This paragraph changed. Reload the page before removing it.')
        node=block_map[key];capabilities=block_capabilities(text,node)
        if not capabilities['canDelete']: raise EditError(capabilities['deleteReason'])
        delete_nodes.append(node)
    existing={node.attrs['data-editor-block'] for node in Tree(text).nodes if 'data-editor-block' in node.attrs}
    known_sources=set(json.loads((ROOT/'content/sources.json').read_text())) if additions else set()
    insertions=[]
    for entry in additions:
        if not isinstance(entry,dict): raise EditError('Reload the page before adding a paragraph.')
        identity=entry.get('id');anchor_id=entry.get('anchor');position=entry.get('position')
        if (not isinstance(identity,str) or not re.fullmatch(r'new-[a-z0-9-]{1,76}',identity)
                or identity in existing):
            raise EditError('A new paragraph identifier is invalid or already in use. Reload the page.')
        at_end=anchor_id=='document-end' and position=='after' and end_offset is not None
        if (not at_end and (not isinstance(anchor_id,str) or anchor_id not in block_map or position not in ('before','after'))) or entry.get('tag')!='p':
            raise EditError('Choose a body insertion point beside an existing block or at the end of the document.')
        anchor=None if at_end else block_map[anchor_id]
        if anchor and not block_capabilities(text,anchor)['canInsert'+position.title()]:
            raise EditError('Add new paragraphs beside body text or headings, outside photos, lists and tables.')
        cleaned=clean_inserted_block(entry.get('html'),known_sources)
        align=clean_format(entry['format']) if 'format' in entry else ''
        existing.add(identity)
        style=f' style="text-align: {align}"' if align else ''
        markup=f'<p data-editor-block="{identity}"{style}>{cleaned}</p>'
        insertions.append({'id':identity,'anchor':anchor,'position':position,'tag':'p','html':cleaned,'format':{'align':align},
                           'markup':markup,'offset':end_offset if at_end else anchor.start if position=='before' else anchor.end})
    return delete_nodes,insertions

def normalized_patches(text, patches):
    """Coalesce insertions in visual order; allow deletion-boundary insertions."""
    inserts={};replacements=[]
    for start,end,value in patches:
        if type(start) is not int or type(end) is not int or not 0<=start<=end<=len(text) or not isinstance(value,str):
            raise EditError('A paragraph moved during this edit. Reload the page before saving.')
        if start==end: inserts.setdefault(start,[]).append(value)
        else: replacements.append((start,end,value))
    replacements.sort()
    if any(a[1]>b[0] for a,b in zip(replacements,replacements[1:])):
        raise EditError('These edits overlap. Save the paragraph and photograph changes separately.')
    if any(start<offset<end for offset in inserts for start,end,_ in replacements):
        raise EditError('A new paragraph overlaps removed text. Reload the page before saving.')
    return sorted(replacements+[(offset,offset,''.join(values)) for offset,values in inserts.items()])

def apply_patches(text, patches):
    for start,end,value in reversed(patches): text=text[:start]+value+text[end:]
    return text

def image_info(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=24:
        return 'png', *struct.unpack('>II',data[16:24])
    if data.startswith(b'\xff\xd8'):
        i=2
        while i+4<len(data):
            if data[i]!=255: i+=1; continue
            marker=data[i+1]; i+=2
            if marker in (0xd8,0xd9) or 0xd0<=marker<=0xd7: continue
            size=int.from_bytes(data[i:i+2],'big')
            if size<2: break
            if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf) and i+7<len(data):
                h,w=struct.unpack('>HH',data[i+3:i+7]); return 'jpg',w,h
            i+=size
    if data[:4]==b'RIFF' and data[8:12]==b'WEBP':
        kind=data[12:16]
        if kind==b'VP8X' and len(data)>=30:
            return 'webp',1+int.from_bytes(data[24:27],'little'),1+int.from_bytes(data[27:30],'little')
        if kind==b'VP8 ' and len(data)>=30 and data[23:26]==b'\x9d\x01\x2a':
            w,h=struct.unpack('<HH',data[26:30]); return 'webp',w&0x3fff,h&0x3fff
        if kind==b'VP8L' and len(data)>=25 and data[20]==0x2f:
            bits=int.from_bytes(data[21:25],'little'); return 'webp',(bits&0x3fff)+1,((bits>>14)&0x3fff)+1
    raise EditError('Choose a JPEG, PNG or WebP photograph.')

def opening_tag(node, changes):
    attrs={**node.attrs,**changes}
    return '<'+node.tag+''.join(' '+key+(f'="{escape(str(value),quote=True)}"' if value is not None else '') for key,value in attrs.items())+'>'

def save(payload):
    if PUBLISHER is not None and PUBLISHER.busy():
        raise EditError('Wait for the publishing checks or upload to finish before saving another edit.')
    with LOCK:
        if PUBLISHER is not None and PUBLISHER.busy():
            raise EditError('Wait for the publishing checks or upload to finish before saving another edit.')
        doc_id,lang=payload.get('id',''),payload.get('lang','')
        path,text,blocks,images=authored(doc_id,lang)
        if hashlib.sha256(text.encode()).hexdigest()!=payload.get('version'):
            raise EditError('This page changed elsewhere. Reload it before saving to keep the latest version.')
        changes=payload.get('blocks',{})
        photo_changes=payload.get('images',{})
        if not isinstance(changes,dict) or not isinstance(photo_changes,dict): raise EditError('Invalid changes.')
        block_map={str(n.start):n for n in blocks}
        image_map={str(n.start):n for n in images}
        if changes.keys()-block_map.keys() or photo_changes.keys()-image_map.keys(): raise EditError('Reload this page before saving.')
        formats=payload.get('blockFormats',{})
        if not isinstance(formats,dict) or formats.keys()-block_map.keys(): raise EditError('Reload this page before changing its formatting.')
        delete_images=payload.get('deleteImages',[])
        if not isinstance(delete_images,list) or any(not isinstance(key,str) or key not in image_map for key in delete_images) or len(set(delete_images))!=len(delete_images):
            raise EditError('Reload this page before removing photographs.')
        removed_images=[image_map[key] for key in delete_images]
        image_regions=[image_removal_node(image) for image in removed_images]
        delete_nodes,insertions=structural_changes(payload,text,block_map,end_offset=insertion_offset(doc_id,text))
        delete_nodes=list({node.start:node for node in delete_nodes+[block for block in blocks if any(region.start<=block.start and block.end<=region.end for region in image_regions)]}.values())
        deleted={str(node.start) for node in delete_nodes}
        sync = translator() if (ROOT/'local-editor/translation/settings.json').exists() else None
        if sync:
            sync.capture(doc_id)
        structure_plan = None
        if sync and (delete_nodes or insertions or removed_images):
            structure_plan=sync.plan_structure(doc_id,lang,delete_nodes,insertions,capabilities=block_capabilities,
                                               delete_images=removed_images, image_removal=image_removal_node,
                                               removal_patches=removal_patches, insertion_point=lambda value:insertion_offset(doc_id,value))
        patches=[]; new_files=[]; linked_patches={}; bn_patches=[]; bn_source=None
        if sync and sync.enabled and lang=='en' and photo_changes:
            bn_source=authored(doc_id,'bn')
        for key,value in changes.items():
            if key in deleted: continue
            n=block_map[key]
            original=text[n.opening:n.close]
            cleaned=clean_block(value,original)
            if cleaned!=original: patches.append((n.opening,n.close,cleaned))
        patches.extend(removal_patches(text,delete_nodes+image_regions))
        for key,value in formats.items():
            if key in deleted: continue
            n=block_map[key];align=clean_format(value)
            if align!=block_format(n)['align']: patches.append((n.start,n.opening,formatted_opening(n,align)))
        patches.extend((entry['offset'],entry['offset'],entry['markup']) for entry in insertions)
        for key,value in photo_changes.items():
            if key in delete_images: continue
            n=image_map[key]
            if not isinstance(value,dict): raise EditError('Invalid photograph change.')
            attrs={}
            if 'alt' in value:
                if not isinstance(value['alt'],str) or len(value['alt'])>3000: raise EditError('Use a short photo description.')
                attrs['alt']=value['alt']
            if value.get('dataUrl'):
                match=re.fullmatch(r'data:image/(?:jpeg|png|webp);base64,([A-Za-z0-9+/=\r\n]+)',value['dataUrl'])
                if not match: raise EditError('Choose a JPEG, PNG or WebP photograph.')
                data=base64.b64decode(match[1],validate=True)
                if len(data)>15*1024*1024: raise EditError('Choose a photograph smaller than 15 MB.')
                ext,w,h=image_info(data)
                if not (0<w<=30000 and 0<h<=30000): raise EditError('The photograph dimensions are not supported.')
                relative=f'assets/uploads/{doc_id}-{secrets.token_hex(6)}.{ext}'
                new_files.append((ROOT/relative,data))
                attrs.update(src=relative,width=str(w),height=str(h))
                if bn_source:
                    matches=[image for image in bn_source[3] if image.attrs.get('src')==n.attrs.get('src')]
                    if len(matches)==1:
                        image=matches[0]
                        bn_patches.append((image.start,image.opening,opening_tag(image,{'src':relative,'width':str(w),'height':str(h)})))
                        if image.parent and image.parent.tag=='a' and image.parent.attrs.get('href')==image.attrs['src']:
                            parent=image.parent
                            bn_patches.append((parent.start,parent.opening,opening_tag(parent,{'href':relative})))
                parent=n.parent
                if parent and parent.tag=='a' and parent.attrs.get('href')==n.attrs['src']:
                    linked_patches[parent.start]=(parent.start,parent.opening,opening_tag(parent,{'href':relative}))
            if attrs: patches.append((n.start,n.opening,opening_tag(n,attrs)))
        patches.extend(linked_patches.values())
        patches=normalized_patches(text,patches)
        updated=apply_patches(text,patches)
        related_patches={}
        if structure_plan:
            for entry in structure_plan.get('related',[]):
                other=Path(entry['path']);before=entry['before']
                if other!=source_path(doc_id,'bn' if lang=='en' else 'en') or other.read_text()!=before:
                    raise EditError('The matching language page changed. Reload before saving these paragraphs.')
                if other in related_patches and related_patches[other][0]!=before:
                    raise EditError('The matching language page changed. Reload before saving these paragraphs.')
                related_patches.setdefault(other,(before,[]))[1].extend(entry['patches'])
        if bn_patches:
            bn_path,bn_before,_,_=bn_source
            if bn_path in related_patches and related_patches[bn_path][0]!=bn_before:
                raise EditError('The Bengali page changed. Reload it before saving.')
            related_patches.setdefault(bn_path,(bn_before,[]))[1].extend(bn_patches)
        related=[]
        changes_by_lang={lang:{'path':path,'before':text,'after':updated,'patches':patches}}
        for other,(before,other_patches) in related_patches.items():
            other_patches=normalized_patches(before,other_patches)
            after=apply_patches(before,other_patches)
            related.append((other,before,after))
            changes_by_lang['bn' if lang=='en' else 'en']={'path':other,'before':before,'after':after,'patches':other_patches}
        if updated==text:
            return {'ok':True,'message':'No changes to save.','document':document(doc_id,lang)}
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)
        backup=ROOT/'local-editor/backups'/stamp
        backup.mkdir(parents=True)
        relative=path.relative_to(ROOT)
        (backup/relative).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,backup/relative)
        for other,_,_ in related:
            target=backup/other.relative_to(ROOT)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(other,target)
        history=ROOT/'content/page-history.json'
        history_before=history.read_bytes()
        (backup/'page-history.json').write_bytes(history_before)
        (backup/'change.json').write_text(json.dumps({'page':doc_id,'language':lang,'source':str(relative),'savedAt':stamp},indent=2))
        try:
            for asset,data in new_files:
                asset.parent.mkdir(parents=True,exist_ok=True); asset.write_bytes(data)
            temporary=path.with_suffix('.html.editor-tmp')
            temporary.write_text(updated); temporary.replace(path)
            for other,_,replacement in related:
                temporary=other.with_suffix('.html.editor-tmp')
                temporary.write_text(replacement); temporary.replace(other)
            logs=[]
            for command in ('build.py','scripts/check_site.py'):
                run=subprocess.run([sys.executable,str(ROOT/command)],cwd=ROOT,capture_output=True,text=True,timeout=180)
                logs.append(run.stdout+run.stderr)
                if run.returncode: raise EditError('The site check found a problem. Your previous version has been restored. '+(run.stderr or run.stdout)[-1600:])
            (backup/'checks.txt').write_text('\n'.join(logs))
        except Exception:
            path.write_text(text); history.write_bytes(history_before)
            for other,original,_ in related: other.write_text(original)
            for asset,_ in new_files:
                asset.unlink(missing_ok=True)
                (ROOT/'site'/asset.relative_to(ROOT)).unlink(missing_ok=True)
            try:
                subprocess.run([sys.executable,str(ROOT/'build.py')],cwd=ROOT,capture_output=True,timeout=180)
            finally:
                history.write_bytes(history_before)
            raise
        sync_message = ''
        if sync:
            try:
                if structure_plan and structure_plan.get('finish'):
                    structure_plan['finish'](changes_by_lang)
                sync.capture(doc_id)
            except Exception:
                # The authored save already succeeded. Never report it as lost
                # merely because the translation bookkeeping needs recovery.
                sync.error = 'Your changes are saved. Bengali tracking needs a retry before publishing.'
                sync_message = ' Bengali tracking needs attention.'
        return {'ok':True,'message':'Saved locally. Site checks passed. A backup is available.'+sync_message,'document':document(doc_id,lang)}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def local_request(self):
        if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
            self.send_error(403); return False
        return True
    def reply(self,status,data,kind='application/json; charset=utf-8'):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','SAMEORIGIN')
        if self.path in ('/','/editor.js','/editor.css'):
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(data)
    def file(self,base,name):
        candidate=base/name
        path=candidate.resolve()
        allowed=is_local_asset(ROOT,candidate) if base==ROOT/'assets' else path.is_relative_to(base.resolve())
        if not allowed or not path.is_file():
            self.reply(404,{'error':'File not found.'}); return
        self.reply(200,path.read_bytes(),mimetypes.guess_type(path)[0] or 'application/octet-stream')
    def do_GET(self):
        if not self.local_request(): return
        parsed=urlsplit(self.path); path=unquote(parsed.path)
        try:
            if path=='/':
                html=(ROOT/'local-editor/index.html').read_text().replace('__EDITOR_TOKEN__',TOKEN)
                self.reply(200,html.encode(),'text/html; charset=utf-8')
            elif path in ('/editor.js','/editor.css'):
                self.file(ROOT/'local-editor',path[1:])
            elif path=='/api/pages':
                with LOCK: result=pages()
                self.reply(200,result)
            elif path=='/api/publish/status':
                if not secrets.compare_digest(self.headers.get('X-Editor-Token',''),TOKEN):
                    self.reply(403,{'error':'Refresh the editor to reconnect.'})
                elif parse_qs(parsed.query).get('refresh') == ['1']:
                    self.reply(200,publisher().status(refresh=True))
                else: self.reply(200,publisher().status())
            elif path=='/api/translation/status':
                if not secrets.compare_digest(self.headers.get('X-Editor-Token',''),TOKEN):
                    self.reply(403,{'error':'Refresh the editor to reconnect.'})
                else: self.reply(200,translator().status())
            elif path=='/api/document':
                q=parse_qs(parsed.query)
                with LOCK: result=document(q.get('id',[''])[0],q.get('lang',['en'])[0])
                self.reply(200,result)
            elif path.startswith('/assets/'):
                self.file(ROOT/'assets',path[len('/assets/'):])
            elif path.startswith('/preview/'):
                self.file(ROOT/'site',path[len('/preview/'):])
            else: self.reply(404,{'error':'Page not found.'})
        except (EditError,ValueError) as exc: self.reply(400,{'error':str(exc)})
        except Exception as exc:
            print(type(exc).__name__,str(exc),file=sys.stderr)
            self.reply(500,{'error':'The editor could not open this page. Your files have not changed.'})
    def do_POST(self):
        if not self.local_request(): return
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:
            self.reply(403,{'error':'Open the editor on this Mac to save.'}); return
        if not secrets.compare_digest(self.headers.get('X-Editor-Token',''),TOKEN):
            self.reply(403,{'error':'Refresh the editor before saving.'}); return
        if self.path not in ('/api/save','/api/pages/create','/api/page-types/create','/api/publish/prepare','/api/publish/confirm',
                             '/api/translation/settings','/api/translation/retry','/api/translation/accept'):
            self.reply(404,{'error':'Not found.'}); return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>24*1024*1024: raise EditError('That upload is too large. Choose a smaller photograph.')
            payload=json.loads(self.rfile.read(size))
            if not isinstance(payload,dict): raise EditError('Invalid save request.')
            if self.path in ('/api/publish/prepare','/api/publish/confirm'):
                with LOCK:
                    translator().assert_publish_ready()
                    if self.path.endswith('/prepare'): result=publisher().start_prepare()
                    else: result=publisher().start_publish(payload.get('preparationId'))
                self.reply(202,result)
            elif self.path=='/api/translation/settings': self.reply(200,translator().configure(payload.get('enabled')))
            elif self.path=='/api/translation/retry': self.reply(200,translator().retry())
            elif self.path=='/api/translation/accept': self.reply(200,translator().accept(payload.get('id')))
            elif self.path=='/api/pages/create': self.reply(200,create_page(payload))
            elif self.path=='/api/page-types/create': self.reply(200,create_type(payload))
            else: self.reply(200,save(payload))
        except (EditError,ValueError) as exc: self.reply(400,{'error':str(exc)})
        except Exception as exc:
            print(type(exc).__name__,str(exc),file=sys.stderr)
            self.reply(500,{'error':'The changes could not be saved. Check the local editor window for details.'})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=45873)
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    url=f'http://127.0.0.1:{args.port}/'
    try: server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        # A second double-click reopens an already running editor, after identification.
        from urllib.request import urlopen
        try:
            with urlopen(url+'api/pages',timeout=2) as response:
                known=json.load(response)
            if not any(p.get('id')=='person-hare-krishna-konar' for p in known.get('pages',[])): raise ValueError()
        except Exception:
            raise SystemExit('The editor port is occupied. Close the other local server and try again.')
        if args.open:
            import webbrowser; webbrowser.open(url)
        return
    print('Aguri Heritage content editor: '+url,flush=True)
    print('Keep this window open while editing. Press Control+C to stop.',flush=True)
    if (ROOT/'local-editor/translation/settings.json').exists():
        translator().initialize(pages()['pages'])
    if args.open:
        import webbrowser; webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__': main()
