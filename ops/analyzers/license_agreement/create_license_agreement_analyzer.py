import json
import os

from dotenv import load_dotenv

from src.acu.client import AzureContentUnderstandingClient

load_dotenv()

endpoint = os.getenv("AZURE_AI_ENDPOINT")
api_key = os.getenv("AZURE_AI_API_KEY")
api_version = os.getenv("AZURE_AI_API_VERSION", "2025-11-01")

if not endpoint:
    raise RuntimeError("Missing AZURE_AI_ENDPOINT")
if not api_key:
    raise RuntimeError("Missing AZURE_AI_API_KEY")

client = AzureContentUnderstandingClient(
    endpoint=endpoint,
    api_version=api_version,
    subscription_key=api_key,
    token_provider=None,
)

defaults = client.get_defaults()
model_deployments = defaults.get("modelDeployments", {}) if isinstance(defaults, dict) else {}
if not model_deployments.get("gpt-4.1-mini"):
    completion_deployment = (
        os.getenv("ACU_GPT41_MINI_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
    )
    if not completion_deployment:
        raise RuntimeError(
            "ACU defaults are not configured for gpt-4.1-mini. "
            "Set ACU_GPT41_MINI_DEPLOYMENT (or AZURE_OPENAI_DEPLOYMENT) and rerun."
        )
    print(f"Setting ACU defaults: gpt-4.1-mini -> {completion_deployment}")
    updated_defaults = client.update_defaults({"gpt-4.1-mini": completion_deployment})
    print("Updated defaults:")
    print(json.dumps(updated_defaults, indent=2))

license_analyzer_id = "license_agreement_extraction_wrt_CUAD_v4_raw_normalized_singlepass"

# Tune these to control verbosity (big lever for speed + output tokens)
RAW_CHAR_CAP = 350          # keep raw extracts short for bbox anchoring
RAW_SENTENCE_CAP = 2        # additional guardrail for long clauses


def raw_desc(base: str) -> str:
    return (
        f"{base} "
        f"VERBATIM ONLY: copy exact text from the document (no paraphrase, no reformatting, no normalization). "
        f"Return the minimal span necessary to answer. "
        f"Hard limits: max {RAW_SENTENCE_CAP} sentences OR ~{RAW_CHAR_CAP} characters (whichever is smaller). "
        f"If the value is not present, return an empty string."
    )


license_agreement_analyzer = {
    "baseAnalyzerId": "prebuilt-document",
    "description": (
        "Single-pass analyzer for License Agreements that outputs BOTH raw (verbatim, source-anchored) "
        "and normalized (machine-friendly) fields. Use *_raw for bounding boxes; use *_normalized for DB/evaluation. "
        "Raw fields are intentionally capped to reduce latency and token usage."
    ),
    "config": {
        # FINAL RECOMMENDATION: keep one analyzer, keep returnDetails False
        "returnDetails": False,
        "enableOcr": True,   # set to False if PDFs are always digitally generated (copy/paste works)
        "enableLayout": True,  # keep True so sources/quads can be produced reliably
        "estimateFieldSourceAndConfidence": True  # needed for bbox (field-level source quads)
    },
    "fieldSchema": {
        "name": "LicenseAgreementFields_RawNormalized_SinglePass",
        "fields": {
            # 1) Document Name
            "DocumentName_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc("Official title of the agreement.")
            },
            "DocumentName_normalized": {
                "type": "string",
                "method": "generate",
                "description": "Clean official title as a single line. Remove extra whitespace/line breaks."
            },

            # 2) Parties
            "Parties_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Parties to the agreement as written (including defined terms / aliases in quotes or parentheses)."
                )
            },
            "Parties_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Normalized parties list. Separate multiple parties with '; '. "
                    "Preserve aliases in parentheses if present. Remove extra whitespace."
                )
            },

            # 3) Agreement Date
            "AgreementDate_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc("Execution/signing date text as written (do not convert format).")
            },
            "AgreementDate_normalized": {
                "type": "string",
                "method": "generate",
                "description": "Agreement execution date in mm/dd/yyyy. If not present, return empty string."
            },

            # 4) Effective Date
            "EffectiveDate_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc("Effective date text as written (may include label like 'Effective Date').")
            },
            "EffectiveDate_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Effective date in mm/dd/yyyy. If only relative wording exists and no explicit date is stated, "
                    "return empty string."
                )
            },

            # 5) Expiration Date / Term End
            "ExpirationDate_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Initial term expiration/end date text as written, or wording indicating perpetual/evergreen."
                )
            },
            "ExpirationDate_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Return expiration date in mm/dd/yyyy if explicitly stated; else return 'Perpetual' if perpetual/evergreen; "
                    "else empty string."
                )
            },

            # 6) Renewal Term
            "RenewalTerm_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc("Renewal language as written (auto-renew, successive terms, conditions).")
            },
            "RenewalTerm_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Concise structured phrase, e.g. 'successive 1 year', '2 years', 'month-to-month', "
                    "'perpetual', or 'no renewal'. Not a paragraph."
                )
            },

            # 7) Notice Period to Terminate Renewal
            "NoticeToTerminateRenewal_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Notice period wording required to prevent renewal (keep units/format as written)."
                )
            },
            "NoticeToTerminateRenewal_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Concise notice period like '60 days' or '30 days'. Use the notice that applies to stopping renewal."
                )
            },

            # 8) Governing Law
            "GoverningLaw_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc("Governing law clause fragment containing the jurisdiction as written.")
            },
            "GoverningLaw_normalized": {
                "type": "string",
                "method": "generate",
                "description": "Jurisdiction only (state/country/province). Example: 'California'."
            },

            # 9) License Grant
            "LicenseGrant_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "License grant clause text as written (scope/rights grant). Return minimal span; avoid long paragraphs."
                )
            },
            "LicenseGrant_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Structured summary as key=value pairs, e.g. "
                    "'type=trademark; exclusivity=non-exclusive; territory=worldwide; sublicensing=yes; transferable=no'."
                )
            },

            # 10) Exclusivity
            "Exclusivity_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc("Text indicating exclusivity/non-exclusivity as written.")
            },
            "Exclusivity_normalized": {
                "type": "string",
                "method": "generate",
                "description": "Return 'Yes' if exclusive else 'No'. If unclear, empty string."
            },

            # 11) Termination for Convenience
            "TerminationForConvenience_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc("Text indicating termination without cause (termination for convenience) as written.")
            },
            "TerminationForConvenience_normalized": {
                "type": "string",
                "method": "generate",
                "description": "Return 'Yes' if either party may terminate without cause else 'No'. If unclear, empty string."
            },
        }
    },
    "models": {
        "completion": "gpt-4.1-mini"
    }
}

print(json.dumps(license_agreement_analyzer, indent=2))

resp = client.begin_create_analyzer(
    analyzer_id=license_analyzer_id,
    analyzer_template=license_agreement_analyzer,
)

print("Waiting for analyzer creation to complete...")
client.poll_result(resp)
print(f"Analyzer '{license_analyzer_id}' created successfully!")
