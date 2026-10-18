"""Build dist/skill.zip after repository and bundle validation."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from validate_repository import validate

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'__pycache__', '.pytest_cache', '.DS_Store'}
LIMIT = 25 * 1024 * 1024


def build(root: Path = ROOT) -> Path:
    errors = validate(root)
    if errors:
        raise ValueError('\n'.join(errors))
    source = root / 'skills/nobiwriter'
    subprocess.run([sys.executable, str(source / 'tests/check_bundle.py')], check=True)
    files = []
    for path in sorted(source.rglob('*')):
        if SKIP.intersection(path.parts) or path.suffix == '.pyc':
            continue
        if path.is_symlink():
            raise ValueError('Refusing to package a symlink: ' + str(path.relative_to(root)))
        if path.is_file():
            files.append(path)
    output = root / 'dist/skill.zip'
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix('.zip.tmp')
    try:
        with ZipFile(temporary, 'w', ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(source.parent))
        if temporary.stat().st_size > LIMIT:
            raise ValueError('Skill ZIP exceeds 25 MiB.')
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


if __name__ == '__main__':
    try:
        print('Built ' + str(build().relative_to(ROOT)))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))
