#!/usr/bin/env python3
"""Deterministic scoring, character lint and output-envelope checks. No model calls.

Python 3.9+; standard library only. These checks do not verify product facts,
judge creativity, approve publication or prove model compliance.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'references' / 'evaluation-profiles.json'
FAMILIES = {'advertising', 'ux', 'product', 'operational', 'educational'}
COMMON = {'brand_voice', 'product_relevance', 'clarity', 'surface_fit', 'language', 'task_effectiveness'}
GATES = {'product_reality', 'claim_evidence', 'agency_and_risk', 'action_and_context', 'financial_meaning', 'scope_and_privacy'}
GATE_STATES = {'pass', 'fail', 'unknown', 'not_applicable'}
READINESS = {'blocked_current_wording', 'needs_revision', 'needs_verification', 'suitable_for_defined_context'}


def rounded(value: Decimal) -> float:
    return float(value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))


def validate_weights(weights: Mapping[str, int]) -> None:
    if not weights or any(type(w) is not int or w <= 0 for w in weights.values()):
        raise ValueError('Weights must be positive integers, not booleans.')
    if sum(weights.values()) != 100:
        raise ValueError('Profile weights must sum to 100.')


def validate_scores(scores: Mapping[str, Optional[int]], weights: Mapping[str, int]) -> None:
    validate_weights(weights)
    if set(scores) != set(weights):
        raise ValueError('Scores must contain exactly the criteria in the selected profile.')
    for name, value in scores.items():
        if value is not None and (type(value) is not int or not 0 <= value <= 10):
            raise ValueError(f'{name}: use an integer from 0 to 10, or null for unknown.')


def validate_config(config: Mapping[str, Any]) -> None:
    if set(config['profiles']) != FAMILIES or set(config['common_criteria']) != COMMON:
        raise ValueError('Unexpected profile families or common criteria.')
    for name, weights in config['profiles'].items():
        validate_weights(weights)
        expected = COMMON | {'creativity', 'distinctiveness'} if name == 'advertising' else COMMON
        if set(weights) != expected:
            raise ValueError(f'{name}: unexpected criteria.')
    if set(config['gate_names']) != GATES or set(config['gate_states']) != GATE_STATES:
        raise ValueError('Unexpected gate schema.')
    if set(config['readiness_states']) != READINESS:
        raise ValueError('Unexpected readiness states.')
    base = config['base_score']
    if set(base['exclude']) != {'surface_fit'}:
        raise ValueError('Only surface_fit is excluded from base quality.')
    if set(base['required_observed']) != {'brand_voice', 'clarity', 'language'}:
        raise ValueError('Base quality requires the three language/meaning anchors.')
    if not 0 < base['minimum_weight_coverage'] <= 1:
        raise ValueError('Invalid minimum coverage.')


def load_config(path: Path = CONFIG) -> dict:
    config = json.loads(path.read_text(encoding='utf-8'))
    validate_config(config)
    return config


def quality_score(scores: Mapping[str, Optional[int]], weights: Mapping[str, int]) -> Optional[float]:
    """Legacy-compatible full score. A missing criterion never becomes zero."""
    validate_scores(scores, weights)
    if any(v is None for v in scores.values()):
        return None
    total = sum(Decimal(scores[k]) * weights[k] for k in weights)
    return rounded(total / 100)


def evaluate(record: Mapping[str, Any], config: Optional[dict] = None) -> dict:
    config = load_config() if config is None else config
    validate_config(config)
    family = record['profile']
    if family not in config['profiles']:
        raise ValueError('Unknown profile.')
    weights = config['profiles'][family]
    scores = record['scores']
    validate_scores(scores, weights)
    reasons = record.get('reasons', {})
    if set(reasons) != set(weights) or any(not isinstance(v, str) or not v.strip() for v in reasons.values()):
        raise ValueError('Each criterion, including an unknown one, needs an explicit reason.')
    gate_data = record.get('gates', {})
    if set(gate_data) != GATES:
        raise ValueError('Exactly six evidence gates are required.')
    for name, item in gate_data.items():
        if not isinstance(item, dict) or item.get('state') not in GATE_STATES:
            raise ValueError(f'{name}: invalid gate state.')
        if not isinstance(item.get('reason'), str) or not item['reason'].strip():
            raise ValueError(f'{name}: a gate reason is required.')
    material = record.get('material_copy_issue', False)
    if type(material) is not bool:
        raise ValueError('material_copy_issue must be a boolean.')

    base_keys = [k for k in weights if k not in config['base_score']['exclude']]
    observed = [k for k in base_keys if scores[k] is not None]
    base_total = sum(weights[k] for k in base_keys)
    base_observed = sum(weights[k] for k in observed)
    coverage = Decimal(base_observed) / base_total
    sufficient = (set(config['base_score']['required_observed']) <= set(observed)
                  and coverage >= Decimal(str(config['base_score']['minimum_weight_coverage'])))
    base_score = None
    if sufficient:
        base_score = rounded(sum(Decimal(scores[k]) * weights[k] for k in observed) / base_observed)

    unknown = [k for k in weights if scores[k] is None]
    failed_gates = [k for k, v in gate_data.items() if v['state'] == 'fail']
    unknown_gates = [k for k, v in gate_data.items() if v['state'] == 'unknown']
    weak = [k for k, v in scores.items() if v is not None and v <= config['quality_revision_floor']]
    creative_weak = []
    if family == 'advertising':
        creative_weak = [k for k, floor in config['advertising_revision_floor'].items()
                         if scores[k] is not None and scores[k] <= floor]
    revision = bool(material or weak or creative_weak)
    verification = bool(unknown_gates or unknown)
    if failed_gates:
        readiness = 'blocked_current_wording'
    elif revision:
        readiness = 'needs_revision'
    elif verification:
        readiness = 'needs_verification'
    else:
        readiness = 'suitable_for_defined_context'
    return {
        'version': config['version'], 'rubric_id': config['rubric_id'], 'profile': family,
        'base_score': base_score, 'base_weight_observed': base_observed,
        'base_weight_possible': base_total, 'base_coverage_percent': rounded(coverage * 100),
        'base_excluded': [k for k in base_keys if scores[k] is None],
        'base_score_reason': 'sufficient_observed_data' if sufficient else 'insufficient_anchors_or_coverage',
        'surface_score': scores['surface_fit'], 'overall_score': quality_score(scores, weights),
        'unknown_criteria': unknown,
        'criteria': [{'name': k, 'score': scores[k], 'weight': weights[k], 'reason': reasons[k]} for k in weights],
        'gates': gate_data, 'readiness': readiness, 'failed_gates': failed_gates,
        'needs_revision': revision, 'needs_verification': verification,
        'unknown_gates': unknown_gates, 'weak_criteria': sorted(set(weak + creative_weak)),
        'empirical_effectiveness_tested': False, 'publication_authorization': False,
        'example_only': record.get('example_only', False) is True,
    }


def lint_text(text: str, sensitive: bool = False) -> list:
    """Scan GENERATED prose only. Do not silently rewrite quotes, URLs or code."""
    findings = []
    codes = {0x064B: 'tanwin', 0x064C: 'tanwin', 0x064D: 'tanwin',
             0x061B: 'semicolon', ord(';'): 'semicolon', 0x064A: 'arabic_yeh', 0x0643: 'arabic_kaf'}
    for lineno, line in enumerate(text.splitlines(), 1):
        for column, character in enumerate(line, 1):
            code = codes.get(ord(character))
            if character in {'!', '\uff01'}:
                code = 'exclamation_in_sensitive_copy' if sensitive else 'exclamation_mark'
            if code:
                findings.append({'rule': code, 'line': lineno, 'column': column,
                                 'codepoint': f'U+{ord(character):04X}', 'severity': 'error'})
    return findings


def check_output_contract(envelope: Mapping[str, Any], *, intent: str, requested_count: Optional[int] = 1,
                          analysis_required: bool = True) -> list:
    """Structural test-harness envelope, not a mandatory user-facing JSON shape."""
    errors = []
    copy = envelope.get('copy', [])
    if not isinstance(copy, list) or any(not isinstance(t, str) or not t.strip() for t in copy):
        errors.append('copy_must_be_a_list_of_nonempty_strings')
        copy = []
    if intent == 'audit':
        if copy:
            errors.append('unsolicited_rewrite_in_audit')
        if not isinstance(envelope.get('verdict'), str) or not envelope['verdict'].strip():
            errors.append('missing_verdict')
    elif intent in {'create', 'edit', 'optimize', 'adapt'}:
        if not copy:
            errors.append('missing_copy_or_safe_draft')
        if requested_count is not None and len(copy) != requested_count:
            errors.append('wrong_output_count')
    if analysis_required:
        review = envelope.get('evaluation')
        if not isinstance(review, dict):
            errors.append('missing_evaluation')
        else:
            for field in ('rationale', 'limitation', 'usage_status'):
                if not isinstance(review.get(field), str) or not review[field].strip():
                    errors.append('missing_' + field)
            if not review.get('scores') and not review.get('score_limitation'):
                errors.append('missing_scores_or_explained_limitation')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    score = commands.add_parser('score', help='Compute scores from a reasoned evaluation record.')
    score.add_argument('record', type=Path)
    lint = commands.add_parser('lint', help='Lint generated Persian prose, not raw input quotations.')
    lint.add_argument('text_file', type=Path)
    lint.add_argument('--sensitive', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'score':
            result = evaluate(json.loads(args.record.read_text(encoding='utf-8')))
            exit_code = 0
        else:
            result = {'findings': lint_text(args.text_file.read_text(encoding='utf-8'), args.sensitive)}
            exit_code = int(bool(result['findings']))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Validation error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
