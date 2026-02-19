# License Agreement Analyzer Ops

Files:

- `schema.json`: analyzer schema
- `create_analyzer.py`: create/upsert analyzer from schema
- `update_analyzer.py`: update existing analyzer with schema

## Usage

From repo root:

```bash
python ops/analyzers/license_agreement/create_analyzer.py --wait
```

or

```bash
python ops/analyzers/license_agreement/update_analyzer.py --wait
```

By default scripts read:

- `ACU_ANALYZER_ID`
- `AZURE_AI_ENDPOINT`
- `AZURE_AI_API_KEY`
- `AZURE_AI_API_VERSION`

You can override via flags (`--analyzer-id`, `--endpoint`, `--api-key`, `--api-version`, `--schema`).
