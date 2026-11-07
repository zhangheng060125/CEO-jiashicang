"""Package source and templates, excluding runtime databases, credentials, caches and VCS."""
from pathlib import Path
import zipfile,sys
root=Path(__file__).resolve().parents[1]
output=Path(sys.argv[1]) if len(sys.argv)>1 else root.parent/'senhuo-ceo-source.zip'
excluded={'.runtime','.git','__pycache__','node_modules','.pytest_cache','.venv','private_media','ocr'}
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
 for p in root.rglob('*'):
  rel=p.relative_to(root)
  if p.name in ['admin-password.txt','production.env']:continue
  if not p.is_file() or any(part in excluded for part in rel.parts) or p.suffix in ['.sqlite3','.db','.log','.pyc','.zip','.part'] or p.resolve()==output.resolve():continue
  archive.write(p,Path('CEO-jiashicang')/rel)
print('Source release packaged without runtime secrets or databases.')
