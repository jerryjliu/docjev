"""Read-only intake check for the next 40-document challenge. Never runs inference."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'financial_report', 'press_release', 'legal_notice', 'correspondence', 'other'}


def check_intake(root: Path = ROOT) -> list[str]:
    with (root / 'datasets/real-challenge/review.csv').open(newline='') as source:
        rows = list(csv.DictReader(source))
    blockers = []
    if len(rows) != 40 or len({row['id'] for row in rows}) != 40:
        blockers.append('Exactly 40 unique originals are required.')
    if Counter(row['category'] for row in rows) != Counter(dict.fromkeys(CATEGORIES, 8)):
        blockers.append('Each of the five categories requires eight originals.')
    forbidden = set()
    for base in ('datasets/real-small/v1/originals', 'examples/real/originals'):
        forbidden.update(hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / base).glob('*.pdf'))
    seen, pages = set(), 0
    for row in rows:
        label = row['id']
        required = ('path', 'source_url', 'sha256', 'page_count', 'issuer', 'template_family',
                    'rights_note', 'label_evidence', 'scan', 'ambiguous', 'attachment')
        missing = [field for field in required if not row.get(field, '').strip()]
        if missing:
            blockers.append(f'{label}: source intake incomplete ({", ".join(missing)}).')
            continue
        if not row['source_url'].startswith('https://'):
            blockers.append(f'{label}: source URL must identify a public HTTPS source.')
        for field in ('scan', 'ambiguous', 'attachment'):
            if row[field] not in ('yes', 'no'):
                blockers.append(f'{label}: {field} must be yes or no after inspection.')
        path = (root / row['path']).resolve()
        originals = (root / 'datasets/real-challenge/originals').resolve()
        if not path.is_relative_to(originals) or path.suffix.lower() != '.pdf' or not path.is_file():
            blockers.append(f'{label}: expected an original PDF within datasets/real-challenge/originals/.')
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row['sha256'] or digest in seen or digest in forbidden:
            blockers.append(f'{label}: hash mismatch, duplicate, or previously used source.')
        seen.add(digest)
        try:
            count = len(PdfReader(path).pages)
            if count != int(row['page_count']) or count < 1:
                raise ValueError('page count mismatch')
            pages += count
        except Exception:
            blockers.append(f'{label}: unreadable PDF or page count mismatch.')
        if row['ambiguous'] == 'yes' or row['attachment'] == 'yes':
            if row.get('human_review_status') != 'approved' or not row.get('human_reviewer', '').strip():
                blockers.append(f'{label}: human review of the category/attachment is still pending.')
    if pages > 200:
        blockers.append('More than 200 unique pages.')
    families = Counter(row['template_family'] for row in rows if row.get('template_family'))
    if len(families) < 10 or any(count > 4 for count in families.values()):
        blockers.append('Require at least ten template families, at most four originals each.')
    for field, minimum in (('scan', 8), ('ambiguous', 8), ('attachment', 6)):
        if sum(row.get(field) == 'yes' for row in rows) < minimum:
            blockers.append(f'Require at least {minimum} inspected originals with {field}=yes.')
    return blockers


if __name__ == '__main__':
    findings = check_intake()
    print(json.dumps({'intake_ready': not findings, 'blockers': findings,
                      'remote_calls': 0,
                      'note': 'Intake readiness is not packet verification or authorization for inference.'}, indent=2))
    raise SystemExit(1 if findings else 0)
