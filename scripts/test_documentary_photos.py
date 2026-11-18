"""Guard the scoped documentary-photo release and protected homepage artwork."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DocumentaryPhotoTests(unittest.TestCase):
    def test_separate_photographs_and_rights(self):
        catalog = json.loads((ROOT / 'assets/page-artworks/catalog.json').read_text())
        for key, name in [('water-landscape', 'damodar-burnpur-2008.jpg'), ('food-and-village-life', 'ranaghat-paddy-2020.jpg')]:
            item = catalog[key]
            self.assertEqual(item['file'], 'assets/documentary-photos/' + name)
            self.assertTrue((ROOT / item['file']).is_file())
            self.assertIn('commons.wikimedia.org', item['source_url'])
            for lang in ('en', 'bn'):
                self.assertTrue(item['caption_' + lang])
                self.assertTrue(item['alt_' + lang])
            self.assertTrue((ROOT / 'assets/social' / (key + '.jpg')).is_file())

    def test_inline_photos_stay_in_correct_sections(self):
        for prefix in ('', 'bn/'):
            food = (ROOT / 'content' / (prefix + 'food-and-village-life.html')).read_text()
            start = food.index('id="macher-tok-and-family-memory"')
            photo = food.index('assets/documentary-photos/sarbamangala-2007.jpg')
            self.assertLess(start, photo)
            self.assertLess(food.index('[cite:food-sarbamangala-2025]', start), photo)
            self.assertIn('max-width:375px', food)
            culture = (ROOT / 'content' / (prefix + 'culture.html')).read_text()
            self.assertLess(culture.index('id="manasa"'), culture.index('assets/documentary-photos/manasa-met-2011-499.jpg'))
            self.assertIn('2011.499', culture)
            self.assertIn('CC0', culture)

    def test_protected_homepage_artwork(self):
        expected = '3a3b1aee8ec9f5ec6018a4337d12fbe75ff8f7164983dc192d150ca790df7708'
        self.assertEqual(hashlib.sha256((ROOT / 'assets/burdwan-river-of-memory.webp').read_bytes()).hexdigest(), expected)
        for prefix in ('', 'bn/'):
            home = (ROOT / 'content' / (prefix + 'index.html')).read_text()
            self.assertIn('assets/burdwan-river-of-memory.webp', home)
            self.assertNotIn('assets/documentary-photos/', home)

if __name__ == '__main__':
    unittest.main()
