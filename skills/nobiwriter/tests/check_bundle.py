#!/usr/bin/env python3
"""Check bundle structure and rubric metadata. Does not execute a model."""
from __future__ import annotations
import argparse
import ast
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from quality_tools import load_config

INTENTS = {'create', 'edit', 'audit', 'optimize', 'adapt', 'plan'}
REQUIRED_REFS = [
    'intent-routing.md', 'product-taxonomy.md', 'touchpoint-surface-map.md',
    'evaluation-framework.md', 'evaluation-profiles.json', 'output-contract.md',
    'brand-voice.md', 'claims.md', 'vocabulary.md', 'product-rules.md',
    'copywriting-and-landings.md', 'ux-and-microcopy-patterns.md', 'review.md',
    'gold-campaign-exemplar.md', 'creative-quality.md', 'safe-alternatives.md',
    'final-copy-lint.md', 'visual-evaluation.md', 'strategic-creative-reasoning.md',
    'reference-loading-audit.md',
]


def validate(root: Path = ROOT) -> dict:
    root = root.resolve()
    errors = []
    required = ['SKILL.md', 'VERSION', 'agents/openai.yaml', 'assets/icon.svg',
                'scripts/quality_tools.py', 'scripts/render_scorecard.py',
                'templates/request-context.yaml', 'templates/evaluation-record.json',
                'tests/README.md', 'tests/results-template.json',
                'tests/prior-round-results.json', 'tests/routing-evaluation-cases.json',
                'tests/release-1.2.0-cases.json', 'tests/release-1.3.0-cases.json',
                'tests/activation-routing-cases.json', 'tests/test_quality_tools.py']
    required += ['references/' + name for name in REQUIRED_REFS]
    for name in required:
        p = root / name
        if not p.is_file() or p.is_symlink():
            errors.append('Missing or unsafe file: ' + name)
    if errors:
        return {'static_validation': 'failed', 'errors': errors}
    core = (root / 'SKILL.md').read_text(encoding='utf-8')
    front = re.match(r'^---\n(.*?)\n---\n', core, re.S)
    if not front or set(re.findall(r'^(\w+):', front.group(1), re.M)) != {'name', 'description'}:
        errors.append('Expected name/description YAML frontmatter only')
    elif not re.search(r'^name:\s*nobiwriter\s*$', front.group(1), re.M):
        errors.append('Invalid skill name')
    if len(core.splitlines()) >= 500:
        errors.append('Entrypoint exceeds the compact 500-line target')
    for name in REQUIRED_REFS:
        if '](references/' + name + ')' not in core:
            errors.append('Missing direct entrypoint reference: ' + name)
    # Frontmatter controls skill discovery, so keep it concise and valid.
    desc_match = re.search(r'^description:\s*(.+)$', front.group(1), re.M) if front else None
    if not desc_match or not 1 <= len(desc_match.group(1)) <= 1024:
        errors.append('Discovery description must be between 1 and 1024 characters')
    links = 0
    python_files = 0
    for p in root.rglob('*'):
        if '__pycache__' in p.parts:
            continue
        if p.is_symlink():
            errors.append('Non-portable symlink: ' + str(p.relative_to(root)))
            continue
        if not p.is_file():
            continue
        if p.suffix in {'.md', '.json', '.yaml', '.yml', '.py'}:
            text = p.read_text(encoding='utf-8')
            if re.search(r'^(?:<{7}|={7}|>{7})(?: |$)', text, re.M):
                errors.append('Unresolved conflict: ' + str(p.relative_to(root)))
            if p.suffix == '.json':
                json.loads(text)
            if p.suffix == '.py':
                ast.parse(text, filename=str(p), feature_version=(3, 9))
                python_files += 1
            if p.suffix == '.md':
                for target in re.findall(r'\[[^\]\n]*\]\(([^)\s]+)\)', text):
                    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('#'):
                        continue
                    target = unquote(target.split('#', 1)[0])
                    candidate = (p.parent / target).resolve()
                    links += 1
                    if not candidate.is_relative_to(root) or not candidate.exists():
                        errors.append(f'Broken/out-of-bundle link: {p.relative_to(root)} -> {target}')
    config = load_config(root / 'references/evaluation-profiles.json')
    version = (root / 'VERSION').read_text(encoding='utf-8').strip()
    if version != config['version'] or version not in core:
        errors.append('Bundle version mismatch')
    cases = []
    for name in ('routing-evaluation-cases.json', 'release-1.2.0-cases.json', 'release-1.3.0-cases.json'):
        suite = json.loads((root / 'tests' / name).read_text(encoding='utf-8'))
        if name == 'release-1.3.0-cases.json' and suite['version'] != version:
            errors.append('Test suite version mismatch: ' + name)
        for case in suite['cases']:
            if case.get('intent') not in INTENTS or not case.get('prompt') or not case.get('must') or not case.get('must_not'):
                errors.append('Incomplete case: ' + str(case.get('id')))
            cases.append(case['id'])
    if len(cases) != len(set(cases)):
        errors.append('Duplicate behavioral test ID')
    activation = json.loads((root / 'tests/activation-routing-cases.json').read_text(encoding='utf-8'))
    activations = activation.get('cases', [])
    if len(activations) != 20 or sum(case.get('expected_trigger') is True for case in activations) != 10:
        errors.append('Expected 10 positive and 10 negative activation tests')
    if activation.get('base_version') != version:
        errors.append('Activation suite version mismatch')
    for case in activations:
        if not case.get('prompt') or type(case.get('expected_trigger')) is not bool:
            errors.append('Invalid activation case: ' + str(case.get('id')))
        if case.get('expected_trigger') is True:
            if case.get('expected_operation') not in INTENTS or not case.get('expected_family'):
                errors.append('Missing positive activation routing: ' + str(case.get('id')))
            ref = case.get('expected_reference')
            if not ref or ref not in REQUIRED_REFS:
                errors.append('Unknown expected reference: ' + str(case.get('id')))
    result_template = json.loads((root / 'tests/results-template.json').read_text(encoding='utf-8'))
    if result_template['skill_version'] != version or {r['case_id'] for r in result_template['runs']} != set(cases):
        errors.append('Result template does not cover the current suite')
    return {'static_validation': 'passed' if not errors else 'failed', 'version': version,
            'local_links_checked': links, 'quality_profiles_checked': len(config['profiles']),
            'python_files_parsed_for_3_9': python_files, 'behavioral_cases_defined': len(cases),
            'activation_cases_defined': len(activations),
            'behavioral_cases_executed_in_this_command': 0, 'model_behavior_validated': False,
            'errors': errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill_directory', nargs='?', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = validate(args.skill_directory)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(bool(result['errors']))
    except (ValueError, KeyError, TypeError, OSError, SyntaxError) as exc:
        print(f'Static validation failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
