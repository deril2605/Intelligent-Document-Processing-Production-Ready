#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.acu.client import AzureContentUnderstandingClient


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Create or upsert a license agreement ACU analyzer.")
    parser.add_argument("--analyzer-id", default=os.getenv("ACU_ANALYZER_ID"), help="ACU analyzer id to create/update")
    parser.add_argument("--endpoint", default=os.getenv("AZURE_AI_ENDPOINT"), help="AZURE_AI_ENDPOINT")
    parser.add_argument("--api-key", default=os.getenv("AZURE_AI_API_KEY"), help="AZURE_AI_API_KEY")
    parser.add_argument("--api-version", default=os.getenv("AZURE_AI_API_VERSION", "2025-11-01"), help="ACU API version")
    parser.add_argument(
        "--schema",
        default=str(Path(__file__).with_name("schema.json")),
        help="Path to analyzer schema JSON",
    )
    parser.add_argument("--wait", action="store_true", help="Wait for long-running operation completion")
    parser.add_argument("--timeout", type=int, default=900, help="Poll timeout seconds when --wait is set")
    args = parser.parse_args()
    if not args.analyzer_id:
        raise ValueError("Missing analyzer id. Provide --analyzer-id or set ACU_ANALYZER_ID")
    if not args.endpoint:
        raise ValueError("Missing endpoint. Provide --endpoint or set AZURE_AI_ENDPOINT")
    if not args.api_key:
        raise ValueError("Missing api key. Provide --api-key or set AZURE_AI_API_KEY")

    schema_path = Path(args.schema)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    analyzer_schema = json.loads(schema_path.read_text(encoding="utf-8"))

    client = AzureContentUnderstandingClient(
        endpoint=args.endpoint,
        api_version=args.api_version,
        subscription_key=args.api_key,
        token_provider=None,
    )

    response = client.begin_create_analyzer(
        analyzer_id=args.analyzer_id,
        analyzer_template=analyzer_schema,
    )

    print(f"Analyzer create request accepted for '{args.analyzer_id}'. status={response.status_code}")
    if args.wait:
        result = client.poll_result(response, timeout_seconds=args.timeout, polling_interval_seconds=3)
        print(json.dumps(result, indent=2))
    else:
        print("Run with --wait to poll until completion.")


if __name__ == "__main__":
    main()
