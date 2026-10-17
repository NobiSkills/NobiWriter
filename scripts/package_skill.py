"""Build a portable skill archive after structural validation."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from validate_repository import validate
root=Path(__file__).resolve().parents[1]
errors=validate(root)
if errors: raise SystemExit('\n'.join(errors))
version=(root/'VERSION').read_text().strip()
source=root/'skills/nobiwriter'
output=root/'dist'/f'nobiwriter-{version}.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output,'w',ZIP_DEFLATED) as z:
    for p in sorted(source.rglob('*')):
        if p.is_file(): z.write(p,p.relative_to(source.parent))
print(f'Built {output.relative_to(root)}')
