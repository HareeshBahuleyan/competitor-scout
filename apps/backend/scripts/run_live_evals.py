#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from competitor_scout.agents.client import OtariClient, OtariError
from competitor_scout.agents.contracts import ChildTaskResult, SynthesisResult
from competitor_scout.agents.prompts import child_messages, synthesis_messages
from competitor_scout.config import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
CORPUS_PATH = REPOSITORY_ROOT / "evals" / "competitor-signals-v1.json"
REPORT_DIRECTORY = REPOSITORY_ROOT / "eval-reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run paid hosted-Otari agent evaluations")
    parser.add_argument(
        "--confirm-paid-run",
        action="store_true",
        help="Second explicit safeguard acknowledging that the run can incur cost",
    )
    return parser.parse_args()


def require_paid_authorization(args: argparse.Namespace) -> None:
    if os.environ.get("ALLOW_PAID_OTARI_EVALS", "").casefold() != "true":
        raise SystemExit("Paid evaluation blocked: set ALLOW_PAID_OTARI_EVALS=true explicitly.")
    if not args.confirm_paid_run:
        raise SystemExit(
            "Paid evaluation blocked: pass --confirm-paid-run as the second safeguard."
        )


def _load_corpus() -> list[dict[str, Any]]:
    document = json.loads(CORPUS_PATH.read_text())
    if not isinstance(document, list) or not document:
        raise ValueError("evaluation corpus must be a non-empty JSON array")
    return document


async def run_case(
    client: OtariClient,
    case: dict[str, Any],
    *,
    main_model: str,
    child_model: str,
    child_tokens: int,
    main_tokens: int,
    child_deadline: int,
    synthesis_deadline: int,
) -> dict[str, Any]:
    case_id = str(case["id"])
    session_label = f"live-eval:{case_id}"
    child_result, child_metadata = await client.structured_completion(
        model=child_model,
        messages=child_messages(
            {
                "objective": "Extract only directly quoted material competitor changes.",
                "source_url": case["source_url"],
                "source_text": case["source_text"],
                "search_allowed": False,
            }
        ),
        output_type=ChildTaskResult,
        session_label=session_label,
        max_completion_tokens=child_tokens,
        deadline_seconds=child_deadline,
    )
    synthesis_result, main_metadata = await client.structured_completion(
        model=main_model,
        messages=synthesis_messages(child_result),
        output_type=SynthesisResult,
        session_label=session_label,
        max_completion_tokens=main_tokens,
        deadline_seconds=synthesis_deadline,
    )

    expected_publish = bool(case["expected_publish"])
    published = bool(synthesis_result.findings)
    citation_valid = all(
        all(index < len(child_result.evidence) for index in finding.evidence_indexes)
        for finding in synthesis_result.findings
    )
    category_correct = not expected_publish or any(
        finding.category.value == case["expected_category"] for finding in synthesis_result.findings
    )
    quote_fragment = case["required_quote_fragment"]
    quote_present = quote_fragment is None or any(
        str(quote_fragment) in evidence.quoted_text for evidence in child_result.evidence
    )
    return {
        "id": case_id,
        "expected_publish": expected_publish,
        "published": published,
        "unsupported_rejected": expected_publish or not published,
        "category_correct": category_correct,
        "citation_valid": citation_valid,
        "required_quote_present": quote_present,
        "child_request_id": child_metadata.request_id,
        "main_request_id": main_metadata.request_id,
        "settled_cost_usd": str(
            sum(
                (
                    value
                    for value in (
                        child_metadata.usage.cost_usd,
                        main_metadata.usage.cost_usd,
                    )
                    if value is not None
                ),
                Decimal("0"),
            )
        ),
    }


async def run_live() -> int:
    settings = get_settings()
    corpus = _load_corpus()
    maximum_cost = settings.max_run_cost_usd * len(corpus) * 2
    print(
        f"Starting {len(corpus)} cases. Conservative configured maximum: USD {maximum_cost:.2f}.",
        flush=True,
    )
    results: list[dict[str, Any]] = []
    async with OtariClient(settings) as client:
        for case in corpus:
            try:
                result = await run_case(
                    client,
                    case,
                    main_model=settings.otari_main_model,
                    child_model=settings.otari_child_model,
                    child_tokens=settings.child_output_token_limit,
                    main_tokens=settings.main_output_token_limit,
                    child_deadline=settings.child_deadline_seconds,
                    synthesis_deadline=settings.synthesis_deadline_seconds,
                )
            except OtariError as error:
                result = {"id": case["id"], "error_code": error.code}
            results.append(result)

    scored = [result for result in results if "error_code" not in result]
    rejected = [result for result in scored if not result["expected_publish"]]
    supported = [result for result in scored if result["expected_publish"]]
    thresholds = {
        "all_cases_completed": len(scored) == len(corpus),
        "unsupported_rejection": bool(rejected)
        and all(result["unsupported_rejected"] for result in rejected),
        "valid_citations": bool(supported)
        and all(result["citation_valid"] for result in supported),
        "category_accuracy_at_least_90_percent": bool(supported)
        and sum(result["category_correct"] for result in supported) / len(supported) >= 0.9,
        "required_quotes": bool(supported)
        and all(result["required_quote_present"] for result in supported),
    }
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "corpus": CORPUS_PATH.name,
        "thresholds": thresholds,
        "results": results,
    }
    REPORT_DIRECTORY.mkdir(exist_ok=True)
    report_path = REPORT_DIRECTORY / (
        f"competitor-signals-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"Safe evaluation report written to {report_path}")
    return 0 if all(thresholds.values()) else 1


def main() -> int:
    args = parse_args()
    try:
        require_paid_authorization(args)
    except SystemExit as error:
        print(str(error), file=sys.stderr)
        return 2
    return asyncio.run(run_live())


if __name__ == "__main__":
    raise SystemExit(main())
