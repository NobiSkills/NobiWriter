#!/usr/bin/env python3
"""Render a calculated score record as Markdown or an accessible SVG.

Standard library only. SVG display depends on the host. Always retain the
Markdown assessment when inline graphics are unavailable. Never accept a
hand-supplied aggregate: recompute it from the criterion scores and weights.
"""
from __future__ import annotations
import argparse
import json
import sys
from html import escape
from pathlib import Path
from typing import Optional
from quality_tools import evaluate, load_config

DIGITS = str.maketrans('0123456789.', '\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9\u066b')


def number(value) -> str:
    return str(value).translate(DIGITS)


def grade(score: Optional[float]) -> tuple:
    if score is None:
        return 'unknown', '#6b7280'
    if score < 5:
        return 'weak', '#b91c1c'
    if score < 8:
        return 'developing', '#926600'
    return 'strong', '#166534'


def markdown(record: dict) -> str:
    config = load_config()
    result = evaluate(record, config)
    labels = config['labels_fa']
    lines = ['## ' + labels['title']]
    if result['example_only']:
        lines.append('**' + labels['example'] + '**')
    for key in ('base_score', 'surface_score', 'overall_score'):
        val = result[key]
        lines.append('**' + labels[key] + ':** ' + (labels['unknown'] if val is None else number(val) + '/\u06f1\u06f0'))
    lines += ['**' + labels['coverage'] + ':** ' + number(result['base_coverage_percent']) + '\u066a',
              '**' + labels['readiness'] + ':** ' + labels[result['readiness']], '',
              '| ' + ' | '.join(labels[k] for k in ('criterion', 'score', 'weight', 'bar', 'reason')) + ' |',
              '| --- | --- | --- | --- | --- |']
    for row in result['criteria']:
        value = row['score']
        bar = '\u2014' if value is None else '\u2588' * value + '\u2591' * (10 - value)
        reason = row['reason'].replace('|', '\\|').replace('\n', ' ')
        score = labels['unknown'] if value is None else number(value)
        lines.append('| ' + ' | '.join([labels[row['name']], score, number(row['weight']), bar, reason]) + ' |')
    lines += ['', labels['note']]
    if result['needs_verification']:
        lines.append(labels['needs_verification'])
    return '\n'.join(lines) + '\n'


def svg(record: dict) -> str:
    config = load_config()
    result = evaluate(record, config)
    labels = config['labels_fa']
    width = 960
    height = 240 + len(result['criteria']) * 54
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
             '<title id="title">' + escape(labels['title']) + '</title>',
             '<desc id="desc">' + escape(labels['note']) + '</desc>',
             '<rect width="100%" height="100%" rx="18" fill="#ffffff"/>',
             '<g font-family="DejaVu Sans, Tahoma, Arial, sans-serif" fill="#172033">']
    def text(x, y, value, size=18, color='#172033'):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" direction="rtl" text-anchor="start">{escape(str(value))}</text>')
    text(924, 37, labels['title'], 23)
    if result['example_only']:
        text(924, 63, labels['example'], 14)
    summary = []
    for key in ('base_score', 'surface_score', 'overall_score'):
        val = result[key]
        summary.append(labels[key] + ': ' + (labels['unknown'] if val is None else number(val) + '/\u06f1\u06f0'))
    text(924, 94, ' | '.join(summary), 16)
    text(924, 123, labels['readiness'] + ': ' + labels[result['readiness']], 16)
    text(924, 151, labels['coverage'] + ': ' + number(result['base_coverage_percent']) + '\u066a', 14)
    for index, row in enumerate(result['criteria']):
        y = 177 + 54 * index
        score = row['score']
        label, color = grade(score)
        parts.append(f'<rect x="30" y="{y}" width="375" height="16" rx="8" fill="#edf0f4"/>')
        if score is not None:
            parts.append(f'<rect x="30" y="{y}" width="{375 * score / 10:g}" height="16" rx="8" fill="{color}"/>')
        text(540, y + 14, labels[label], 15, color)
        text(670, y + 14, labels['unknown'] if score is None else number(score) + '/\u06f1\u06f0', 16)
        text(924, y + 14, labels[row['name']] + ' (' + number(row['weight']) + '\u066a)', 16)
    text(924, height - 27, labels['note'], 14)
    parts += ['</g>', '</svg>']
    return '\n'.join(parts) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--format', choices=['markdown', 'svg'], default='markdown')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        record = json.loads(args.record.read_text(encoding='utf-8'))
        rendered = svg(record) if args.format == 'svg' else markdown(record)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding='utf-8')
        else:
            print(rendered, end='')
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f'Render error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
