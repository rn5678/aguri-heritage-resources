import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_links import open_file_links

class FileLinksTest(unittest.TestCase):
    def test_pdf_opens_without_download(self):
        text = open_file_links('<a href="assets/a.pdf" download="a.pdf">Download PDF ↓</a>')
        self.assertNotIn('download', text)
        self.assertIn('target="_blank"', text)
        self.assertIn('rel="noopener"', text)
        self.assertIn('Open PDF ↗', text)

    def test_bengali_and_nested_content(self):
        self.assertIn('খুলুন <span>↗</span>', open_file_links('<a href="../assets/a.txt" download>ডাউনলোড করুন <span>↓</span></a>'))

    def test_journal_routes_keep_fragments(self):
        for prefix in ('assets/', '../assets/', '/assets/', 'https://aguri-heritage.in/assets/'):
            text = open_file_links(f'<a href="{prefix}documents/Ugrakshatriya_Pratinidhi_Vol_01.pdf#page=4">PDF</a>')
            self.assertIn('href="/api/documents/Ugrakshatriya_Pratinidhi_Vol_01.pdf#page=4"', text)

    def test_external_destinations_preserved(self):
        href = 'https://example.org/a.pdf?x=1&amp;y=2#page=3'
        self.assertIn('href="' + href + '"', open_file_links('<a href="' + href + '">Read</a>'))

    def test_source_pages_untouched(self):
        for href in ('https://commons.wikimedia.org/wiki/File:book.pdf', 'https://archive.org/details/in.ernet.dli.2015.1', 'https://doi.org/10.1000/123.4', 'history.html#part'):
            anchor = '<a href="' + href + '">Source</a>'
            self.assertEqual(open_file_links(anchor), anchor)

    def test_extensionless_file(self):
        text = open_file_links('<a href="https://ir.nbu.ac.in/bitstreams/36c0b35a-8abc-4cec-9126-563695a6c862/download">PDF</a>')
        self.assertIn('target="_blank"', text)

    def test_image_and_existing_rel(self):
        text = open_file_links('<a href="image.JPG" rel="noreferrer"><img src="image.JPG" alt="Photo"></a>')
        self.assertIn('<img src="image.JPG" alt="Photo">', text)
        self.assertIn('rel="noreferrer noopener"', text)
        self.assertEqual(open_file_links(text), text)

    def test_unquoted_attributes(self):
        text = open_file_links('<a href=assets/a.pdf download>PDF</a>')
        self.assertIn('href="assets/a.pdf"', text)
        self.assertNotIn('download', text)

    def test_quoted_angle_bracket(self):
        text = open_file_links('<a title="Size > 1 MB" href="a.pdf" download>PDF</a>')
        self.assertIn('title="Size &gt; 1 MB"', text)
        self.assertIn('href="a.pdf"', text)
        self.assertNotIn('download', text)

if __name__ == '__main__':
    unittest.main()
