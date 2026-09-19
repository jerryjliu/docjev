"""Rebuild/verify the authentic demo packet without downloading or modifying originals."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    provenance = json.loads((HERE / 'SOURCE.json').read_text())
    manifest = json.loads((HERE / 'demo-manifest.json').read_text())
    for source in provenance['sources']:
        path = ROOT / source['path']
        assert sha(path) == source['sha256'], f'Changed original: {path}'
        assert len(PdfReader(path).pages) == source['page_count']
    packet = manifest['split'][0]
    path = ROOT / packet['path']
    if not args.verify:
        writer = PdfWriter()
        for source_id in packet['source_ids']:
            source = next(s for s in provenance['sources'] if s['id'] == source_id)
            writer.append(ROOT / source['path'])
        writer.add_metadata({'/Title': 'Assembled public-finance demo packet', '/Subject': 'Complete unmodified source pages; see SOURCE.json. Independently assembled demonstration, not an official government packet.'})
        with path.open('wb') as stream:
            writer.write(stream)
        packet['sha256'] = sha(path)
        (HERE / 'demo-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    assert sha(path) == packet['sha256'], 'Changed assembled packet'
    reader = PdfReader(path)
    assert len(reader.pages) == packet['page_count'] == 15
    assert [p for s in packet['segments'] for p in s['pages']] == list(range(1, 16))
    offset = 0
    for source_id in packet['source_ids']:
        source = next(s for s in provenance['sources'] if s['id'] == source_id)
        original = PdfReader(ROOT / source['path'])
        for page in original.pages:
            output = reader.pages[offset]
            assert page.get_contents().get_data() == output.get_contents().get_data()
            assert page.mediabox == output.mediabox
            offset += 1
    print('Verified 5 original PDFs and all 15 unmodified assembled page content streams.')


if __name__ == '__main__':
    main()
