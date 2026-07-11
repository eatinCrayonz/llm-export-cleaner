# LLM Export Cleaner

A local Windows application that removes unnecessary provider metadata from
ChatGPT, Claude, and Grok exports, incrementally maintains a minimal cleaned
library, filters obvious low-value conversations using visible saved rules,
searches cleaned text, and exports portable JSON or JSONL.

It contains no model calls, semantic scoring, cognitive analysis, or cloud
service. Raw exports remain external; the cleaned SQLite library is stored at:

```text
%LOCALAPPDATA%\LLM Export Cleaner\cleaner.sqlite3
```

## Desktop workflow

1. Select the provider and import its JSON export.
2. Edit or select a cleaning profile.
3. Search or browse retained conversations.
4. Export either the complete current cleaned corpus or only the latest import's
   new and changed conversations.

The default profile excludes single-exchange conversations and requires two user
turns, while preserving short Project conversations. Filtering is reversible:
the canonical cleaned record remains in the database with explicit exclusion
reasons.

## Incremental imports

Every source file is hashed. Exact re-imports are no-ops. Overlapping exports
merge by provider conversation and message IDs; only new or genuinely changed
records are rewritten and re-filtered. Absence from a later export never deletes
an older conversation.

## Search

SQLite FTS5 indexes titles plus user and assistant text. Search defaults to the
selected profile's included corpus; **Include filtered-out** reveals excluded
conversations and their reasons.

## Clean exports

JSON and JSONL outputs contain only the documented canonical fields. Every
output receives a companion `*-manifest.json` with source sizes, import count,
profile, export mode, conversation/message counts, and output bytes.

See [the canonical schema](docs/canonical-schema.md) and
[Windows application instructions](docs/windows-application.md).

## Development

```powershell
python -m unittest discover -s tests -v
python -m llm_export_cleaner.cli --help
```

