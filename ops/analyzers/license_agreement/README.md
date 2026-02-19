# License Agreement Analyzer Ops

Files:

- `create_license_agreement_analyzer.py`: canonical analyzer creation script
- `schema.json`: reference schema snapshot (optional)

## Usage

From repo root:

```bash
python -m ops.analyzers.license_agreement.create_license_agreement_analyzer
```

Script reads these environment variables:

- `AZURE_AI_ENDPOINT`
- `AZURE_AI_API_KEY`
- `AZURE_AI_API_VERSION`

You can override via flags (`--analyzer-id`, `--endpoint`, `--api-key`, `--api-version`, `--schema`).
