"""Install pinned official Tesseract models in the private runtime; verifies Git blob hashes."""
import hashlib
import os
from pathlib import Path
import sys
import httpx

ROOT=Path(__file__).resolve().parents[1]
target=Path(os.environ.get('HOTEL_DATA_DIR',ROOT/'.runtime'))/'ocr/tessdata'
revision='87416418657359cb625c412a48b6e1d6d41c29bd'
models={'chi_sim':'388bac276d033d06e5ed5ba7a7ad14ae58f97dab','eng':'bbef4675053b5b468cdb477053e28b1c698ba08e'}
def verified(data,expected):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==expected
target.mkdir(parents=True,exist_ok=True)
with httpx.Client(timeout=60,follow_redirects=True) as client:
 for name,expected in models.items():
  path=target/(name+'.traineddata')
  if path.exists() and verified(path.read_bytes(),expected):continue
  response=client.get(f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{revision}/{name}.traineddata');response.raise_for_status()
  if not verified(response.content,expected):raise SystemExit('Official model checksum mismatch; installation refused')
  path.write_bytes(response.content)
print('Pinned Chinese/English OCR models installed and verified in runtime; no system changes.')
