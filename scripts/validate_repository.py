from pathlib import Path
import json
import re
import sys
import yaml
from jsonschema import Draft202012Validator, FormatChecker

root = Path(__file__).resolve().parents[1]
skill = root / 'skills' / 'nobiwriter'
errors = []
text = (skill / 'SKILL.md').read_text(encoding='utf-8')
parts = text.split('---', 2)
meta = yaml.safe_load(parts[1]) if len(parts) == 3 else {}
if set(meta) != {'name', 'description'} or meta.get('name') != 'nobiwriter':
    errors.append('Invalid skill frontmatter')
if len(text.splitlines()) >= 500:
    errors.append('SKILL.md exceeds line budget')
for path in root.rglob('*.md'):
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):
            continue
        if not (path.parent / target.split('#', 1)[0]).exists():
            errors.append(f'Broken link: {path.relative_to(root)} -> {target}')
validators = {}
for path in (root / 'schemas').glob('*.schema.json'):
    data = json.loads(path.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(data)
    validators[path.name.split('.')[0]] = Draft202012Validator(data, format_checker=FormatChecker())
for name, schema_name in [('claims', 'claim'), ('product-facts', 'product-facts')]:
    for record in json.loads((root / 'data' / f'{name}.json').read_text(encoding='utf-8')):
        errors.extend(str(e) for e in validators[schema_name].iter_errors(record))
brief = json.loads((root / 'data' / 'example-brief.json').read_text(encoding='utf-8'))
errors.extend(str(e) for e in validators['brief'].iter_errors(brief))
cases = json.loads((root / 'evals' / 'cases.json').read_text(encoding='utf-8'))
if len({c['id'] for c in cases}) != len(cases) or any(not c['acceptance'] for c in cases):
    errors.append('Invalid evaluation cases')
# An allowed record without evidence and a recorded decision must be rejected.
invalid = {'id':'negative-test','claim_text':'test','claim_type':'capability','product':'test','scope':'test','evidence_required':'test','evidence_existing':[],'status':'allowed','exceptions':[]}
if validators['claim'].is_valid(invalid):
    errors.append('Claim schema accepted an unsupported allowed claim')
interface = yaml.safe_load((skill / 'agents' / 'openai.yaml').read_text(encoding='utf-8'))['interface']
if '$nobiwriter' not in interface['default_prompt']:
    errors.append('Missing skill invocation in default prompt')
if errors:
    print('\n'.join(errors))
    sys.exit(1)
print(f'PASS: skill metadata, local links, 3 schemas, demo data and {len(cases)} evaluation definitions. Behavioral model evaluation not run.')
