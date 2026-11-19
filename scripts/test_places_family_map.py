import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSET = 'assets/maps/burdwan-family-villages-complete.png'

class PlacesFamilyMapTests(unittest.TestCase):
    def test_exact_approved_image(self):
        self.assertEqual(hashlib.sha256((ROOT / ASSET).read_bytes()).hexdigest(),
                         '36c460fcdb06d0b3b0212ef8403f8dc483678771cd9b9cab0df5ed833a766cfc')

    def test_bilingual_accessible_map_and_existing_places(self):
        for lang in ('en', 'bn'):
            path = ROOT / 'content' / ('bn/geography.html' if lang == 'bn' else 'geography.html')
            page = path.read_text()
            self.assertEqual(page.count('id="family-villages-map"'), 1)
            self.assertIn(f'src="{ASSET}"', page)
            self.assertIn('width="5280" height="6380"', page)
            self.assertIn('loading="lazy"', page)
            self.assertEqual(page.count(f'href="{ASSET}"'), 2)
            self.assertIn('https://www.openstreetmap.org/copyright', page)
            for anchor in ('reading-old-place-names', 'places-to-explore', 'water-landscape'):
                self.assertIn(f'id="{anchor}"', page)

if __name__ == '__main__':
    unittest.main()
