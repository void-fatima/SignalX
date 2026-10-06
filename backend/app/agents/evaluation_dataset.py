"""Private evaluation schemas, label isolation and conversation-held-out validation."""
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.contracts import AgentInput, Decision, ProductSnapshot
from app.agents.orchestrator import _prepare_input
from app.agents.screening import normalize

DATA_DIRECTORY = Path(__file__).with_name("eval_data")


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class EvaluationCase(EvaluationModel):
    case_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    language: Literal["en", "fa"]
    category: str = Field(min_length=1)
    source: Literal["synthetic", "observed_dev_reference"] = "synthetic"
    agent_input: AgentInput
    # Public ProductInput has no best_fit/not_fit fields. Extended legacy profile
    # probes are explicit and are never silently injected into recorded real input.
    legacy_profile: ProductSnapshot | None = None

    @model_validator(mode="after")
    def consistent_profile(self):
        if self.legacy_profile is not None:
            product = self.agent_input.product
            if any(getattr(product, name) != getattr(self.legacy_profile, name)
                   for name in ("name", "description", "target_customer")):
                raise ValueError("Legacy profile must match the public product fields")
        return self


class EvaluationLabel(EvaluationModel):
    case_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    split: Literal["dev", "test"]
    relevant: bool = Field(strict=True)
    acceptable_decisions: list[Decision] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    certainty: Literal["clear", "policy_sensitive"]
    authoring: Literal["assistant_authored_provisional"]


class DatasetManifest(EvaluationModel):
    dataset_version: str
    label_policy_version: str
    source: Literal["authored_examples_with_observed_dev_reference"]
    test_policy: Literal["conversation_holdout_no_threshold_tuning"]
    case_count: int = Field(ge=1)
    dev_count: int = Field(ge=1)
    test_count: int = Field(ge=1)
    cases_sha256: str
    labels_sha256: str


def input_digest(inputs: AgentInput) -> str:
    # Run ID/provider mode are execution metadata, not input identity. Include
    # product, source IDs, conversation, authors, timestamps and selected context.
    encoded = json.dumps(inputs.model_dump(mode="json", exclude={"metadata"}),
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_dataset(cases: list[EvaluationCase], labels: list[EvaluationLabel]) -> None:
    by_case = {case.case_id: case for case in cases}
    by_label = {label.case_id: label for label in labels}
    if len(by_case) != len(cases) or len(by_label) != len(labels):
        raise ValueError("Duplicate evaluation case/label IDs")
    if by_case.keys() != by_label.keys():
        raise ValueError("Every case needs exactly one label")
    group_splits, conversation_splits, sources, digests, contents = {}, {}, {}, set(), set()
    for case in cases:
        label = by_label[case.case_id]
        inputs, _, target, context = _prepare_input(case.agent_input)
        if case.source == "observed_dev_reference" and label.split != "dev":
            raise ValueError("Known development observations cannot enter the independent test split")
        if label.conversation_id != target.conversation_id or label.group_id != case.group_id:
            raise ValueError("Label/input conversation or family group mismatch")
        if len(set(label.acceptable_decisions)) != len(label.acceptable_decisions):
            raise ValueError("Duplicate acceptable decisions")
        for mapping, key in ((group_splits, case.group_id), (conversation_splits, target.conversation_id)):
            if key in mapping and mapping[key] != label.split:
                raise ValueError("Development and test conversations/family groups overlap")
            mapping[key] = label.split
        digest = input_digest(inputs)
        if digest in digests:
            raise ValueError("Duplicate evaluation inputs")
        digests.add(digest)
        content = (inputs.product.name, inputs.product.description, inputs.product.target_customer,
                   normalize(target.content), tuple(normalize(m.content) for m in context))
        if content in contents:
            raise ValueError("Duplicate source content, even under different message/conversation IDs")
        contents.add(content)
        for message in [target, *context]:
            identity = (message.conversation_id, message.content, message.author, message.timestamp)
            if message.id in sources and sources[message.id] != identity:
                raise ValueError("Source ID reused across conversations or with conflicting text")
            sources[message.id] = identity
            if message.timestamp > target.timestamp:
                raise ValueError("Evaluation uses only context available at target time")


def load_dataset(directory: Path = DATA_DIRECTORY) -> tuple[DatasetManifest, list[EvaluationCase], list[EvaluationLabel]]:
    manifest = DatasetManifest.model_validate_json((directory / "manifest.json").read_text(encoding="utf-8"))
    bodies = [(directory / name).read_bytes() for name in ("cases.json", "labels.json")]
    # Git may check text out as CRLF on Windows. Freeze content with canonical
    # LF endings, so platform-only newline conversion does not invalidate labels.
    if [hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest() for body in bodies] != [manifest.cases_sha256, manifest.labels_sha256]:
        raise ValueError("Dataset checksum mismatch; version and freeze labels before evaluation")
    cases = [EvaluationCase.model_validate(row) for row in json.loads(bodies[0])]
    labels = [EvaluationLabel.model_validate(row) for row in json.loads(bodies[1])]
    validate_dataset(cases, labels)
    if (len(cases) != manifest.case_count or sum(l.split == "dev" for l in labels) != manifest.dev_count
            or sum(l.split == "test" for l in labels) != manifest.test_count):
        raise ValueError("Dataset manifest counts do not match")
    return manifest, cases, labels
