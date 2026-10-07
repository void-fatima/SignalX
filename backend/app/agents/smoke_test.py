"""Manual AvalAI/Gemini scenarios; import and --help never make calls."""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.agents.acceptance import (
    AcceptanceValidationError, RequestPacer, analysis_checks, load_snapshot,
    save_snapshot, usage_report, validation_diagnostic,
)
from app.agents.contracts import AgentInput, AgentOutput, Signals
from app.agents.orchestrator import analyze_agent
from app.agents.providers.base import ProviderError
from app.agents.providers.config import RealProviderConfig
from app.agents.providers.factory import configured_real_provider, real_provider_client
from app.agents.providers.gemini_config import (
    GEMINI_BASE_URL, GEMINI_SMOKE_MODEL, GeminiProviderConfig,
)
from app.agents.reply import generate_suggested_reply
from app.agents.reply_draft import PERSIAN

BASE_URL = "https://api.avalai.ir/v1"
MODEL = "gpt-5.6-luna"
TARGET_TEXT = "I'm looking for a Python course for beginners. How much does it cost?"
PERSIAN_TEXT = "من تازه می‌خوام پایتون یاد بگیرم و دنبال یه دوره مناسب مبتدی‌ها هستم. قیمتش چقدره؟"
CONTEXT_TEXT = "کسی دوره Python Starter رو امتحان کرده؟ برای مبتدی‌ها مناسبه؟"
CONTEXT_TARGET = "آره ولی خیلی گرونه."


def build_input(scenario: str = "english") -> AgentInput:
    timestamp = datetime.now(timezone.utc)
    contextual = scenario == "context"
    message_id = "smoke-context-target" if contextual else "smoke-target"
    context = [{"id": "smoke-context", "content": CONTEXT_TEXT, "author": "another-community-user",
                "timestamp": timestamp - timedelta(minutes=1)}] if contextual else []
    return AgentInput.model_validate({
        "product": {"id": "smoke-product", "name": "Python Starter Course",
                    "description": ("Beginner-friendly Python programming course." if scenario == "english"
                                    else "Beginner Python course with practical exercises."),
                    "target_customer": "Beginners"},
        "message": {"id": message_id,
                    "content": CONTEXT_TARGET if contextual else PERSIAN_TEXT if scenario == "persian" else TARGET_TEXT,
                    "author": "smoke-test-user", "timestamp": timestamp, "conversation_id": "smoke-conversation"},
        "context_messages": context,
        "metadata": {"run_id": str(uuid4()), "provider_mode": "real"},
    })


def _print_report(report: dict, *, failed: bool = False) -> None:
    secrets = [value for name in ("OPENAI_API_KEY", "GEMINI_API_KEY")
               for key in (os.environ.get(name, ""),)
               for value in (key, key.strip()) if value]

    def redact(value):
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {redact(name): redact(item) for name, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    stream = sys.stderr if failed else sys.stdout
    text = json.dumps(redact(report), indent=2, ensure_ascii=False)
    try:
        text.encode(stream.encoding or "utf-8")
    except UnicodeEncodeError:
        text = json.dumps(redact(report), indent=2, ensure_ascii=True)
    print(text, file=stream)


def _analysis_report(inputs: AgentInput, output: AgentOutput, scenario: str) -> dict:
    checks = analysis_checks(inputs, output, contextual=scenario == "context")
    qualification = output.qualification
    return {"scenario": scenario, "status": "success", "screening": output.screening.model_dump(),
        "intent": qualification.intent, "need": qualification.need,
        "signals": {name: getattr(qualification, name) for name in Signals.model_fields},
        "score": output.scoring.score, "decision": output.scoring.decision.value,
        "decision_reason": output.decision_reason, "prompt_version": output.prompt_version,
        "scoring_version": output.scoring_version,
        "evidence": [item.model_dump() for item in qualification.evidence],
        "limitations": qualification.limitations, "usage": usage_report(output.usage),
        "checks": checks, "human_review_required": True,
        "review": "Inspect intent/need against the supplied target message and context; semantic correctness is not proven by schema checks."}


def _reply_report(inputs: AgentInput, original: AgentOutput, updated: AgentOutput) -> dict:
    if (updated.model_dump(exclude={"usage", "suggested_reply"}) != original.model_dump(exclude={"usage", "suggested_reply"})
            or updated.usage[:len(original.usage)] != original.usage or not updated.suggested_reply):
        raise AcceptanceValidationError("analysis_unchanged")
    records = updated.usage[len(original.usage):]
    if not records or any(not record.stage.startswith("suggested_reply") or record.provider_mode != "real" for record in records):
        raise AcceptanceValidationError("reply_usage_appended")
    if bool(PERSIAN.search(inputs.message.content)) != bool(PERSIAN.search(updated.suggested_reply)):
        raise AcceptanceValidationError("language_matches")
    return {"scenario": "reply", "status": "success", "suggested_reply": updated.suggested_reply,
        "score": updated.scoring.score, "decision": updated.scoring.decision.value,
        "usage": usage_report(records), "prior_usage": usage_report(original.usage),
        "checks": {"analysis_unchanged": True, "reply_usage_appended": True, "language_matches": True,
                   "no_duplicate_qualification": True},
        "human_review_required": True, "automatic_sending": False,
        "review": "Inspect the draft for helpfulness and implicit unsupported claims before any separate human approval."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=
        "Run ONE paid smoke scenario or the bounded acceptance sequence. Repairs are paced; no automatic sending.")
    parser.add_argument("--scenario", choices=("english", "persian", "context", "reply", "acceptance"), default="english")
    parser.add_argument("--provider", choices=("avalai", "gemini"),
                        help="Must match LLM_PROVIDER for live execution; never overrides the environment")
    parser.add_argument("--save-analysis", type=Path, help="Explicit new local snapshot for a later reply; never overwrites")
    parser.add_argument("--analysis-file", type=Path, help="Saved real input/analysis required for reply-only execution")
    parser.add_argument("--replay-analysis", type=Path, help="Check a paired snapshot offline; no provider request or new usage")
    args = parser.parse_args(argv)
    if (args.scenario == "reply") != (args.analysis_file is not None):
        parser.error("--analysis-file is required only for --scenario reply")
    if args.save_analysis is not None and args.scenario in {"reply", "acceptance"}:
        parser.error("--save-analysis applies only to a single qualification scenario")
    if args.replay_analysis is not None and (args.scenario in {"reply", "acceptance"}
            or args.analysis_file is not None or args.save_analysis is not None):
        parser.error("--replay-analysis applies only to a single qualification scenario without other snapshot options")
    selected = args.provider or os.environ.get("LLM_PROVIDER", "avalai").strip()
    endpoint = GEMINI_BASE_URL + "chat/completions" if selected == "gemini" else BASE_URL + "/responses"
    summary = {"provider_mode": "real", "provider": selected if selected in {"avalai", "gemini"} else "invalid",
        "requested_model": GEMINI_SMOKE_MODEL if selected == "gemini" else MODEL, "endpoint": endpoint,
        "scenario": args.scenario, "toman_per_usd_reporting_only": "270000",
        "exact_account_charge": False, "latency_includes_pacing": True,
        "cost_note": ("Gemini entitlement/charge cannot be inferred; frozen contract retains null/unknown."
                      if selected == "gemini" else "Configured USD rates provide estimates, not account charges."),
        "execution_mode": "offline_replay" if args.replay_analysis else "live"}
    pacer = RequestPacer(budget=6 if args.scenario == "acceptance" else 2, endpoint=endpoint)
    reports = []
    attempt_usage = []
    prior_usage_count = 0
    phase = "input_validation"
    try:
        if args.replay_analysis is not None:
            phase = "snapshot_load"
            snapshot = load_snapshot(args.replay_analysis)
            inputs, output = snapshot.agent_input, snapshot.analysis
            # The frozen snapshot records an executed prompt and actual models,
            # but not the original endpoint or requested model. Do not infer
            # historical transport from the current process configuration.
            recorded_provider = {"qualify_gemini_v1": "gemini",
                                 "qualify_real_v1": "responses"}.get(output.prompt_version, "unknown")
            summary.update(provider=recorded_provider, requested_model=None, endpoint=None,
                           latency_includes_pacing=None,
                           cost_note="Recorded usage only; no request was made and no account charge is inferred.")
            attempt_usage = output.usage
            expected = build_input(args.scenario)
            if (inputs.product != expected.product or inputs.message.content != expected.message.content
                    or [m.content for m in inputs.context_messages] != [m.content for m in expected.context_messages]):
                raise AcceptanceValidationError("scenario_match")
            phase = "analysis_acceptance"
            report = _analysis_report(inputs, output, args.scenario)
            _print_report({**summary, **report, "paid_api_request_attempts": 0, "usage_from_recording": True})
            return 0
        if selected != configured_real_provider():
            raise ProviderError("--provider must match LLM_PROVIDER; no provider override or fallback is allowed", [])
        if selected == "gemini":
            if not all(os.environ.get(name, "").strip() for name in
                       ("LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_BASE_URL")):
                raise ProviderError("Gemini live scenarios require explicit LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL and GEMINI_BASE_URL", [])
            config = GeminiProviderConfig.from_env()
            if config.base_url != GEMINI_BASE_URL or config.model != GEMINI_SMOKE_MODEL:
                raise ProviderError("Gemini smoke test requires gemini-3.5-flash-lite and the official Gemini OpenAI-compatible base URL", [])
        else:
            config = RealProviderConfig.from_env()
        config.require_valid()
        if selected == "avalai" and (config.base_url != BASE_URL or config.model != MODEL):
            _print_report({**summary, "status": "configuration_error", "paid_api_request_attempts": 0,
                "error": "Set OPENAI_BASE_URL=https://api.avalai.ir/v1 and OPENAI_MODEL=gpt-5.6-luna. No analysis was run."}, failed=True)
            return 2
        if selected == "avalai" and not os.environ.get("OPENAI_API_KEY", "").strip():
            _print_report({**summary, "status": "configuration_error", "paid_api_request_attempts": 0,
                "error": "OPENAI_API_KEY must be set in this process environment. No analysis was run."}, failed=True)
            return 2
        if selected == "avalai" and args.scenario != "english" and (config.rates is None
                or config.rates.input_usd_per_million != Decimal("0.20")
                or config.rates.output_usd_per_million != Decimal("1.20")):
            _print_report({**summary, "status": "configuration_error", "paid_api_request_attempts": 0,
                "error": "Acceptance requires OPENAI_INPUT_USD_PER_MILLION=0.20, OPENAI_OUTPUT_USD_PER_MILLION=1.20 and a nonempty OPENAI_PRICE_VERSION."}, failed=True)
            return 2
        if args.save_analysis is not None and (args.save_analysis.exists() or not args.save_analysis.parent.is_dir()):
            raise AcceptanceValidationError("snapshot_path")
        phase = "snapshot_load"
        snapshot = load_snapshot(args.analysis_file) if args.analysis_file is not None else None
        # Caller-owned paced client is scoped to this run. Default production
        # clients and public entry point logic are unchanged; no Mock injection.
        with httpx.Client(timeout=config.timeout_seconds, follow_redirects=False,
                          event_hooks={"request": [pacer.before_request]}) as client, real_provider_client(client):
            if snapshot is not None:
                prior_usage_count = len(snapshot.analysis.usage)
                phase = "reply_eligibility"
                updated = generate_suggested_reply(snapshot.agent_input, snapshot.analysis)
                attempt_usage = updated.usage[prior_usage_count:]
                phase = "analysis_unchanged"
                reports.append(_reply_report(snapshot.agent_input, snapshot.analysis, updated))
            else:
                cases = ("persian", "context") if args.scenario == "acceptance" else (args.scenario,)
                persian_pair = None
                for scenario in cases:
                    attempt_usage = []
                    phase = "input_validation"
                    inputs = build_input(scenario)
                    phase = "analysis_output_validation"
                    output = analyze_agent(inputs)
                    attempt_usage = output.usage
                    # An explicitly requested snapshot retains the actual typed
                    # provider analysis even when a later acceptance check fails.
                    if args.save_analysis is not None:
                        phase = "snapshot_save"
                        save_snapshot(args.save_analysis, inputs, output)
                    phase = "analysis_acceptance"
                    report = _analysis_report(inputs, output, scenario)
                    if args.save_analysis is not None:
                        report["analysis_snapshot"] = str(args.save_analysis)
                    reports.append(report)
                    if scenario == "persian":
                        persian_pair = (inputs, output)
                if args.scenario == "acceptance":
                    inputs, original = persian_pair
                    prior_usage_count = len(original.usage)
                    attempt_usage = []
                    phase = "reply_eligibility"
                    updated = generate_suggested_reply(inputs, original)
                    attempt_usage = updated.usage[prior_usage_count:]
                    phase = "analysis_unchanged"
                    reports.append(_reply_report(inputs, original, updated))
    except ProviderError as exc:
        diagnostic_report = ({"validation_diagnostics": exc.diagnostics,
            "failed_check": exc.diagnostics[-1]["failed_check"],
            "failure_category": exc.diagnostics[-1]["failure_category"]} if exc.diagnostics else {})
        _print_report({**summary, "status": "provider_error", "error": str(exc),
            **diagnostic_report,
            "guidance": "Stop this run on authentication, quota, balance, rate-limit or compatibility failures. No fallback or automatic HTTP 429 retry.",
            "paid_api_request_attempts": pacer.request_count, "completed_scenarios": reports,
            "usage": usage_report(exc.usage[prior_usage_count:])}, failed=True)
        return 1
    except (ValidationError, ValueError, OSError) as exc:
        diagnostic = (exc.diagnostic if isinstance(exc, AcceptanceValidationError)
                      else validation_diagnostic(phase))
        _print_report({**summary, "status": "validation_error", **diagnostic,
            "error": diagnostic["explanation"],
            "paid_api_request_attempts": pacer.request_count, "completed_scenarios": reports,
            "usage": usage_report(attempt_usage)}, failed=True)
        return 2
    except KeyboardInterrupt:
        _print_report({**summary, "status": "interrupted", "paid_api_request_attempts": pacer.request_count,
            "error": "Interrupted. Dispatched requests may have been processed; exact account charges are unavailable.",
            "completed_scenarios": reports, "usage": usage_report(attempt_usage)}, failed=True)
        return 130
    except Exception:
        _print_report({**summary, "status": "local_error", "paid_api_request_attempts": pacer.request_count,
            "error": "Unexpected local failure; no raw exception, headers or response body is printed.",
            "completed_scenarios": reports, "usage": usage_report(attempt_usage)}, failed=True)
        return 3

    result = {"status": "success", "results": reports} if args.scenario == "acceptance" else reports[0]
    _print_report({**summary, **result, "paid_api_request_attempts": pacer.request_count})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
