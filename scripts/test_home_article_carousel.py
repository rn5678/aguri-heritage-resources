from pathlib import Path
import sys
import unittest
from html.parser import HTMLParser
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from home_article_carousel import articles,render,render_spotlight,spotlight_article,article_link,teasers,ROOT
from build import PAGES
class CarouselTests(unittest.TestCase):
 def test_all_editorial_articles_and_profiles_in_both_editions(self):
  en,bn=articles('en',PAGES),articles('bn',PAGES)
  self.assertEqual([x[0] for x in en],[x[0] for x in bn])
  self.assertEqual(len(en),len({x[0] for x in en}))
  self.assertTrue({'origins','person-sandip-nandy','translation-electricity','translation-journal-autobiography','translation-prabasi-book-review'} <= {x[0] for x in en})
  for lang in ('en','bn'):
   for key,title,image in articles(lang,PAGES):
    self.assertTrue(title);self.assertTrue((ROOT/image).is_file())
   out=render(lang,PAGES)
   self.assertEqual(out.count('data-home-article-slide'),len(en))
   self.assertEqual(out.count(' hidden'),len(en)-2) # all except three cards, plus controls
   self.assertNotIn('story-text',out)
   for restored in ('story-grid home-article-track','class="story-body"','class="story-link"','carousel-controls home-article-controls'):
    self.assertIn(restored,out)
   for control in ('data-home-prev','data-home-next','data-home-pause'):self.assertIn(control,out)
 def test_one_carousel_and_unrelated_content_preserved(self):
  for lang in ('en','bn'):
   s=(ROOT/'content'/('bn' if lang=='bn' else '')/'index.html').read_text()
   self.assertEqual(s.count('<!-- home-article-carousel -->'),1)
   self.assertNotIn('data-story-carousel',s)
   for section in ('quick-links','welcome','resources','invitation'):self.assertIn('class="'+section+'"',s)
 def test_curated_artwork_replaces_dense_charts_and_reading_scans(self):
  expected={'origins':'assets/page-artworks/origins-armoured.webp',
   'military-settlers-bengal':'assets/military-settlers/header.webp'}
  for slug in ('journal-autobiography','electricity','prabasi-book-review'):
   expected['translation-'+slug]='assets/page-artworks/translation-'+slug+'.webp'
  for lang in ('en','bn'):
   images={k:image for k,_,image in articles(lang,PAGES)}
   for key,image in expected.items(): self.assertEqual(images[key],image)
   self.assertEqual(images['person-sandip-nandy'],'assets/people/sandip-nandy.jpg')
 def test_bilingual_teasers_and_localized_future_fallback(self):
  import json
  from unittest.mock import patch
  curated=json.loads((ROOT/'content/home-carousel-teasers.json').read_text())
  for lang in ('en','bn'):
   rows=articles(lang,PAGES);lines=teasers(lang,PAGES)
   for key,_,_ in rows:
    self.assertTrue(lines[key].strip())
    self.assertNotIn('\n',lines[key])
    self.assertEqual(lines[key],curated[key][lang])
   self.assertEqual(render(lang,PAGES).count('class="home-article-teaser"'),len(rows))
  fake={'pages':[{'id':'future-story','en':{'description':'A new story'},'bn':{'description':'একটি নতুন গল্প'}}]}
  with patch('home_article_carousel.load_registry',return_value=fake):
   self.assertEqual(teasers('bn',PAGES)['future-story'],'একটি নতুন গল্প')
  css=(ROOT/'assets/homepage-hero-carousel.css').read_text()
  for rule in ('white-space:nowrap','text-overflow:ellipsis','font-size:13px'):self.assertIn(rule,css)
 def test_fixed_spotlight_uses_publication_not_recent_edit(self):
  rows=articles('en',PAGES)
  self.assertEqual(spotlight_article(rows)[0],'aguri-working-lives-colonial-india')
  for lang in ('en','bn'):
   hero=render_spotlight(lang,PAGES)
   self.assertEqual(hero.count('data-home-spotlight'),1)
   self.assertNotIn('data-home-article-carousel',hero)
   self.assertNotIn('<button',hero)
  sample=[('old','Old','x'),('new','New','y')]
  history={'en/old':{'baseline':{'date':'2025-01-01'},'updated':'2027-01-01'},'en/new':{'baseline':{'date':'2026-01-01'}}}
  self.assertEqual(spotlight_article(sample,history,{'article_id':None})[0],'new')
  self.assertEqual(spotlight_article(sample,history,{'article_id':'old'})[0],'old')
  with self.assertRaises(ValueError):spotlight_article(sample,history,{'article_id':'invalid'})
 def test_english_only_reading_targets_are_explicit_in_bengali(self):
  self.assertEqual(article_link('translation-electricity','bn'),('../translation-electricity.html',' hreflang="en"'))
 def test_responsive_cards_and_original_spotlight_frame_ratio(self):
  css=(ROOT/'assets/homepage-hero-carousel.css').read_text()
  for rule in ('aspect-ratio:4/3','repeat(3,minmax(0,1fr))','max-width:899px','max-width:599px',':focus-within'):
   self.assertIn(rule,css)
if __name__=='__main__':unittest.main()
