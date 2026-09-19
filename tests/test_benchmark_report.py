"""Regenerate complete and interrupted study reports entirely from local records."""

import json

import pytest

from benchmarks.report import write_report


@pytest.fixture
def study(tmp_path):
    labels = ['tax_form', 'financial_report', 'press_release', 'legal_notice', 'other']
    originals = [{'id': f'e{i:03}', 'split': 'test', 'category': labels[i // 8], 'page_count': 1,
                  'source_ids': [f'e{i:03}']} for i in range(40)]
    packets = [{'id': f'p{i:03}', 'split': 'test', 'page_count': 5,
                'source_ids': [x['id'] for x in originals[i*5:(i+1)*5]],
                'segments': [{'category': x['category'], 'pages': [j+1]}
                             for j, x in enumerate(originals[i*5:(i+1)*5])]} for i in range(8)]
    data = {'classify': originals, 'split': packets}
    plan, rows = [], []
    for task, items in data.items():
        dev = {**items[0], 'id': f'dev-{task}', 'split': 'dev'}
        items.append(dev)
        for engine in ('jev', 'openai'):
            for item in items:
                phase = 'warmup' if item['split'] == 'dev' else 'measured'
                planned = {'observation_id': f'{task}-{engine}-{item["id"]}', 'source_id': item['id'],
                           'task': task, 'engine': engine, 'model': engine, 'scope': 'decision', 'concurrency': 1,
                           'phase': phase, 'repeat': -1 if phase == 'warmup' else 0}
                plan.append(planned)
                result = {'metrics': {'decision_ms': 8}}
                if task == 'classify':
                    result['category'] = item['category']
                else:
                    result['segments'] = item['segments']
                rows.append({**planned, 'status': 'ok', 'dispatched': True, 'wall_ms': 9,
                             'result': result, 'requests': [{'task': task, 'cost_usd': .001, 'input_tokens': 10}]})
    manifest = {'run_id': 'fixture-real-accuracy', 'started_at': '2026-09-19T00:00:00Z', 'status': 'complete',
                'demo_set': 'real', 'experiment_kind': 'real-document-accuracy-pilot',
                'config': {'scope': 'decision', 'ocr': 'liteparse', 'warmups': 1, 'repeats': 1,
                           'concurrency': 1, 'budget_usd': 2}, 'datasets': data, 'execution_plan': plan,
                'preparation_receipt': {'items': {'e000': {'status': 'ok', 'wall_ms': 120,
                                                         'preparation_metrics': {'ocr_cost_usd': 0, 'ocr_ms': 110}}}},
                'pricing_snapshot': {'date': '2026-09-18', 'currency': 'USD'}, 'budget': {}}
    def save(observations=None, events=None):
        (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
        (tmp_path / 'raw.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in (rows if observations is None else observations)))
        (tmp_path / 'events.jsonl').write_text(''.join(json.dumps(event)+'\n' for event in (events or [])))
        return write_report(tmp_path)
    return tmp_path, manifest, rows, save


def test_real_study_report_counts_and_accounting_are_reproducible(study, monkeypatch):
    path, _, _, save = study
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    summary = save()
    before = {name: (path / name).read_bytes() for name in ('summary.json', 'metrics.csv', 'report.md', 'latency.svg')}
    assert write_report(path) == summary
    assert all((path / name).read_bytes() == content for name, content in before.items())
    assert summary['run_status'] == 'complete'
    assert summary['components']['warmup']['planned_calls'] == 4
    assert summary['components']['warmup']['dispatched_calls'] == 4
    assert summary['components']['measured']['dispatched_calls'] == 96
    assert summary['components']['warmup']['decision_cost_usd_known'] == pytest.approx(.004)
    assert summary['accounting']['full_run_cost_usd_known'] == pytest.approx(.100)
    report = (path / 'report.md').read_text()
    assert '40/40 correct' in report and '8/8 exact' in report
    assert 'actual 0' not in report
    assert 'Actual warmup invocations dispatched: 4' in report
    assert 'human review was not performed' in report
    assert '40 unique sources and 48 task inputs' in report
    assert '12.5 points' in report and '2.5 percentage points' in report
    assert '2026-09-18' in report
    assert 'not measured (one pass)' in report
    assert 'bootstrap' not in report.lower()
    assert 'synthetic' not in report.lower()
    for group in summary['groups']:
        assert group['repeat_disagreement_documents'] is None
        assert group.get('accuracy_95pct_bootstrap', group.get('packet_exact_match_95pct_bootstrap')) is None


def test_empty_raw_report_retains_all_denominators_and_na_chart(study):
    path, manifest, _, save = study
    manifest['status'] = 'blocked'
    manifest['stop_reason'] = {'code': 'budget_admission', 'message': 'Estimate exceeds local guard'}
    summary = save([])
    assert len(summary['groups']) == 4
    assert summary['missing_terminal_calls'] == 100
    assert summary['run_status'] == 'blocked'
    assert summary['components']['warmup']['dispatched_calls'] == 0
    report = (path / 'report.md').read_text()
    assert '0/40 correct' in report and '0/8 exact' in report
    assert 'budget_admission' in report
    svg = (path / 'latency.svg').read_text()
    assert svg.count('n/a / n/a') == 4
    assert '0.0 / 0.0' not in svg


def test_unclosed_warmup_is_unknown_and_cannot_look_complete(study):
    path, manifest, rows, save = study
    warmup = next(row for row in rows if row['phase'] == 'warmup')
    event = {'event': 'dispatch_started', 'observation_id': warmup['observation_id'], 'reserved_cost_usd': .1}
    manifest['status'] = 'running'
    summary = save([], [event])
    assert summary['run_status'] == 'incomplete'
    assert summary['unclosed_dispatches'] == 1
    assert summary['components']['warmup']['dispatched_calls'] == 1
    assert summary['components']['warmup']['request_count_complete'] is False
    assert summary['components']['warmup']['unknown_cost_calls'] == 1
    assert summary['accounting']['known_cost_is_lower_bound']
    assert 'lower bound' in (path / 'report.md').read_text()


def test_hard_kill_truncated_final_write_preserves_earlier_result(study):
    path, _, rows, save = study
    save(rows[:1])
    with (path / 'raw.jsonl').open('a') as stream:
        stream.write('{"observation_id":')
    summary = write_report(path)
    assert summary['run_status'] == 'incomplete'
    assert summary['truncated_final_records']['raw']
    assert summary['groups'][0]['correct_count'] == 1
    assert summary['groups'][0]['planned_unique'] == 40


def test_interior_corrupt_record_is_not_silently_dropped(study):
    path, _, rows, save = study
    save([])
    (path / 'raw.jsonl').write_text('{bad\n'+json.dumps(rows[0])+'\n')
    with pytest.raises(ValueError, match='interior JSONL'):
        write_report(path)


def test_legacy_demo_still_reports_source_matches_and_unique_bootstrap(study):
    path, manifest, rows, save = study
    manifest.pop('execution_plan')
    manifest['experiment_kind'] = 'demonstration'
    manifest['datasets'] = {'classify': manifest['datasets']['classify'][:1]}
    summary = save(rows[:1])
    assert summary['groups'][0]['accuracy_95pct_bootstrap'] is None
    report = (path / 'report.md').read_text()
    assert '# Real-document timing pilot' in report
    assert '1/1 source matches' in report
    assert 'not estimable with fewer than two unique sources' in report


def test_start_cannot_be_erased_by_non_dispatched_placeholder(study):
    _, manifest, rows, save = study
    row = {**rows[0], 'status': 'skipped', 'dispatched': False, 'requests': [], 'result': {},
           'skip_reason': 'evidence_write_failure'}
    event = {'event': 'dispatch_started', 'observation_id': row['observation_id'], 'reserved_cost_usd': .2}
    manifest['status'] = 'stopped'
    summary = save([row], [event])
    assert summary['unclosed_dispatches'] == 1
    assert summary['components']['measured']['unknown_cost_calls'] == 1
    assert summary['components']['measured']['dispatched_calls'] == 1
    assert summary['components']['measured']['unclosed_dispatch_reservations_usd'] == .2
    assert summary['accounting']['known_cost_is_lower_bound']


def test_preparation_copy_is_used_when_manifest_has_no_embedded_receipt(study):
    path, manifest, _, save = study
    receipt = manifest.pop('preparation_receipt')
    (path / 'preparation.json').write_text(json.dumps(receipt))
    summary = save([])
    assert summary['components']['preparation']['items'] == 1
    assert summary['components']['preparation']['ocr_ms_known'] == 110


def test_all_failed_group_has_no_success_latency(study):
    path, manifest, rows, save = study
    manifest['status'] = 'stopped'
    failed = [{**row, 'status': 'error', 'result': {}, 'requests': [], 'usage_unknown': True,
               'request_count_complete': False, 'error': {'type': 'TimeoutError'}}
              for row in rows if row['task'] == 'split' and row['engine'] == 'jev' and row['phase'] == 'measured']
    summary = save(failed)
    group = next(x for x in summary['groups'] if x['task'] == 'split' and x['engine'] == 'jev')
    assert group['failed_calls'] == 8
    assert group['exact_packets'] == 0
    assert group['unknown_cost_calls'] == 8
    assert group['decision_p50_ms'] is None
    assert 'n/a / n/a' in (path / 'latency.svg').read_text()


def test_csv_exports_flattened_quality_metrics(study):
    import csv

    path, _, _, save = study
    summary = save()
    with (path / 'metrics.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert float(rows[0]['macro_f1']) == 1
    row = next(row for row in rows if row['task'] == 'split' and row['engine'] == 'jev')
    group = next(group for group in summary['groups'] if group['task'] == 'split' and group['engine'] == 'jev')
    for metric in ('boundary', 'segment'):
        for name in ('precision', 'recall', 'f1', 'true_positive', 'predicted', 'actual'):
            assert float(row[f'{metric}_{name}']) == group[metric][name]
    assert float(row['coverage_validity']) == 1
    assert int(row['same_category_boundaries_actual']) == group['same_category_boundaries_actual']
