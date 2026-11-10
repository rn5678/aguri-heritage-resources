"""Bilingual FAQ and navigation regressions for the approved public page."""
from pathlib import Path
from types import SimpleNamespace
import re
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
from homepage import CHROME
from localization import PAGES_BN
ROOT=Path(__file__).resolve().parents[1]

class FAQ(unittest.TestCase):
    def test_last_navigation_link_in_both_shells(self):
        self.assertEqual(build.NAV_KEYS[-1], 'faq')
        for lang in ('en','bn'):
            header=CHROME[lang][0]
            nav=re.search(r'<nav.*?</nav>',header,re.S).group()
            self.assertEqual(re.findall(r'href="([^"]+)"',nav)[-1],'faq.html')
    def test_reviewed_nine_answers_and_parity(self):
        ids=[]
        for suffix in ('','bn/'):
            body=(ROOT/'content'/f'{suffix}faq.html').read_text()
            keys=re.findall(r'<h2 id="([^"]+)"',body)
            self.assertEqual(len(keys),9)
            ids.append(keys)
            self.assertNotIn('18 May 2026',body)
            self.assertNotIn('১৮ মে ২০২৬',body)
            self.assertNotIn('Is Kesh an Aguri surname?',body)
            self.assertNotIn('Editorial review before publication',body)
            self.assertEqual(len(re.findall(r'class="text-link"',body)),9)
        self.assertEqual(*ids)
    def test_page_metadata_and_current_navigation(self):
        key,label,title,desc=next(p for p in build.PAGES if p[0]=='faq')
        for lang,suffix in (('en',''),('bn','bn/')):
            if lang=='bn': label,title,desc=PAGES_BN['faq']
            labels={k:(PAGES_BN[k][0] if lang=='bn' else l) for k,l,*_ in build.PAGES}
            body,_=build.render_page(key,label,title,desc,(ROOT/'content'/f'{suffix}faq.html').read_text(),lang,{},labels,SimpleNamespace(updated=lambda *args:'2026-11-10'))
            self.assertIn(f'<link rel="canonical" href="https://aguri-heritage.in/{suffix}faq">',body)
            self.assertIn('<a href="faq.html" aria-current="page">',body)
            self.assertIn('hreflang="bn"',body)
            self.assertIn('hreflang="en"',body)

if __name__=='__main__': unittest.main()
