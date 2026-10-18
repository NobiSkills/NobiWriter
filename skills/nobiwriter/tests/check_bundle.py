#!/usr/bin/env python3
"""Static checks only. This does not execute a model or a product UI."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Mapping

CRITERIA = {'brand_voice', 'product_relevance', 'clarity', 'surface_fit', 'language', 'task_effectiveness'}
FAMILIES = {'advertising', 'ux', 'product', 'operational', 'educational'}
INTENTS = {'create', 'edit', 'audit', 'optimize', 'adapt', 'plan'}


def quality_score(scores: Mapping[str, int | None], weights: Mapping[str, int]) -> float | None:
    if set(scores) != CRITERIA or set(weights) != CRITERIA:
        raise ValueError('Exactly six declared criteria are required.')
    if any(type(w) is not int or w <= 0 for w in weights.values()) or sum(weights.values()) != 100:
        raise ValueError('Weights must be positive integers summing to 100.')
    for score in scores.values():
        if score is not None and (type(score) is not int or not 0 <= score <= 10):
            raise ValueError('A criterion must be an integer from 0 to 10 or null.')
    if any(score is None for score in scores.values()):
        return None
    return round(sum(scores[k] * weights[k] for k in CRITERIA) / 100, 1)


def usage_status(gates: list[str], material_copy_issue: bool = False) -> str:
    allowed = {'pass', 'fail', 'unknown', 'not_applicable'}
    if not gates or any(g not in allowed for g in gates):
        raise ValueError('Provide valid gate states.')
    if 'fail' in gates:
        return 'blocked_current_wording'
    if 'unknown' in gates:
        return 'needs_verification'
    if material_copy_issue:
        return 'needs_revision'
    return 'suitable_for_defined_context'


def validate(root: Path) -> dict:
    root = root.resolve()
    errors: list[str] = []
    core = root / 'SKILL.md'
    if not core.is_file():
        raise ValueError('Missing SKILL.md')
    text = core.read_text(encoding='utf-8')
    front = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not front or not re.search(r'^name:\s*nobiwriter\s*$', front.group(1), re.M):
        errors.append('Invalid name/frontmatter')
    if len(text.splitlines()) >= 500:
        errors.append('SKILL.md exceeds the compact-entrypoint target')
    required = [
        'references/intent-routing.md', 'references/product-taxonomy.md',
        'references/touchpoint-surface-map.md', 'references/evaluation-framework.md',
        'references/evaluation-profiles.json', 'references/output-contract.md',
        'references/brand-voice.md', 'references/claims.md', 'references/vocabulary.md',
        'references/product-rules.md', 'references/copywriting-and-landings.md',
        'references/ux-and-microcopy-patterns.md', 'references/review.md',
        'references/gold-campaign-exemplar.md', 'templates/request-context.yaml',
        'tests/routing-evaluation-cases.json', 'tests/README.md',
        'tests/results-template.json', 'agents/openai.yaml',
    ]
    for rel in required:
        p = root / rel
        if not p.is_file() or p.is_symlink():
            errors.append(f'Missing/unsafe required file: {rel}')
        if rel.startswith('references/') and f']({rel})' not in text:
            errors.append(f'No direct entrypoint link: {rel}')
    local_links = 0
    for md in root.rglob('*.md'):
        if md.is_symlink():
            continue
        body = md.read_text(encoding='utf-8')
        for target in re.findall(r'\[[^\]\n]*\]\(([^)\s]+)\)', body):
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('#'):
                continue
            target = target.split('#', 1)[0]
            if not target:
                continue
            candidate = (md.parent / target).resolve()
            local_links += 1
            if not candidate.is_relative_to(root) or not candidate.exists():
                errors.append(f'Broken/out-of-bundle link in {md.relative_to(root)}: {target}')
    profile = json.loads((root / 'references/evaluation-profiles.json').read_text(encoding='utf-8'))
    if set(profile['profiles']) != FAMILIES:
        errors.append('Unexpected profile families')
    for name, weights in profile['profiles'].items():
        try:
            assert quality_score(dict.fromkeys(CRITERIA, 8), weights) == 8.0
            partial = dict.fromkeys(CRITERIA, 8)
            partial['surface_fit'] = None
            assert quality_score(partial, weights) is None
            mixed = dict.fromkeys(CRITERIA, 8)
            mixed['clarity'] = 10
            assert quality_score(mixed, weights) == round(8 + 2 * weights['clarity'] / 100, 1)
            try:
                quality_score(dict.fromkeys(CRITERIA, True), weights)
                errors.append(f'{name}: boolean accepted as a score')
            except ValueError:
                pass
        except (AssertionError, ValueError) as exc:
            errors.append(f'Profile failure: {name}: {exc}')
    assert usage_status(['pass', 'fail']) == 'blocked_current_wording'
    assert usage_status(['unknown', 'fail']) == 'blocked_current_wording'
    assert usage_status(['pass', 'unknown']) == 'needs_verification'
    assert usage_status(['pass'], True) == 'needs_revision'
    assert usage_status(['pass', 'not_applicable']) == 'suitable_for_defined_context'
    suite = json.loads((root / 'tests/routing-evaluation-cases.json').read_text(encoding='utf-8'))
    ids = [c['id'] for c in suite['cases']]
    if len(ids) != len(set(ids)):
        errors.append('Duplicate regression test IDs')
    for case in suite['cases']:
        if case['intent'] not in INTENTS or not case['must'] or not case['must_not']:
            errors.append(f'Incomplete behavioral case: {case["id"]}')
    result = {'static_validation': 'passed' if not errors else 'failed',
              'local_links_checked': local_links,
              'quality_profiles_checked': len(profile['profiles']),
              'behavioral_cases_defined': len(ids),
              'behavioral_cases_executed': 0,
              'model_behavior_validated': False,
              'errors': errors}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill_directory', nargs='?', default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    try:
        result = validate(Path(args.skill_directory))
    except (ValueError, KeyError, OSError, json.JSONDecodeError, AssertionError) as exc:
        print(f'Static validation failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result['errors'] else 1

if __name__ == '__main__':
    sys.exit(main())
