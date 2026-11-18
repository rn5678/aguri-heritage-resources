"""Keep the bilingual collection chronological without changing featured selection."""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portrait_headers import COLLECTION_SELECTION, PROFILE_PATTERN

# Birth years stated in the existing authored biographies. Same-year ties retain
# their earlier collection order; undated profiles are not assigned guessed years.
# Sandip Nandy: 1975-01-15, https://www.the-aiff.com/media/uploads/2019/12/First-List-of-Inter-State-Transfer-First-Window-June-9-to-Aug-31-2013.pdf
# ISL 2014-09-04 profile independently reports age 39, consistent with that year.
ORDER = ['pratap-chandra-ray', 'satya-kinkar-sahana', 'jadabendra-nath-panja',
         'ganapati-panja', 'benoy-choudhury', 'dasarathi-tah',
         'shib-shankar-chowdhury', 'hare-krishna-konar', 'ramapada-chowdhury',
         'tuhin-kumar-roy', 'shakti-samanta', 'benoy-krishna-konar',
         'ranjit-kumar-panja', 'ajit-kumar-panja', 'nikhilananda-sar',
         'sandip-nandy', 'manohar-ray']


class PeopleChronology(unittest.TestCase):
    def test_both_authored_collections_have_same_birth_year_order(self):
        for prefix in ('', 'bn/'):
            body = (ROOT / f'content/{prefix}people.html').read_text()
            self.assertEqual([m[0] for m in re.findall(PROFILE_PATTERN, body, re.S)], ORDER)
            self.assertEqual(body.count('class="small people-chronology-note"'), 1)

    def test_featured_carousel_selection_is_unchanged(self):
        self.assertEqual(COLLECTION_SELECTION,
                         ('ajit-kumar-panja', 'shakti-samanta', 'ramapada-chowdhury',
                          'jadabendra-nath-panja', 'ganapati-panja',
                          'hare-krishna-konar', 'satya-kinkar-sahana'))


if __name__ == '__main__':
    unittest.main()
