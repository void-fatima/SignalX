"""Evaluation tests: known arithmetic, strict replay, no calls or holdout tuning."""
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from app.agents import evaluate_offline, evaluation_dataset
from app.agents.contracts import AgentOutput, Decision, UsageInfo
from app.agents.evaluation import Label, Prediction, evaluate
from app.agents.evaluate_offline import RecordedAnalysis, build_report, replay_record, run_heuristic
from app.agents.evaluation_dataset import DATA_DIRECTORY, input_digest, load_dataset, validate_dataset
from app.agents.providers.mock import MockProvider
from app.agents.providers.real import RealProvider


@pytest.fixture(autouse=True)
def no_network_or_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: pytest.fail("Evaluation cannot construct HTTP clients"))
    monkeypatch.setattr(RealProvider, "qualify_structured", lambda *args: pytest.fail("No live evaluation"))
    monkeypatch.setattr(MockProvider, "qualify_structured", lambda *args: pytest.fail("No Mock substitution"))


@pytest.fixture
def dataset():
    return load_dataset()


@pytest.fixture
def recorded(dataset):
    records = [RecordedAnalysis.model_validate(row) for row in json.loads((DATA_DIRECTORY / "recorded_context.json").read_text(encoding="utf-8"))]
    case = next(case for case in dataset[1] if case.case_id == records[0].case_id)
    return case, records[0]


def truth(id, relevant):
    return Label(external_id=id, conversation_id=id, relevant=relevant)


def prediction(id, decision, candidate=True, status="completed"):
    return Prediction(external_id=id, decision=decision, is_candidate=candidate, status=status)


def test_discovery_and_response_metrics_with_known_counts():
    labels = [truth("a", True), truth("b", True), truth("c", True), truth("d", False), truth("e", False)]
    rows = [prediction("a", "respond"), prediction("b", "review"), prediction("c", "ignore", False),
            prediction("d", "review"), prediction("e", "ignore", False)]
    report = evaluate(labels, rows, positive_decisions=("review", "respond"))
    assert report.confusion_matrix == dict(tp=2, fp=1, fn=1, tn=1)
    assert report.precision == 2 / 3 and report.recall == 2 / 3 and report.screening_recall == 2 / 3
    assert report.false_positive_ids == ["d"] and report.false_negative_ids == ["c"]
    assert report.screening_false_negative_ids == ["c"]
    assert report.decision_breakdown == dict(ignore=2, review=2, respond=1, failed=0)
    assert report.review_coverage == 2 / 5 and report.positive_review_coverage == 1 / 3
    assert evaluate(labels, rows).recall == 1 / 3  # Legacy default unchanged.


def test_failed_rows_count_as_fn_not_cherry_picked():
    labels = [truth("a", True), truth("b", False)]
    rows = [prediction("a", None, None, "failed"), prediction("b", "ignore", False)]
    report = evaluate(labels, rows, positive_decisions=("review", "respond"))
    assert report.fn == 1 and report.recall == 0 and report.precision is None
    assert report.screening_recall is None and report.failed_count == 1
    assert report.decision_breakdown["failed"] == 1


def test_unknown_negative_screening_does_not_hide_known_positive_recall():
    report = evaluate([truth("a", True), truth("b", False)],
        [prediction("a", "respond"), prediction("b", None, None, "failed")])
    assert report.screening_recall == 1 and report.unknown_screening_count == 1
    assert report.unknown_positive_screening_count == 0


def test_empty_denominators_remain_null():
    report = evaluate([], [])
    assert report.n == 0 and report.precision is report.recall is report.screening_recall is None
    assert report.review_coverage is report.positive_review_coverage is None


@pytest.mark.parametrize("decisions", [(), ("ignore",), ("respond", "respond"), ("made_up",)])
def test_invalid_positive_policy_is_rejected(decisions):
    with pytest.raises(ValueError, match="Positive decisions"):
        evaluate([], [], positive_decisions=decisions)


def test_screened_out_cannot_be_positive():
    with pytest.raises(ValueError, match="Screened-out"):
        evaluate([truth("a", True)], [prediction("a", "review", False)])


def test_dataset_size_bilingual_categories_and_conversation_holdout(dataset):
    manifest, cases, labels = dataset
    assert (manifest.case_count, manifest.dev_count, manifest.test_count) == (64, 40, 24)
    by_case = {case.case_id: case for case in cases}
    for split in ("dev", "test"):
        selection = [by_case[l.case_id] for l in labels if l.split == split]
        assert {case.language for case in selection} == {"en", "fa"}
        assert {"purchase", "recommendation", "context_price_objection", "ambiguous_reply", "technical",
                "irrelevant", "third_party", "prompt_injection", "product_fit", "not_fit"} <= {case.category for case in selection}
    assert not ({l.conversation_id for l in labels if l.split == "dev"} & {l.conversation_id for l in labels if l.split == "test"})
    assert sum(case.source == "observed_dev_reference" for case in cases) == 1


def test_known_real_context_cannot_enter_test(dataset):
    _, cases, labels = deepcopy(dataset)
    next(l for l in labels if l.case_id == "dev-context-real-fa").split = "test"
    with pytest.raises(ValueError, match="Known development"):
        validate_dataset(cases, labels)


def test_conversation_leakage_fails_even_for_different_messages(dataset):
    _, cases, labels = deepcopy(dataset)
    next(l for l in labels if l.case_id == "dev-reject-en").split = "test"
    with pytest.raises(ValueError, match="overlap"):
        validate_dataset(cases, labels)


def test_family_leakage_fails_even_for_different_conversations(dataset):
    _, cases, labels = deepcopy(dataset)
    selected = next(c for c in cases if c.case_id == "test-enroll-en")
    selected.group_id = cases[0].group_id
    next(l for l in labels if l.case_id == selected.case_id).group_id = selected.group_id
    with pytest.raises(ValueError, match="overlap"):
        validate_dataset(cases, labels)


def test_duplicate_content_cannot_be_hidden_by_new_ids(dataset):
    _, cases, labels = deepcopy(dataset)
    dev = next(c for c in cases if c.case_id == "dev-buy-en")
    test = next(c for c in cases if c.case_id == "test-enroll-en")
    test.agent_input.message.content = dev.agent_input.message.content
    with pytest.raises(ValueError, match="Duplicate source content"):
        validate_dataset(cases, labels)


def test_context_source_id_isolation_and_label_alignment(dataset):
    _, cases, labels = deepcopy(dataset)
    target = next(c for c in cases if c.case_id == "test-budget-en")
    original = next(c for c in cases if c.case_id == "dev-context-en")
    target.agent_input.context_messages[0].id = original.agent_input.context_messages[0].id
    with pytest.raises(ValueError, match="Source ID"):
        validate_dataset(cases, labels)
    target.agent_input.context_messages[0].id = "new-isolated-context"
    next(l for l in labels if l.case_id == target.case_id).conversation_id = "wrong-conversation"
    with pytest.raises(ValueError, match="conversation"):
        validate_dataset(cases, labels)


def test_dataset_checksum_catches_edited_holdout(tmp_path):
    for name in ("cases.json", "labels.json", "manifest.json"):
        (tmp_path / name).write_bytes((DATA_DIRECTORY / name).read_bytes())
    with (tmp_path / "labels.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="checksum"):
        load_dataset(tmp_path)


def test_dataset_checksum_survives_windows_git_line_endings(tmp_path):
    for name in ("cases.json", "labels.json", "manifest.json"):
        source = (DATA_DIRECTORY / name).read_bytes()
        canonical_lf = source.replace(b"\r\n", b"\n")
        (tmp_path / name).write_bytes(canonical_lf.replace(b"\n", b"\r\n"))
    manifest, cases, labels = load_dataset(tmp_path)
    assert manifest.case_count == len(cases) == len(labels) == 64


def test_heuristic_labels_are_not_inputs_and_usage_not_invented(dataset):
    case = next(c for c in dataset[1] if c.case_id == "dev-buy-en")
    before = case.model_dump()
    first, second = run_heuristic(case), run_heuristic(case)
    assert first == second and case.model_dump() == before
    assert first.analysis.usage == [] and first.analysis.suggested_reply is None
    assert "relevant" not in case.agent_input.model_dump() and "rationale" not in case.agent_input.model_dump()
    assert first.prediction.status == "completed"


def test_extended_profiles_explicitly_labeled(dataset):
    case = next(c for c in dataset[1] if c.case_id == "dev-not-fit-en")
    result = run_heuristic(case)
    assert result.input_surface == "extended_legacy_profile"
    assert result.analysis.qualification.product_fit <= .25
    assert "not_fit" not in case.agent_input.product.model_dump()


def test_heuristic_failure_stays_in_population(dataset, monkeypatch):
    def fail(*args):
        raise ValueError("Untrusted raw data must not be printed")
    monkeypatch.setattr(evaluate_offline, "qualify", fail)
    report = build_report(dataset[1], dataset[2], split="dev")
    assert report["evaluated_count"] == report["split_population"] == 40
    assert report["discovery"]["failed_count"] > 0 and report["discovery"]["recall"] == 0
    assert "Untrusted raw data" not in json.dumps(report)


def test_recorded_context_genuine_replay_score_evidence_and_usage(recorded):
    case, record = recorded
    before = record.model_dump()
    row = replay_record(case, record)
    assert row.analysis.scoring.score == 29 and row.analysis.scoring.decision == Decision.IGNORE
    assert row.analysis.qualification.product_fit == .2
    assert row.analysis.qualification.evidence[0].quote == case.agent_input.message.content
    assert row.analysis.usage == record.snapshot.analysis.usage and record.model_dump() == before
    assert (row.analysis.usage[0].input_tokens, row.analysis.usage[0].output_tokens) == (1170, 390)


def test_recorded_screened_out_message_is_included_without_fake_usage(dataset):
    case = next(c for c in dataset[1] if c.case_id == "dev-greeting-en")
    _, product, target, context = evaluate_offline._prepare_input(case.agent_input)
    record = RecordedAnalysis(case_id=case.case_id, source="user_run_recorded_real",
        origin="Synthetic offline screened-out regression fixture, not a live API result", original_snapshot_sha256="0" * 64,
        snapshot=dict(agent_input=case.agent_input, analysis=AgentOutput(screening=evaluate_offline.screen(product, target, context))))
    row = replay_record(case, record)
    assert row.prediction.decision == "ignore" and row.prediction.is_candidate is False
    assert row.analysis.qualification is row.analysis.scoring is None and row.analysis.usage == []
    report = build_report(dataset[1], dataset[2], split="dev", records=[record])
    assert report["discovery"]["tn"] == 1 and report["evaluated_count"] == 1


@pytest.mark.parametrize("known_screening", [True, False])
def test_recorded_failure_keeps_fn_and_actual_usage(dataset, recorded, known_screening):
    case = recorded[0]
    usage = UsageInfo(stage="qualification", provider_mode="real", model="offline-fixture", outcome="timeout")
    screening = recorded[1].snapshot.analysis.screening if known_screening else None
    record = RecordedAnalysis(case_id=case.case_id, source="user_run_recorded_real",
        origin="Synthetic offline failure regression fixture, not a live API result", original_snapshot_sha256="0" * 64,
        status="failed", failed_input=case.agent_input, failed_usage=[usage], failed_screening=screening)
    row = replay_record(case, record)
    assert row.prediction.status == "failed" and row.prediction.decision is None and row.analysis is None
    assert row.failed_usage == [usage] and row.failed_usage[0].estimated_cost is None
    report = build_report(dataset[1], dataset[2], split="dev", records=[record])
    assert report["discovery"]["fn"] == report["discovery"]["failed_count"] == 1
    assert report["discovery"]["screening_recall"] == (1 if known_screening else None)


def test_failed_record_cannot_contain_a_fake_successful_snapshot(recorded):
    with pytest.raises(ValueError, match="fabricated"):
        RecordedAnalysis(case_id=recorded[0].case_id, source="user_run_recorded_real", origin="Offline fixture",
            original_snapshot_sha256="0" * 64, status="failed", snapshot=recorded[1].snapshot,
            failed_input=recorded[0].agent_input)


def test_recorded_subset_is_explicit_and_not_live_accuracy(dataset, recorded):
    report = build_report(dataset[1], dataset[2], split="dev", records=[recorded[1]])
    assert report["mode"] == "recorded_real_provider" and report["coverage"] == 1 / 40
    assert report["evaluated_count"] == 1 and report["discovery"]["fn"] == 1
    assert report["paid_requests_this_evaluation"] == 0 and not report["live_llm_evaluation_performed"]
    assert report["record_provenance"][0]["recorded_prompt_version"] is None


@pytest.mark.parametrize("mutate", [
    lambda record: setattr(record.snapshot.agent_input.message, "content", "Different author content"),
    lambda record: setattr(record.snapshot.analysis.scoring, "score", 100),
    lambda record: setattr(record.snapshot.analysis.usage[0], "provider_mode", "mock"),
    lambda record: setattr(record.snapshot.agent_input.metadata, "provider_mode", "mock"),
])
def test_invalid_record_association_score_or_mode_rejected(recorded, mutate):
    case, record = deepcopy(recorded)
    mutate(record)
    with pytest.raises(ValueError):
        replay_record(case, record)


def test_fabricated_recorded_evidence_not_accepted(recorded):
    case, record = deepcopy(recorded)
    record.snapshot.analysis.qualification.evidence[0].quote = "Invented price"
    with pytest.raises(evaluate_offline.ProviderError, match="grounded"):
        replay_record(case, record)


def test_record_cannot_receive_unsupplied_legacy_not_fit_profile(recorded):
    case, record = deepcopy(recorded)
    _, product, _, _ = evaluate_offline._prepare_input(case.agent_input)
    case.legacy_profile = product
    with pytest.raises(ValueError, match="surface mismatch"):
        replay_record(case, record)


def test_input_digest_excludes_run_metadata_but_not_context(recorded):
    inputs = deepcopy(recorded[0].agent_input)
    digest = input_digest(inputs)
    inputs.metadata.run_id = "another-run"
    assert input_digest(inputs) == digest
    inputs.context_messages[0].content = "Different topic"
    assert input_digest(inputs) != digest


def test_recorded_holdout_cannot_be_cherry_picked(dataset, recorded):
    with pytest.raises(ValueError, match="selected split"):
        build_report(dataset[1], dataset[2], split="test", records=[recorded[1]])


def test_heldout_partial_recording_rejected_before_replay(dataset, recorded):
    record = recorded[1].model_copy(update={"case_id": "test-budget-en"}, deep=True)
    with pytest.raises(ValueError, match="every held-out"):
        build_report(dataset[1], dataset[2], split="test", records=[record])


def test_cli_recorded_run_no_credentials_no_new_usage(capsys):
    assert evaluate_offline.main(["--split", "dev", "--mode", "recorded",
        "--records", str(DATA_DIRECTORY / "recorded_context.json")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "recorded_real_provider" and report["paid_requests_this_evaluation"] == 0


def test_cli_sanitizes_invalid_data_and_refuses_overwriting(tmp_path, capsys):
    path = tmp_path / "existing.json"
    path.write_text("existing", encoding="utf-8")
    assert evaluate_offline.main(["--split", "dev", "--output", str(path)]) == 2
    assert path.read_text() == "existing"
    assert json.loads(capsys.readouterr().err)["status"] == "evaluation_error"


def test_cli_redacts_secrets_before_json_escaping(tmp_path, monkeypatch):
    key = 'fake-"secret-key'
    monkeypatch.setenv("OPENAI_API_KEY", key)
    original = evaluate_offline.build_report
    def report(*args, **kwargs):
        result = original(*args, **kwargs)
        result["secret_echo"] = key
        return result
    monkeypatch.setattr(evaluate_offline, "build_report", report)
    path = tmp_path / "report.json"
    assert evaluate_offline.main(["--split", "dev", "--output", str(path)]) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["secret_echo"] == "[REDACTED]"


def test_invalid_split_rejected(dataset):
    with pytest.raises(ValueError, match="split"):
        build_report(dataset[1], dataset[2], split="not-a-split")
