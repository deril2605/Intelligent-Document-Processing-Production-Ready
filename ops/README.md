# Ops Folder

This folder contains operational assets to keep analyzer and database rollout repeatable.

## Structure

- `ops/analyzers/<document_type>/`
  - `schema.json`: analyzer contract for that document type
  - `create_analyzer.py`: create/upsert analyzer from schema
  - `update_analyzer.py`: update analyzer using same schema flow
- `ops/db/reviewed_tables/`
  - one SQL file per reviewed output table
- `ops/db/migrations/`
  - ordered SQL migration scripts

## Recommended Rollout for a New Document Type

1. Add analyzer schema under `ops/analyzers/<document_type>/schema.json`.
2. Run create/update script for the analyzer.
3. Add reviewed table SQL under `ops/db/reviewed_tables/`.
4. Add/extend migration scripts under `ops/db/migrations/`.
5. Update app config mapping (`document_type -> analyzer_id -> reviewed_table`) when introduced.
