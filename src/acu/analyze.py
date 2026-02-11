from __future__ import annotations

import os
from typing import Any, Dict, Optional
from azure.identity import DefaultAzureCredential
from src.acu.client import AzureContentUnderstandingClient

def token_provider():
    credential = DefaultAzureCredential()
    token = credential.get_token("https://cognitiveservices.azure.com/.default")
    return token.token

def analyze_document(
    *,
    analyzer_id: str,
    file_path: str,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    api_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run ACU analyzer on a local file and return the final ACU JSON result.

    Args:
        analyzer_id: ACU analyzer ID
        file_path: local path to input PDF
        endpoint/api_key/api_version: optional overrides (else uses env vars)
        content_type: default application/pdf

    Returns:
        Full ACU operation result JSON (what poll_result returns)
    """
    client = AzureContentUnderstandingClient(
        endpoint=endpoint,
        api_version=api_version,
        subscription_key=api_key,
        token_provider=token_provider if not os.getenv("AZURE_AI_API_KEY") else None,
        x_ms_useragent="azure-ai-content-understanding-python-sample-ga"    # The user agent is used for tracking sample usage and does not provide identity information. You can change this if you want to opt out of tracking.
    )

    analysis_response = client.begin_analyze_binary(
        analyzer_id=analyzer_id,
        file_location=file_path,
    )
    return client.poll_result(analysis_response)

def analyze_bytes(
    *,
    analyzer_id: str,
    data: bytes,
    endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    api_version: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run ACU analyzer on in-memory bytes and return the final ACU JSON result.
    """
    client = AzureContentUnderstandingClient(
        endpoint=os.getenv("AZURE_AI_ENDPOINT"),
        api_version="2025-11-01",
        subscription_key=os.getenv("AZURE_AI_API_KEY"),
        token_provider=token_provider if not os.getenv("AZURE_AI_API_KEY") else None,
        x_ms_useragent="azure-ai-content-understanding-python-sample-ga"    # The user agent is used for tracking sample usage and does not provide identity information. You can change this if you want to opt out of tracking.
    )

    analysis_response = client.begin_analyze_binary(
        analyzer_id=analyzer_id,
        data=data,
    )
    return client.poll_result(analysis_response)