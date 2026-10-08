"""AvalAI acceptance adapted from Setayesh Samani's original commit 3a84276.

Explicit, sequential real-provider acceptance matrix. Import/--help are offline.

Labels are used only after analysis to compare rankings, never in provider input.
No replies, sending, production changes, price inference or provider fallback.
"""
import argparse
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from app.agents.acceptance import RequestPacer, usage_report
from app.agents.contracts import AgentInput, AgentOutput, MessageInput, ProductInput, Signals
from app.agents.orchestrator import _prepare_input, analyze_agent
from app.agents.providers.base import ProviderError
from app.agents.providers.config import RealProviderConfig
from app.agents.providers.factory import real_provider_client
from app.agents.prompts.qualification import PROMPT_VERSION as AVALAI_PROMPT_VERSION
from app.agents.qualification import validate_qualification_result
from app.agents.scoring import SCORING_VERSION, calculate_score_with_reason
from app.agents.screening import normalize
from app.agents.smoke_test import _print_report

CASES_FILE = Path(__file__).with_name("cross_business_cases.json")
REQUEST_BUDGET = 18
PROVIDER_PROMPT_VERSIONS = {"avalai": AVALAI_PROMPT_VERSION}
CHECKS = {
    "matrix": "Matrix IDs, labels or completed combinations are invalid or incomplete.",
    "configuration": "Set OPENAI_MODEL, OPENAI_API_KEY and OPENAI_BASE_URL=https://api.avalai.ir/v1. If LLM_PROVIDER is supplied it must be avalai.",
    "analysis_complete": "A target was screened out or qualification, scoring, evidence or usage is missing.",
    "provenance": "Real mode, selected provider's executed prompt, cost metadata or scoring version does not match.",
    "evidence_grounding": "Evidence does not reference an exact supplied message substring.",
    "scoring": "Score, decision or reason differs from the deterministic scorer.",
    "usage": "Qualification attempt stages, outcomes or request counts are inconsistent.",
    "unsupported_amount": "Qualification contains an unsupported numeric or monetary claim; inspect this run.",
    "foreign_profile_text": "Qualification contains another business's profile text absent from this run's sources.",
    "local_validation": "Local input/output validation failed; raw exception data is suppressed.",
}


class MatrixValidationError(ValueError):
    def __init__(self, check: str):
        self.failed_check = check
        super().__init__(CHECKS[check])


def load_cases() -> tuple[list[ProductInput], list[MessageInput], dict[str, str]]:
    fixture = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    products = [ProductInput.model_validate(item) for item in fixture["products"]]
    now = datetime.now(timezone.utc)
    messages = [MessageInput(id=item["id"], content=item["content"],
        author="acceptance-user", timestamp=now, conversation_id="cross-business-" + item["id"])
        for item in fixture["messages"]]
    expected = {item["id"]: item["expected_business_id"] for item in fixture["messages"]}
    return products, messages, expected


def build_matrix(products: list[ProductInput], messages: list[MessageInput]) -> list[AgentInput]:
    if (not products or not messages or len({p.id for p in products}) != len(products)
            or len({m.id for m in messages}) != len(messages)):
        raise MatrixValidationError("matrix")
    return [AgentInput(product=product.model_copy(deep=True), message=message.model_copy(deep=True),
        context_messages=[], metadata={"provider_mode": "real", "run_id": str(uuid4())})
        for product in products for message in messages]


def _claim_checks(inputs: AgentInput, output: AgentOutput, products: list[ProductInput]) -> None:
    # Check only natural-language claims, not the six numeric signals/usage.
    qualification = output.qualification
    claims = normalize(" ".join([qualification.intent, qualification.need,
        *qualification.limitations, *(e.reason for e in qualification.evidence)]))
    sources = normalize(" ".join([inputs.product.name, inputs.product.description,
        inputs.product.target_customer, inputs.message.content, *(m.content for m in inputs.context_messages)]))
    # A supplied headcount (12-person) is legitimate. A new numeric fact is not.
    def numeric_text(text: str) -> str:
        return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)
    numeric_claims, numeric_sources = numeric_text(claims), numeric_text(sources)
    numbers = r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)"
    if any(number not in re.findall(numbers, numeric_sources) for number in re.findall(numbers, numeric_claims)):
        raise MatrixValidationError("unsupported_amount")
    money = re.compile(r"(?:[$€£]\s*\d[\d.,]*|\d[\d.,]*\s*(?:usd|dollars?|euros?|toman|rial|تومان|ریال)\b|"
        r"\b(?:usd|dollars?|euros?|toman|rial|تومان|ریال)\s*\d[\d.,]*|"
        r"(?:price|cost|fee|charge|قیمت|هزینه)\s*(?:(?:is|around|about|approximately|حدوداً|حدودا|برابر)\s+|[:=]\s*)\d[\d.,]*)")
    if any(amount not in numeric_sources for amount in money.findall(numeric_claims)):
        raise MatrixValidationError("unsupported_amount")
    for product in products:
        if product.id == inputs.product.id:
            continue
        for field in (product.name, product.description, product.target_customer):
            text = normalize(field)
            phrase = r"(?<!\w)" + re.escape(text) + r"(?!\w)"
            if text and re.search(phrase, claims) and not re.search(phrase, sources):
                raise MatrixValidationError("foreign_profile_text")


def validate_run(inputs: AgentInput, output: AgentOutput, products: list[ProductInput],
                 request_count: int, *, provider: str = "avalai") -> dict[str, bool]:
    if provider not in PROVIDER_PROMPT_VERSIONS:
        raise MatrixValidationError("configuration")
    output = AgentOutput.model_validate(output.model_dump(), strict=True)
    if (not output.screening.is_candidate or output.qualification is None or output.scoring is None
            or not output.qualification.evidence or not output.usage
            or not output.qualification.intent.strip() or not output.qualification.need.strip()
            or output.suggested_reply is not None):
        raise MatrixValidationError("analysis_complete")
    if (inputs.metadata.provider_mode != "real" or output.prompt_version != PROVIDER_PROMPT_VERSIONS[provider]
            or output.scoring_version != SCORING_VERSION
            or any(u.provider_mode != "real" or u.cost_status == "mock" for u in output.usage)):
        raise MatrixValidationError("provenance")
    _, _, target, context = _prepare_input(inputs)
    try:
        qualification, grounded = validate_qualification_result(output.qualification, target, context, output.usage)
    except ProviderError:
        raise MatrixValidationError("evidence_grounding") from None
    scoring, reason = calculate_score_with_reason(qualification, valid_purchase_evidence=grounded)
    if output.scoring != scoring or output.decision_reason != reason:
        raise MatrixValidationError("scoring")
    records = output.usage
    if (len(records) not in {1, 2} or request_count != len(records)
            or any(u.attempt_no != i or u.stage != ("qualification" if i == 1 else "qualification_repair")
                   or not u.model for i, u in enumerate(records, 1))
            or records[-1].outcome != "success"
            or (len(records) == 2 and records[0].outcome != "invalid_output")):
        raise MatrixValidationError("usage")
    _claim_checks(inputs, output, products)
    checks = {"evidence_grounded": True, "deterministic_scoring": True, "real_provider_provenance": True,
        "no_cross_business_fact_leakage": True, "no_unsupported_numeric_amounts": True}
    return checks


def result_row(inputs: AgentInput, output: AgentOutput, request_count: int, checks: dict,
               *, provider: str = "avalai", endpoint: str | None = None) -> dict:
    q = output.qualification
    return {"message": inputs.message.id, "business_id": inputs.product.id, "business": inputs.product.name,
        "signals": {name: getattr(q, name) for name in Signals.model_fields},
        "score": output.scoring.score, "decision": output.scoring.decision.value,
        "intent": q.intent, "need": q.need, "limitations": q.limitations,
        "evidence": [e.model_dump() for e in q.evidence], "provider": provider, "provider_mode": "real",
        "endpoint": endpoint,
        "model": output.usage[-1].model, "request_count": request_count,
        "prompt_version": output.prompt_version, "scoring_version": output.scoring_version,
        "decision_reason": output.decision_reason, "usage": usage_report(output.usage), "checks": checks}


def summarize(rows: list[dict], expected: dict[str, str], business_ids: list[str]) -> dict:
    pairs = [(row["message"], row["business_id"]) for row in rows]
    wanted = {(message, business) for message in expected for business in business_ids}
    if (not expected or len(business_ids) < 2 or len(pairs) != len(set(pairs))
            or set(pairs) != wanted or len(set(business_ids)) != len(business_ids)
            or any(business not in business_ids for business in expected.values())):
        raise MatrixValidationError("matrix")
    checks, rankings, comparisons = {}, {}, {}
    for message, business in expected.items():
        group = sorted((row for row in rows if row["message"] == message),
                       key=lambda row: (-row["signals"]["product_fit"], -row["score"], row["business_id"]))
        match = next(row for row in group if row["business_id"] == business)
        others = [row for row in group if row["business_id"] != business]
        checks[message + "_correct_business_ranked_highest"] = all(
            match["signals"]["product_fit"] > row["signals"]["product_fit"] for row in others)
        rankings[message] = [{"business": row["business"], "product_fit": row["signals"]["product_fit"],
                              "score": row["score"], "decision": row["decision"]} for row in group]
        comparisons[message] = {"matched_score_higher": all(match["score"] > row["score"] for row in others),
            "matched_need_strength_higher": all(match["signals"]["need_strength"] > row["signals"]["need_strength"] for row in others),
            "product_fit_margins": {row["business_id"]: match["signals"]["product_fit"] - row["signals"]["product_fit"] for row in others},
            "score_margins": {row["business_id"]: match["score"] - row["score"] for row in others}}
    for name in ("no_cross_business_fact_leakage", "evidence_grounded"):
        checks[name] = all(row["checks"][name] for row in rows)
    return {"status": "automated_pass" if all(checks.values()) else "fail", "genericity_checks": checks,
        "rankings": rankings, "comparisons": comparisons, "human_review_required": True,
        "review_scope": "Inspect intent, need, evidence reasons and limitations for invented prices or capabilities and cross-business paraphrases. "
                        "Automated leakage checks detect foreign profile names/whole fields; they do not prove semantic grounding. "
                        "Fit margins are reported without a tuned cutoff. Score/need-strength comparisons are diagnostic, not forced decisions.",
        "evaluation_scope": "Nine live acceptance examples, not a model-accuracy estimate. Offline fixtures test software only."}


def _print_results(report: dict, *, failed: bool, json_only: bool) -> None:
    if not json_only:
        lines = ["message    | business                  | fit   | buy   | need  | score | decision | provider/model | requests"]
        for row in report["results"]:
            signals = row["signals"]
            lines.append(f"{row['message']:10} | {row['business']:25} | {signals['product_fit']:.3f} | "
                f"{signals['purchase_intent']:.3f} | {signals['need_strength']:.3f} | {row['score']:5} | "
                f"{row['decision']:8} | {row['provider']}/{row['model']} | {row['request_count']}")
        for message, ranking in report.get("rankings", {}).items():
            lines.append(f"\n{message} ranking:")
            lines.extend(f"{i}. {row['business']} (fit={row['product_fit']}, score={row['score']})"
                         for i, row in enumerate(ranking, 1))
        text = "\n".join(lines)
        for name in ("OPENAI_API_KEY",):
            key = os.environ.get(name, "").strip()
            if key:
                text = text.replace(key, "[REDACTED]")
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", errors="backslashreplace").decode("ascii"))
    _print_report(report, failed=failed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nine-operation real-provider matrix; at most 18 paced requests.")
    parser.add_argument("--provider", choices=("avalai",), default="avalai")
    parser.add_argument("--json-only", action="store_true", help="Print the structured comparison report without the text table")
    args = parser.parse_args(argv)
    rows, attempted_usage = [], []
    pacer = None
    phase, current = "configuration", None
    report = {"provider": args.provider, "provider_mode": "real", "results": rows,
        "paid_api_request_attempts": 0, "request_budget": REQUEST_BUDGET, "automatic_sending": False,
        "latency_includes_pacing": True}
    try:
        required = ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL")
        if (os.environ.get("LLM_PROVIDER", "avalai").strip() != "avalai"
                or not all(os.environ.get(name, "").strip() for name in required)):
            raise MatrixValidationError("configuration")
        config = RealProviderConfig.from_env()
        config.require_valid()
        if config.base_url != "https://api.avalai.ir/v1":
            raise MatrixValidationError("configuration")
        endpoint = config.responses_url
        report.update(requested_model=config.model, endpoint=endpoint)
        pacer = RequestPacer(REQUEST_BUDGET)
        phase = "matrix"
        products, messages, expected = load_cases()
        cases = build_matrix(products, messages)
        if (len(products) != 3 or len(messages) != 3 or len(cases) != 9
                or set(expected) != {message.id for message in messages}
                or set(expected.values()) != {product.id for product in products}):
            raise MatrixValidationError("matrix")
        with httpx.Client(timeout=config.timeout_seconds, follow_redirects=False,
                          event_hooks={"request": [pacer.before_request]}) as client, real_provider_client(client):
            for inputs in cases:
                current = {"message": inputs.message.id, "business_id": inputs.product.id}
                attempted_usage = []
                before = pacer.request_count
                phase = "local_validation"
                output = analyze_agent(inputs)
                attempted_usage = output.usage
                checks = validate_run(inputs, output, products, pacer.request_count - before, provider=args.provider)
                rows.append(result_row(inputs, output, pacer.request_count - before, checks,
                                       provider=args.provider, endpoint=endpoint))
        report.update(summarize(rows, expected, [p.id for p in products]))
        code = 0 if report["status"] == "automated_pass" else 2
    except ProviderError as exc:
        # Provider explanations are sanitized; raw errors/HTTP data never escape.
        report.update(status="provider_error", error=str(exc), failed_run=current,
                      failed_usage=usage_report(exc.usage),
                      guidance="Stop on auth/quota/rate-limit/provider failures; no fallback or automatic retry.")
        code = 1
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        check = exc.failed_check if isinstance(exc, MatrixValidationError) else phase
        report.update(status="validation_error", failed_check=check, error=CHECKS[check],
                      failed_run=current, failed_usage=usage_report(attempted_usage))
        code = 2
    except KeyboardInterrupt:
        report.update(status="interrupted", failed_run=current, failed_usage=usage_report(attempted_usage))
        code = 130
    except Exception:
        report.update(status="local_error", error="Unexpected local error; no raw exception or provider data is printed.",
                      failed_run=current, failed_usage=usage_report(attempted_usage))
        code = 3
    report["paid_api_request_attempts"] = pacer.request_count if pacer is not None else 0
    _print_results(report, failed=code != 0, json_only=args.json_only)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
