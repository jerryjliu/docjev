"""Hand-computed task metrics, especially same-category boundaries and failures."""

import pytest

from benchmarks.metrics import (
    bootstrap_mean,
    label_metrics,
    percentile,
    prf,
    split_metrics,
    summarize,
)


def segment(category, *pages):
    return {"category": category, "pages": list(pages)}


def test_classification_failures_are_in_denominator_and_recall():
    metrics = label_metrics(["invoice", "invoice", "contract", "contract"],
                            ["invoice", "contract", "contract", None], ["invoice", "contract"])
    assert metrics["accuracy"] == 0.5
    assert metrics["per_class"]["invoice"]["recall"] == 0.5
    assert metrics["per_class"]["invoice"]["precision"] == 1
    assert metrics["confusion_matrix"]["contract"]["__missing__"] == 1
    assert metrics["macro_f1"] == pytest.approx((2 / 3 + 0.5) / 2)


def test_same_category_boundary_is_a_real_document_boundary():
    truth = [[segment("invoice", 1, 2), segment("invoice", 3, 4), segment("letter", 5)]]
    prediction = [[segment("invoice", 1, 2, 3, 4), segment("letter", 5)]]
    result = split_metrics(truth, prediction, [5])
    assert result["page_accuracy"] == 1
    assert result["packet_exact_match"] == 0
    assert result["boundary"]["precision"] == 1
    assert result["boundary"]["recall"] == 0.5
    assert result["boundary"]["f1"] == pytest.approx(2 / 3)
    assert result["segment"]["f1"] == pytest.approx(2 / 5)
    assert result["same_category_boundary_recall"] == 0


def test_failed_packet_loses_all_pages_segments_and_boundaries():
    truth = [[segment("invoice", 1), segment("letter", 2)]]
    result = split_metrics(truth, [None], [2])
    assert result["page_accuracy"] == 0
    assert result["packet_exact_match"] == 0
    assert result["coverage_validity"] == 0
    assert result["boundary"]["recall"] == 0
    assert result["segment"]["recall"] == 0


def test_invalid_coverage_is_not_accepted_as_a_good_split():
    truth = [[segment("invoice", 1, 2)]]
    result = split_metrics(truth, [[segment("invoice", 1), segment("invoice", 1)]], [2])
    assert result["page_accuracy"] == 0
    assert result["coverage_validity"] == 0


def test_no_boundary_conventions_are_explicit():
    result = split_metrics([[segment("invoice", 1, 2)]], [[segment("invoice", 1, 2)]], [2])
    assert result["boundary"]["f1"] == 1
    assert result["same_category_boundary_recall"] is None
    assert prf(0, 0, 0)["precision"] == 1
    assert prf(0, 2, 0)["f1"] == 0
    assert percentile([], .95) is None
    assert percentile([10, 20], .95) == pytest.approx(19.5)
    assert bootstrap_mean([1.0]) is None


def test_summary_uses_first_pass_quality_and_all_successful_latencies():
    rows = []
    for repeat, category, timing in [(0, "invoice", 10), (1, "contract", 30)]:
        rows.append({"task": "classify", "id": "a", "engine": "jev", "model": "jev-1.13.0",
                     "scope": "decision", "concurrency": 1, "phase": "measured", "repeat": repeat,
                     "status": "ok", "wall_ms": timing, "requests": [],
                     "result": {"category": category, "needs_review": False,
                                "metrics": {"decision_ms": timing}}})
    # A not-yet-recorded source must still count against an interrupted report's denominator.
    data = {"classify": [{"id": "a", "split": "test", "category": "invoice"},
                         {"id": "b", "split": "test", "category": "contract"}]}
    result = summarize(rows, data)["groups"][0]
    assert result["accuracy"] == 0.5
    assert result["planned_unique"] == 2
    assert result["decision_p50_ms"] == 20
    assert result["latency_samples"] == 2
    assert result["repeat_disagreement_documents"] == 1


@pytest.mark.asyncio
async def test_budget_reserves_in_flight_and_retains_unknown_charges():
    from benchmarks.run import Budget

    budget = Budget(1)
    assert await budget.reserve(.7)
    assert not await budget.reserve(.4)
    await budget.settle(.7, [{"cost_usd": None}], dispatched=True)
    assert budget.unknown_reserved == .7
    assert not await budget.reserve(.4)
    assert await budget.reserve(.2)
    await budget.settle(.2, [{"cost_usd": .05}], dispatched=True)
    assert budget.known == .05
    assert budget.committed == pytest.approx(.75)


def frozen_study():
    categories = ['tax_form', 'financial_report', 'press_release', 'legal_notice', 'other']
    originals = [{'id': f'e{i:03}', 'split': 'test', 'category': categories[i % 5],
                  'page_count': 1, 'source_ids': [f'e{i:03}']} for i in range(40)]
    packets = [{'id': f'p{i:03}', 'split': 'test', 'page_count': 5,
                'source_ids': [item['id'] for item in originals[i*5:(i+1)*5]],
                'segments': [segment(item['category'], j+1) for j, item in enumerate(originals[i*5:(i+1)*5])]} for i in range(8)]
    data = {'classify': originals, 'split': packets}
    plan = []
    for task, items in data.items():
        for engine in ('jev', 'openai'):
            for item in items:
                plan.append({'observation_id': f'{task}-{engine}-{item["id"]}', 'source_id': item['id'],
                             'task': task, 'engine': engine, 'model': engine, 'scope': 'decision',
                             'concurrency': 1, 'phase': 'measured', 'repeat': 0})
    return data, plan


def terminal(planned, *, status='ok', **kwargs):
    return {**planned, 'status': status, 'dispatched': status != 'skipped',
            'wall_ms': 9, 'requests': [],
            'result': {'category': 'tax_form', 'metrics': {'decision_ms': 8}}, **kwargs}


def test_empty_log_still_scores_all_four_frozen_groups():
    data, plan = frozen_study()
    summary = summarize([], data, execution_plan=plan, experiment_kind='real-document-accuracy-pilot')
    assert len(summary['groups']) == 4
    assert summary['missing_terminal_calls'] == 96
    for group in summary['groups']:
        assert group['planned_unique'] == (40 if group['task'] == 'classify' else 8)
        assert group['completed_unique'] == group['successful_calls'] == 0
        assert group['decision_p50_ms'] is None
        assert group['latency_samples'] == 0
        assert group['repeat_disagreement_documents'] is None
        assert group['repeat_disagreement_status'] == 'not_measured'
        if group['task'] == 'classify':
            assert group['correct_count'] == 0
            assert group['accuracy'] == 0
        else:
            assert group['segment']['actual'] == 40
            assert group['boundary']['actual'] == 32
            assert group['packet_exact_match'] == 0


def test_partial_run_separates_timeout_skipped_missing_and_unclosed():
    data, plan = frozen_study()
    rows = [terminal(plan[0]), terminal(plan[1], status='error', result={}, requests=[{'cost_usd': .01, 'task': 'classify'}],
                                       usage_unknown=True, request_count_complete=False, error={'type': 'TimeoutError'}),
            terminal(plan[2], status='skipped', result={}, skip_reason='budget_stop')]
    starts = [{'event': 'dispatch_started', 'observation_id': plan[3]['observation_id'], 'reserved_cost_usd': .1}]
    summary = summarize(rows, data, execution_plan=plan, events=starts)
    group = summary['groups'][0]
    assert group['correct_count'] == 1
    assert group['accuracy'] == 1/40
    assert group['dispatched_calls'] == 3
    assert group['failed_calls'] == 1
    assert group['skipped_calls'] == 1
    assert group['missing_terminal_calls'] == 37
    assert group['unclosed_dispatches'] == 1
    assert group['unknown_cost_calls'] == 2
    assert group['decision_cost_usd_known'] == .01
    assert not group['request_count_complete']
    assert group['latency_samples'] == 1
    assert group['decision_p50_ms'] == 8
    assert group['skip_reasons'] == {'budget_stop': 1}


@pytest.mark.parametrize('change', ['duplicate', 'unknown_id', 'wrong_source', 'wrong_group'])
def test_frozen_plan_rejects_ambiguous_or_unexpected_terminals(change):
    data, plan = frozen_study()
    rows = [terminal(plan[0])]
    if change == 'duplicate':
        rows *= 2
    elif change == 'unknown_id':
        rows[0]['observation_id'] = 'unknown'
    elif change == 'wrong_source':
        rows[0]['source_id'] = 'unknown'
    else:
        rows[0]['model'] = 'wrong-model'
    with pytest.raises(ValueError):
        summarize(rows, data, execution_plan=plan)


def test_invalid_same_set_split_never_receives_interval_or_error_list_credit():
    data, plan = frozen_study()
    planned = [row for row in plan if row['task'] == 'split' and row['engine'] == 'jev']
    rows = []
    for row, truth in zip(planned, data['split'], strict=True):
        rows.append(terminal(row, result={'segments': truth['segments'] + truth['segments'], 'metrics': {'decision_ms': 10}}))
    group = next(group for group in summarize(rows, data, execution_plan=plan)['groups']
                 if group['task'] == 'split' and group['engine'] == 'jev')
    assert group['packet_exact_match'] == 0
    assert group['packet_exact_match_95pct_bootstrap'] == [0, 0]
    assert group['failed_calls'] == 8
    assert len(group['failures_or_incorrect_ids']) == 8
    assert group['decision_p50_ms'] is None


def test_later_success_cannot_rescue_first_pass_failure():
    data = {'classify': [{'id': 'a', 'split': 'test', 'category': 'tax_form'}]}
    base = {'observation_id': 'a0', 'source_id': 'a', 'task': 'classify', 'engine': 'jev', 'model': 'jev',
            'scope': 'decision', 'concurrency': 1, 'phase': 'measured', 'repeat': 0}
    plan = [base, {**base, 'observation_id': 'a1', 'repeat': 1}]
    rows = [terminal(plan[0], status='error', result={}), terminal(plan[1])]
    group = summarize(rows, data, execution_plan=plan)['groups'][0]
    assert group['accuracy'] == group['completed_unique'] == 0
    assert group['latency_samples'] == 1


def test_preparation_and_warmup_costs_are_counted_once_outside_measured_groups():
    data, plan = frozen_study()
    warmup = {**plan[0], 'observation_id': 'warmup', 'phase': 'warmup', 'repeat': -1}
    plan.append(warmup)
    rows = [terminal(plan[0], requests=[{'task': 'classify', 'cost_usd': .03}]),
            terminal(warmup, requests=[{'task': 'classify', 'cost_usd': .02}])]
    preparation = {'items': {
        'fresh': {'status': 'ok', 'parser': {'name': 'llamaparse'}, 'wall_ms': 120,
                  'preparation_metrics': {'ocr_ms': 100, 'conversion_ms': 10, 'ocr_cost_usd': .5,
                                          'requests': [{'task': 'ocr', 'cost_usd': .5}]}},
        'cached': {'status': 'ok', 'cache_hit': True, 'wall_ms': 3,
                   'preparation_metrics': {'ocr_cost_usd': .5}},
        'failed': {'status': 'error', 'wall_ms': 7, 'parser': {'name': 'llamaparse'},
                   'preparation_metrics': {'requests': [{'task': 'ocr', 'cost_usd': None}]}},
    }}
    summary = summarize(rows, data, execution_plan=plan, preparation=preparation)
    components = summary['components']
    assert components['measured']['decision_cost_usd_known'] == .03
    assert components['warmup']['decision_cost_usd_known'] == .02
    assert components['warmup']['dispatched_calls'] == 1
    assert components['preparation']['cost_usd_known'] == .5
    assert components['preparation']['unknown_cost_items'] == 1
    assert components['preparation']['wall_ms_known'] == 130
    assert components['preparation']['cache_hits'] == 1
