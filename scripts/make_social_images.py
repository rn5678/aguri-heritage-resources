#!/usr/bin/env python3
"""Create 1200×630 JPEG link-preview images from the page artwork catalogue.

Messaging apps and social networks show these when a page is shared. JPEG is
used because WebP previews are not displayed by every app. Requires Pillow;
the normal site build does not. Re-run after adding or changing page artwork.
"""
from pathlib import Path
import json
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
catalog = json.loads((ROOT / 'assets/page-artworks/catalog.json').read_text())
out = ROOT / 'assets/social'
out.mkdir(exist_ok=True)
for key, item in catalog.items():
    if key == '404':
        continue
    with Image.open(ROOT / item['file']) as source:
        image = ImageOps.fit(source.convert('RGB'), (1200, 630), Image.LANCZOS, centering=(0.5, 0.45))
    image.save(out / f'{key}.jpg', 'JPEG', quality=82, optimize=True, progressive=True)
print(f'{len(list(out.glob("*.jpg")))} preview images in {out.relative_to(ROOT)}')
