#!/usr/bin/env python3
"""Local, resumable Bengali OCR. Originals are never modified.

Each PDF page is a scanned spread, not a printed page. Split the spread
before recognition so Tesseract can find the two columns on each leaf.
Machine confidence is a triage signal, not a measure of historical accuracy.
Requires Pillow, pypdf, Poppler and Tesseract with ben+eng language data.
"""
from pathlib import Path
import concurrent.futures, csv, io, json, os, subprocess, tempfile
from PIL import Image, ImageOps
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'

def process(job):
    volume, page = job
    slug = f'v{volume}-{page:03}'
    out = ASSETS / 'ocr' / f'{slug}.json'
    if out.exists():
        return json.loads(out.read_text())
    pdf = ASSETS / 'documents' / f'Ugrakshatriya_Pratinidhi_Vol_{volume:02}.pdf'
    with tempfile.TemporaryDirectory(prefix='aguri-ocr-') as tmp:
        prefix = str(Path(tmp) / 'spread')
        subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile',
                        '-scale-to','3800','-gray','-png',str(pdf),prefix],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        im = Image.open(prefix + '.png').convert('L')
        preview = im.copy()
        preview.thumbnail((1900,1900))
        preview.save(ASSETS / 'scans' / f'{slug}.jpg',quality=85,optimize=True)
        w,h = im.size
        texts, scores = [], []
        for side, (x0,x1) in [('left',(0,w//2)),('right',(w//2,w))]:
            leaf = ImageOps.autocontrast(im.crop((x0,int(h*.035),x1,int(h*.97))))
            leafpath = Path(tmp) / f'{side}.png'
            leaf.save(leafpath)
            base = str(Path(tmp) / side)
            env = dict(os.environ, OMP_THREAD_LIMIT='1')
            subprocess.run(['tesseract',str(leafpath),base,'-l','ben+eng','--psm','3','txt','tsv'],
                           check=True,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            texts.append({'side':side,'text':Path(base+'.txt').read_text().strip()})
            for row in csv.DictReader(io.StringIO(Path(base+'.tsv').read_text()),delimiter='\t'):
                if row.get('text','').strip() and float(row['conf']) >= 0:
                    scores.append(float(row['conf']))
        record = {'id':slug,'volume':volume,'scan':page,'status':'machine-ocr-unreviewed',
                  'meanWordConfidence':round(sum(scores)/len(scores),1) if scores else None,
                  'leaves':texts}
        out.write_text(json.dumps(record,ensure_ascii=False,indent=2))
        return record

def main():
    jobs = []
    for v in (1,2):
        count = len(PdfReader(ASSETS/'documents'/f'Ugrakshatriya_Pratinidhi_Vol_{v:02}.pdf').pages)
        jobs.extend((v,p) for p in range(1,count+1))
    records=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for i,record in enumerate(pool.map(process,jobs),1):
            records.append(record)
            if i % 10 == 0 or i==len(jobs):
                print(f'OCR complete: {i}/{len(jobs)} scanned spreads',flush=True)
    records.sort(key=lambda x:(x['volume'],x['scan']))
    (ASSETS/'ocr-data.js').write_text('window.JOURNAL_OCR = '+json.dumps(records,ensure_ascii=False)+';\n')
    for v in (1,2):
        chunks=['UNREVIEWED MACHINE OCR — consult the source scan; scan numbers are PDF pages.\n']
        for r in records:
            if r['volume']==v:
                chunks.append(f"\n=== VOLUME {v} / SCAN {r['scan']} ===\n")
                chunks.extend(f"\n[{l['side']} leaf]\n{l['text']}\n" for l in r['leaves'])
        (ASSETS/'ocr'/f'volume-{v}-machine-ocr.txt').write_text(''.join(chunks))
    print('Wrote searchable OCR index and plain-text downloads.',flush=True)

if __name__=='__main__':
    main()
