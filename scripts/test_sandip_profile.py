"""Regression checks for the bilingual Sandip Nandy profile."""
from pathlib import Path
import re,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from profile_pages import profiles
ROOT=Path(__file__).resolve().parents[1]
class SandipProfile(unittest.TestCase):
 def test_bilingual_route_collection_and_credits(self):
  for lang,name in [('en','Sandip Nandy'),('bn','সন্দীপ নন্দী')]:
   pages,descriptors=profiles(lang)
   self.assertIn('person-sandip-nandy',pages)
   self.assertIn('href="person-sandip-nandy.html"',pages['people'])
   self.assertIn(name,pages['person-sandip-nandy'])
   source=(ROOT/'content'/('bn' if lang=='bn' else '')/'people.html').read_text()
   article=re.search(r'<article class="person-profile" aria-labelledby="sandip-nandy">.*?</article>',source,re.S).group()
   self.assertIn('sandip-nandy.jpg',article)
   self.assertIn('https://creativecommons.org/licenses/by-sa/3.0/',article)
   self.assertIn('Rufyrosh',article)
 def test_citation_parity(self):
  cites=[]
  for suffix in ('','bn/'):
   source=(ROOT/'content'/f'{suffix}people.html').read_text()
   article=re.search(r'<article class="person-profile" aria-labelledby="sandip-nandy">.*?</article>',source,re.S).group()
   cites.append(re.findall(r'\[cite:([^]]+)\]',article))
  self.assertEqual(*cites)
if __name__=='__main__':unittest.main()
