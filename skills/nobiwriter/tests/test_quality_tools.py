"""Mechanical regression tests on hand-authored fixtures, not model outputs."""
from __future__ import annotations
import copy
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from quality_tools import (load_config, evaluate, quality_score, lint_text,
                           check_output_contract, validate_config)
from render_scorecard import markdown, svg, grade


def fixture(profile='advertising'):
    config = load_config()
    weights = config['profiles'][profile]
    return {'example_only': True, 'profile': profile, 'scores': dict.fromkeys(weights, 8),
            'reasons': dict.fromkeys(weights, 'Hand-authored test fixture; not a real assessment.'),
            'gates': {k: {'state': 'pass', 'reason': 'Fixture assumption only.'} for k in config['gate_names']},
            'material_copy_issue': False}


def envelope():
    return {'copy': ['One usable piece of copy.'], 'evaluation': {'rationale': 'A reason.',
            'limitation': 'A stated limit.', 'scores': {'clarity': 8}, 'usage_status': 'needs_verification'}}


class ScoreTests(unittest.TestCase):
    def test_all_profiles_sum_to_100(self):
        c = load_config()
        self.assertEqual(len(c['profiles']), 5)
        for weights in c['profiles'].values():
            self.assertEqual(sum(weights.values()), 100)

    def test_full_equal_scores(self):
        for name in load_config()['profiles']:
            r = evaluate(fixture(name))
            self.assertEqual((r['base_score'], r['surface_score'], r['overall_score']), (8.0, 8, 8.0))

    def test_unknown_surface_keeps_base(self):
        f = fixture(); f['scores']['surface_fit'] = None
        r = evaluate(f)
        self.assertEqual(r['base_score'], 8.0)
        self.assertEqual(r['base_coverage_percent'], 100.0)
        self.assertIsNone(r['overall_score'])
        self.assertIsNone(r['surface_score'])
        self.assertEqual(r['readiness'], 'needs_verification')

    def test_partial_base_discloses_coverage(self):
        f = fixture(); f['scores']['product_relevance'] = None
        r = evaluate(f)
        self.assertEqual(r['base_score'], 8)
        self.assertEqual(r['base_weight_observed'], 70)
        self.assertEqual(r['base_coverage_percent'], 82.4)
        self.assertEqual(r['base_excluded'], ['product_relevance'])
        self.assertIsNone(r['overall_score'])

    def test_all_unknown_is_not_zero(self):
        f = fixture(); f['scores'] = dict.fromkeys(f['scores'])
        r = evaluate(f)
        self.assertIsNone(r['base_score']); self.assertIsNone(r['overall_score'])

    def test_missing_anchor_blocks_base(self):
        f = fixture(); f['scores']['clarity'] = None
        self.assertIsNone(evaluate(f)['base_score'])

    def test_low_coverage_blocks_base(self):
        f = fixture()
        f['scores'] = {k: 8 if k in {'brand_voice', 'clarity', 'language'} else None for k in f['scores']}
        self.assertIsNone(evaluate(f)['base_score'])

    def test_boolean_score_rejected(self):
        f = fixture(); f['scores']['clarity'] = True
        with self.assertRaises(ValueError): evaluate(f)

    def test_fractional_criterion_rejected(self):
        f = fixture(); f['scores']['clarity'] = 8.5
        with self.assertRaises(ValueError): evaluate(f)

    def test_out_of_range_rejected(self):
        for value in (-1, 11):
            f = fixture(); f['scores']['clarity'] = value
            with self.assertRaises(ValueError): evaluate(f)

    def test_missing_criterion_rejected(self):
        f = fixture(); del f['scores']['creativity']
        with self.assertRaises(ValueError): evaluate(f)

    def test_extra_criterion_rejected(self):
        f = fixture(); f['scores']['safety'] = 10
        with self.assertRaises(ValueError): evaluate(f)

    def test_bad_weights_rejected(self):
        c = load_config(); c['profiles']['advertising']['creativity'] = 14
        with self.assertRaises(ValueError): validate_config(c)

    def test_half_up_rounding(self):
        self.assertEqual(quality_score({'a': 8, 'b': 9}, {'a': 55, 'b': 45}), 8.5)

    def test_creative_floor_overrides_high_average(self):
        f = fixture(); f['scores'] = dict.fromkeys(f['scores'], 10); f['scores']['creativity'] = 5
        r = evaluate(f)
        self.assertEqual(r['overall_score'], 9.3)
        self.assertEqual(r['readiness'], 'needs_revision')

    def test_no_creativity_penalty_for_ux(self):
        r = evaluate(fixture('ux'))
        self.assertNotIn('creativity', [row['name'] for row in r['criteria']])
        self.assertFalse(r['needs_revision'])

    def test_fail_gate_overrides_quality(self):
        f = fixture(); f['gates']['claim_evidence']['state'] = 'fail'
        self.assertEqual(evaluate(f)['readiness'], 'blocked_current_wording')

    def test_unknown_gate_requires_verification(self):
        f = fixture(); f['gates']['claim_evidence']['state'] = 'unknown'
        self.assertEqual(evaluate(f)['readiness'], 'needs_verification')

    def test_revision_and_unknown_both_retained(self):
        f = fixture(); f['scores']['language'] = 3; f['scores']['surface_fit'] = None
        r = evaluate(f)
        self.assertTrue(r['needs_revision']); self.assertTrue(r['needs_verification'])
        self.assertEqual(r['readiness'], 'needs_revision')

    def test_missing_gate_rejected(self):
        f = fixture(); del f['gates']['claim_evidence']
        with self.assertRaises(ValueError): evaluate(f)

    def test_missing_reason_rejected(self):
        f = fixture(); f['reasons']['clarity'] = ''
        with self.assertRaises(ValueError): evaluate(f)

    def test_fixture_is_labeled(self):
        self.assertTrue(evaluate(fixture())['example_only'])
        self.assertFalse(evaluate(fixture())['empirical_effectiveness_tested'])


class LintTests(unittest.TestCase):
    def test_all_tanwin_marks(self):
        self.assertEqual(len(lint_text('x\u064b x\u064c x\u064d')), 3)

    def test_tanwin_in_analysis_from_report(self):
        data = json.loads((ROOT / 'tests/prior-round-results.json').read_text(encoding='utf-8'))
        row = next(r for r in data['runs'] if r['id'] == 'manual-T10')
        self.assertIn('tanwin', [v['rule'] for v in lint_text(row['source_excerpt'])])

    def test_both_semicolons(self):
        self.assertEqual(len(lint_text('a;b\u061bc')), 2)

    def test_arabic_letters(self):
        self.assertEqual([r['rule'] for r in lint_text('\u064a\u0643')], ['arabic_yeh', 'arabic_kaf'])

    def test_persian_letters_clean(self):
        self.assertEqual(lint_text('\u06cc\u06a9'), [])

    def test_sensitive_exclamation(self):
        self.assertEqual(lint_text('Done!'), [])
        self.assertEqual(lint_text('Done!', True)[0]['rule'], 'exclamation_in_sensitive_copy')

    def test_input_quote_not_automatically_scanned(self):
        payload = {'input_quote': 'x\u064b', 'generated_copy': 'Corrected copy.'}
        self.assertEqual(lint_text(payload['generated_copy']), [])


class ContractTests(unittest.TestCase):
    def test_one_copy_and_review(self):
        self.assertEqual(check_output_contract(envelope(), intent='create'), [])

    def test_missing_review_detected(self):
        self.assertIn('missing_evaluation', check_output_contract({'copy': ['One slogan.']}, intent='create'))

    def test_explicit_no_analysis(self):
        self.assertEqual(check_output_contract({'copy': ['One slogan.']}, intent='create', analysis_required=False), [])

    def test_audit_does_not_rewrite(self):
        e = envelope(); e['verdict'] = 'Needs revision.'
        self.assertIn('unsolicited_rewrite_in_audit', check_output_contract(e, intent='audit'))

    def test_wrong_count_detected(self):
        e = envelope(); e['copy'].append('Another option.')
        self.assertIn('wrong_output_count', check_output_contract(e, intent='create'))

    def test_safe_draft_required_for_creation(self):
        e = envelope(); e['copy'] = []
        self.assertIn('missing_copy_or_safe_draft', check_output_contract(e, intent='create'))

    def test_unknown_scores_need_explanation(self):
        e = envelope(); e['evaluation']['scores'] = {}
        self.assertIn('missing_scores_or_explained_limitation', check_output_contract(e, intent='create'))
        e['evaluation']['score_limitation'] = 'Not enough information.'
        self.assertEqual(check_output_contract(e, intent='create'), [])


class RenderTests(unittest.TestCase):
    def test_markdown_bars(self):
        rendered = markdown(fixture())
        self.assertIn('\u2588' * 8 + '\u2591' * 2, rendered)
        self.assertNotIn('<badge', rendered)

    def test_unknown_value_is_not_zero(self):
        f = fixture(); f['scores']['surface_fit'] = None
        rendered = markdown(f)
        self.assertIn('\u2014', rendered)
        self.assertEqual(grade(None)[0], 'unknown')

    def test_svg_valid_and_accessible(self):
        text = svg(fixture())
        root = ET.fromstring(text)
        self.assertEqual(root.attrib['role'], 'img')
        self.assertEqual(len(root.findall('{http://www.w3.org/2000/svg}title')), 1)
        self.assertNotIn('<script', text)

    def test_chart_does_not_trust_supplied_total(self):
        f = fixture(); f['overall_score'] = 1000
        self.assertNotIn('1000', svg(f))
        self.assertEqual(evaluate(f)['overall_score'], 8)

    def test_color_thresholds(self):
        self.assertEqual([grade(x)[0] for x in (4.9, 5, 7.9, 8)], ['weak', 'developing', 'developing', 'strong'])


if __name__ == '__main__':
    unittest.main()
