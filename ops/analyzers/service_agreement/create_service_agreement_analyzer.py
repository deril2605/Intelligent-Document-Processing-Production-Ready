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

# Ensure defaults include model deployment mapping for gpt-4.1-mini
# defaults = client.get_defaults()
# model_deployments = defaults.get("modelDeployments", {}) if isinstance(defaults, dict) else {}
# if not model_deployments.get("gpt-4.1-mini"):
#     completion_deployment = (
#         os.getenv("ACU_GPT41_MINI_DEPLOYMENT")
#         or os.getenv("AZURE_OPENAI_DEPLOYMENT")
#     )
#     if not completion_deployment:
#         raise RuntimeError(
#             "ACU defaults are not configured for gpt-4.1-mini. "
#             "Set ACU_GPT41_MINI_DEPLOYMENT (or AZURE_OPENAI_DEPLOYMENT) and rerun."
#         )
#     print(f"Setting ACU defaults: gpt-4.1-mini -> {completion_deployment}")
#     updated_defaults = client.update_defaults({"gpt-4.1-mini": completion_deployment})
#     print("Updated defaults:")
#     print(json.dumps(updated_defaults, indent=2))

service_analyzer_id = "service_agreement_extraction_wrt_CUAD_v4_raw_normalized_singlepass"

# Tune these for latency + bbox anchoring reliability
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


service_agreement_analyzer = {
    "baseAnalyzerId": "prebuilt-document",
    "description": (
        "Single-pass analyzer for Service Agreements that outputs BOTH raw (verbatim, source-anchored) "
        "and normalized (machine-friendly) fields. Use *_raw for bounding boxes; use *_normalized for DB/evaluation. "
        "Raw fields are intentionally capped to reduce latency and token usage."
    ),
    "config": {
        "returnDetails": False,
        "enableOcr": True,      # set False if all PDFs are digitally-generated and text is selectable
        "enableLayout": True,   # keep True for reliable sources/quads
        "estimateFieldSourceAndConfidence": True
    },
    "fieldSchema": {
        "name": "ServiceAgreementFields_RawNormalized_SinglePass",
        "fields": {
            # 1) Document Name
            "DocumentName_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc("Official title of the agreement (e.g., 'SERVICE AGREEMENT', exhibit header title).")
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

            # 3) Effective Date (or agreement date used as effective)
            "EffectiveDate_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Effective date text as written (may appear as 'Effective Date', 'dated as of', 'entered into on')."
                )
            },
            "EffectiveDate_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Effective date in mm/dd/yyyy. If only placeholders (e.g., '[Date]') or no explicit date, return empty."
                )
            },

            # 4) Service Term / Service Period
            "ServiceTerm_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Term/Service Period language as written (start/end dates, duration, renewal, evergreen)."
                )
            },
            "ServiceTerm_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Return a concise structured value: "
                    "'mm/dd/yyyy-mm/dd/yyyy' if explicit range, else duration like '2 years', '5 years', "
                    "else 'Evergreen/Auto-renew' if applicable, else empty string."
                )
            },

            # 5) Scope of Services
            "ScopeOfServices_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Minimal clause fragment describing the services to be provided (scope/description/list)."
                )
            },
            "ScopeOfServices_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Concise list of services separated by '; ' (not a paragraph). "
                    "Example: 'platform maintenance; data processing; reporting support'."
                )
            },

            # 6) Service Fee / Compensation
            "ServiceFee_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Fee/compensation language as written (rate, schedule reference, tiered %, fixed $ amount, formula)."
                )
            },
            "ServiceFee_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Best-effort structured fee expression (not a paragraph). Examples: "
                    "'USD 970,000/month', '0.65% AUM up to 25m; 0.60% 25m-50m', 'cost+markup', '% of revenue'. "
                    "If not present, empty string."
                )
            },

            # 7) Payment Terms (invoicing + due)
            "PaymentTerms_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Payment terms as written (invoice frequency, due date/net days, payment method)."
                )
            },
            "PaymentTerms_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Concise: '<invoice frequency>; <due/net days>; <method if stated>'. "
                    "Example: 'monthly invoice; net 45; bank transfer'. If not present, empty string."
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
                "description": "Jurisdiction only (state/country/province). Example: 'Massachusetts' or 'England and Wales'."
            },

            # 9) Confidentiality (presence + key qualifier)
            "Confidentiality_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Confidentiality clause fragment as written (include survival duration if explicitly stated)."
                )
            },
            "Confidentiality_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Return 'Yes' if confidentiality obligations exist else 'No'. "
                    "If a survival period is explicitly stated, append '; <duration>' (e.g., 'Yes; 5 years'). "
                    "If unclear, empty string."
                )
            },

            # 10) Termination (for convenience / for cause / notice)
            "Termination_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Termination clause fragment as written (notice period, for cause/cure, without cause, insolvency triggers)."
                )
            },
            "Termination_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Concise structured summary, e.g. "
                    "'for convenience: 60 days notice; for cause: 30 day cure' "
                    "or 'either party: 30 days written notice'. If not present, empty string."
                )
            },

            # 11) Liability / Indemnification (combined)
            "LiabilityOrIndemnification_raw": {
                "type": "string",
                "method": "generate",
                "description": raw_desc(
                    "Key limitation of liability and/or indemnification clause fragment as written (minimal span)."
                )
            },
            "LiabilityOrIndemnification_normalized": {
                "type": "string",
                "method": "generate",
                "description": (
                    "Best-effort structured summary (not a paragraph). Examples: "
                    "'liability cap=fees paid in last 12 months; excludes consequential damages=yes; indemnity=yes (provider)' "
                    "or 'standard indemnification; gross negligence carve-out'. If unclear, empty string."
                )
            },
        }
    },
    "models": {
        "completion": "gpt-4.1-mini"
    }
}

print(json.dumps(service_agreement_analyzer, indent=2))

resp = client.begin_create_analyzer(
    analyzer_id=service_analyzer_id,
    analyzer_template=service_agreement_analyzer,
)

print("Waiting for analyzer creation to complete...")
client.poll_result(resp)
print(f"Analyzer '{service_analyzer_id}' created successfully!")

