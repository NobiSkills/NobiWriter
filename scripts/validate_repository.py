"""Repository structural validation, not model evaluation."""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote
try:
    import yaml
    from jsonschema import Draft202012Validator, FormatChecker
except ModuleNotFoundError as exc:
    raise SystemExit('Missing development dependency. In your virtual environment run: '
                     'python -m pip install -r requirements-dev.txt') from exc

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {'.git', '.venv', 'venv', 'dist', 'build', '__pycache__', '.pytest_cache'}
TEXT_SUFFIXES = {'.md', '.json', '.yaml', '.yml', '.txt', '.py'}


def validate(root: Path = ROOT) -> list:
    root = root.resolve()
    errors = []
    required = ['README.md', 'VERSION', 'CHANGELOG.md', 'skills/nobiwriter/SKILL.md',
                'skills/nobiwriter/VERSION', 'docs/installation.md', 'scripts/package_skill.py']
    for name in required:
        if not (root / name).is_file():
            errors.append('Missing: ' + name)
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            p = Path(directory) / name
            if p.is_symlink():
                errors.append('Non-portable file symlink: ' + str(p.relative_to(root)))
                continue
            if p.suffix not in TEXT_SUFFIXES:
                continue
            try:
                text = p.read_text(encoding='utf-8')
                if re.search(r'^(?:<{7}|={7}|>{7})(?: |$)', text, re.M):
                    errors.append('Conflict: ' + str(p.relative_to(root)))
                if p.suffix == '.json': json.loads(text)
                if p.suffix in {'.yaml', '.yml'}: yaml.safe_load(text)
                if p.suffix == '.md':
                    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
                        target = target.split('#', 1)[0]
                        if target and not re.match(r'\w+:', target):
                            resolved = (p.parent / unquote(target)).resolve()
                            if not resolved.is_relative_to(root) or not resolved.exists():
                                errors.append(f'Broken/out-of-repository link: {p.relative_to(root)} -> {target}')
            except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
                errors.append(f'{p.relative_to(root)}: {exc}')
    try:
        meta = yaml.safe_load((root / 'skills/nobiwriter/SKILL.md').read_text(encoding='utf-8').split('---', 2)[1])
        if set(meta) != {'name', 'description'} or meta['name'] != 'nobiwriter' or not meta['description']:
            errors.append('Invalid skill frontmatter')
        for sample, schema in [('brief', 'brief'), ('claim-record', 'claim'), ('product-facts', 'product-facts')]:
            spec = json.loads((root / f'schemas/{schema}.schema.json').read_text(encoding='utf-8'))
            Draft202012Validator.check_schema(spec)
            data = json.loads((root / f'examples/{sample}.json').read_text(encoding='utf-8'))
            for error in Draft202012Validator(spec, format_checker=FormatChecker()).iter_errors(data):
                errors.append(f'{sample}: {error.message}')
        cases = json.loads((root / 'evals/cases.json').read_text(encoding='utf-8'))
        if len({c['id'] for c in cases}) != len(cases): errors.append('Duplicate evaluation ID')
        if any(not c.get('prompt') or not c.get('acceptance') for c in cases): errors.append('Incomplete evaluation')
        version = (root / 'VERSION').read_text(encoding='utf-8').strip()
        bundled = (root / 'skills/nobiwriter/VERSION').read_text(encoding='utf-8').strip()
        if not re.fullmatch(r'\d+\.\d+\.\d+', version) or version != bundled or version not in (root / 'CHANGELOG.md').read_text(encoding='utf-8'):
            errors.append('Version mismatch')
    except (OSError, ValueError, KeyError, IndexError, TypeError, yaml.YAMLError) as exc:
        errors.append('Metadata/schema validation: ' + str(exc))
    return errors


if __name__ == '__main__':
    errors = validate()
    print('\n'.join(errors) if errors else 'PASS: structure, local links, JSON/YAML, metadata, schemas and evaluation records')
    sys.exit(bool(errors))
