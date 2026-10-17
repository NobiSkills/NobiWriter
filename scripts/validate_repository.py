"""Structural validation, not model evaluation."""
from pathlib import Path
import json, re, sys
from urllib.parse import unquote
import yaml
from jsonschema import Draft202012Validator, FormatChecker
ROOT = Path(__file__).resolve().parents[1]
def validate(root=ROOT):
    errors=[]
    for name in ['README.md','VERSION','CHANGELOG.md','skills/nobiwriter/SKILL.md','docs/installation.md','scripts/package_skill.py']:
        if not (root/name).is_file(): errors.append(f'Missing: {name}')
    for p in root.rglob('*'):
        if not p.is_file() or set(p.parts)&{'.git','dist','__pycache__'} or p.suffix not in {'.md','.json','.yaml','.yml','.txt','.py'}: continue
        text=p.read_text()
        if re.search(r'^(?:<{7}|={7}|>{7})(?: |$)',text,re.M): errors.append(f'Conflict: {p}')
        try:
            if p.suffix=='.json': json.loads(text)
            if p.suffix in {'.yaml','.yml'}: yaml.safe_load(text)
        except (ValueError,yaml.YAMLError) as e: errors.append(f'{p}: {e}')
        if p.suffix=='.md':
            for t in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
                t=t.split('#',1)[0]
                if t and not re.match(r'\w+:',t) and not (p.parent/unquote(t)).exists(): errors.append(f'Broken link: {p} -> {t}')
    try:
        m=yaml.safe_load((root/'skills/nobiwriter/SKILL.md').read_text().split('---',2)[1])
        if set(m)!={'name','description'} or m['name']!='nobiwriter' or not m['description']: errors.append('Invalid skill frontmatter')
    except (IndexError,TypeError,yaml.YAMLError): errors.append('Missing skill frontmatter')
    for sample,schema in [('brief','brief'),('claim-record','claim'),('product-facts','product-facts')]:
        spec=json.loads((root/f'schemas/{schema}.schema.json').read_text())
        Draft202012Validator.check_schema(spec)
        for e in Draft202012Validator(spec,format_checker=FormatChecker()).iter_errors(json.loads((root/f'examples/{sample}.json').read_text())): errors.append(f'{sample}: {e.message}')
    cases=json.loads((root/'evals/cases.json').read_text())
    if len({c['id'] for c in cases})!=len(cases): errors.append('Duplicate evaluation ID')
    if any(not c.get('prompt') or not c.get('acceptance') for c in cases): errors.append('Incomplete evaluation')
    version=(root/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or version not in (root/'CHANGELOG.md').read_text(): errors.append('Version mismatch')
    return errors
if __name__=='__main__':
    errors=validate()
    print('\n'.join(errors) if errors else 'PASS: structure, local links, JSON/YAML, skill metadata, example schemas and evaluation records')
    sys.exit(bool(errors))
