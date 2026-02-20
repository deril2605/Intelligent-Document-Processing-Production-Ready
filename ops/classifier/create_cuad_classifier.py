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

analyzer_id = "cuad_contract_classifier_v1"

content_analyzer = {
    "baseAnalyzerId": "prebuilt-document",
    "description": (
        "Classifier for CUAD-style contract taxonomy. "
        "Routes an input contract to one of a small set of high-level categories "
        "so downstream extraction can pick the right specialized analyzer."
    ),
    "config": {
        "returnDetails": True,
        "enableSegment": False,
        "contentCategories": {
            "License_Agreements": {
                "description": (
                    "Agreements granting rights to use IP/software/content/technology/trademarks. "
                    "Often include license grant, scope, restrictions, royalties/fees, term, termination."
                )
            },
            "Service": {
                "description": (
                    "Service agreements / MSAs / SOW-like contracts where one party provides services. "
                    "Often include scope of services, service period/term, fees, invoicing/payment, SLA, termination."
                )
            },
            # "Supply": {
            #     "description": (
            #         "Supply or procurement agreements for goods/materials/components. "
            #         "Often include purchase orders, delivery terms, pricing, quantities, inspection/acceptance, warranties."
            #     )
            # },
            # "Manufacturing": {
            #     "description": (
            #         "Manufacturing agreements (contract manufacturing, production). "
            #         "Often include tooling, quality requirements, production volumes, specifications, IP, audits."
            #     )
            # },
            # "Non_Compete_Non_Solicit": {
            #     "description": (
            #         "Non-compete, non-solicitation, restrictive covenants. "
            #         "Focus on restricted activities, duration, geography, remedies, enforcement."
            #     )
            # },
            # "Marketing": {
            #     "description": (
            #         "Marketing/promotion/sponsorship/endorsement/co-branding agreements. "
            #         "Often include campaign deliverables, brand usage guidelines, exclusivity, approvals, term, fees."
            #     )
            # },
            # "Distribution_Channel": {
            #     "description": (
            #         "Reseller/distributor/franchise agreements governing downstream sales channels. "
            #         "Often include territory, resale terms, minimums, channel obligations, trademarks, termination."
            #     )
            # },
            # "Strategic_Alliance_JV": {
            #     "description": (
            #         "Strategic alliance, joint venture, affiliate agreements for partnering/collaboration. "
            #         "Often include governance, contributions, profit share, IP ownership, scope, term, termination."
            #     )
            # }
        }
    },
    "models": {"completion": "gpt-4.1-mini"},
    "tags": {"demo_type": "cuad_contract_classification", "version": "v1"}
}

print(f"Creating CUAD classifier '{analyzer_id}'...")
print(json.dumps(content_analyzer, indent=2))

response = client.begin_create_analyzer(
    analyzer_id=analyzer_id,
    analyzer_template=content_analyzer,
)

print("Waiting for classifier creation to complete...")
client.poll_result(response)
print(f"Classifier '{analyzer_id}' created successfully!")
