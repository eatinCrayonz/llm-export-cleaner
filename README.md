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

The desktop app uses a terminal-style layout of numbered panels: **1 ·
library** (stats), **2 · imports**, a `/` search line, **3 ·
conversations**, and **4 · profile**, where cleaning rules are toggled
live and take effect immediately.

1. Select the provider and import its JSON export (panel 2).
2. Toggle cleaning rules or switch profiles (panel 4).
3. Search or browse retained conversations; excluded rows appear dimmed
   with their filter reason when **show excluded** is on.
4. Export the complete cleaned corpus, only the latest import's changes,
   or just the selected rows.

Keyboard: `i` import · `e` export · `/` search · `p` profile · `x` show
excluded · `h` history. Changing the provider dropdown re-runs the
current search or browse immediately. The conversation table supports extended
selection: `Ctrl+click` toggles rows, `Shift+click` selects ranges, and
`Ctrl+A` selects every currently displayed row. **export selected…**
writes only those conversations, in their visible table order, using
the active cleaning profile.

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
selected profile's included corpus; **show excluded** reveals excluded
conversations and their reasons.

## Recovering Project names and membership

Consumer exports do not consistently include human-readable Project names.
The cleaner therefore accepts small JSON responses copied from the provider's
own signed-in web application. This is manual, local, and requires no API key,
Enterprise account, console script, or browser extension.

### Browser Network workflow

1. Open the provider's normal web application while signed in.
2. Press **F12** to open Developer Tools.
3. Select **Network**.
4. Select the **Fetch/XHR** request category.
5. Enable **Preserve log** if navigating or scrolling will change pages.
6. Reload the page so its requests appear.
7. Use the Network filter box to find the request described below.
8. Click the request, open its **Response** tab, select all of the JSON, and
   copy it. In browsers that offer it, right-clicking the request and choosing
   **Copy > Copy response** is equivalent.
9. In LLM Export Cleaner, click **Claude Project page...**, paste the response,
   and click **Import page**.

Do not paste JavaScript into the browser console. The browser warning about
pasting code is irrelevant to this workflow because only response JSON is being
copied out of Developer Tools and into the local cleaner.

### Claude Project names

On the main Claude page, filter Network requests for `projects_v2`. The active
Project catalog request has this recognizable form:

```text
projects_v2?limit=30&offset=0&filter=is_creator&order_by=updated_at&searchQuery=&is_archived=false
```

Claude may also issue an `is_archived=true` request. Use the
`is_archived=false` response for active Projects. Its JSON contains a `data`
array with records shaped like:

```json
{
  "uuid": "019d98e6-bc5d-73eb-9115-9e23d585f538",
  "name": "Mr Thinker"
}
```

The cleaner stores this as the Project UUID-to-name lookup. Confirm that
`pagination.has_more` is `false`; otherwise copy and import each subsequent
offset page as well.

### Claude conversation-to-Project membership

Open a Claude Project and filter Network requests for `conversations_v2`.
Scroll the conversation list until it finishes loading, copying each paginated
response. Import each response through **Claude Project page...**. The cleaner
uses each conversation's `uuid` and `project_uuid`; it ignores summaries,
settings, permissions, and other website metadata.

The two Claude response types solve separate halves of the lookup:

```text
projects_v2       Project UUID -> Project name
conversations_v2  Conversation UUID -> Project UUID
```

### ChatGPT Projects

ChatGPT exports commonly provide Project membership as `gizmo_id` values such
as `g-p-...`, but not Project names. With the ChatGPT sidebar visible, use the
same Network workflow and filter for this request:

```text
GET /backend-api/gizmos/snorlax/sidebar
```

Copy its response JSON and paste it into **ChatGPT Projects...**. The observed
response nests the lookup at:

```text
items[].gizmo.gizmo.id
items[].gizmo.gizmo.display.name
```

Some versions may omit one `gizmo` wrapper; the importer accepts both shapes.
If the response has a non-null `cursor`, capture and import subsequent cursor
pages. The app reports how many Project IDs matched the imported ChatGPT export
and how many remain unnamed.

These copied responses can contain account identifiers and other private
metadata. Do not publish them. The cleaner extracts only the identifiers and
names needed for local Project matching.

## Clean exports

Plain text, Markdown, JSON, and JSONL outputs contain only the documented canonical fields.
Plain text is the default for human or LLM reading: it omits merge-only IDs and
constant branch flags while retaining conversation boundaries, provider, date,
Project name, speaker roles, timestamps, and text. Delimiter-like lines inside
messages are prefixed with a backslash so conversation boundaries remain
unambiguous. Markdown remains available as an equivalent transcript extension;
JSON/JSONL remain available for structured pipelines. Every
output receives a companion `*-manifest.json` with source sizes, import count,
profile, export mode, conversation/message counts, and output bytes.

Cleaning profiles can optionally remove fenced code generated by assistants.
The surrounding explanation and conversation remain, code-only turns become
`[Generated code removed]`, inline code remains, and user messages are not
modified. The original code stays in SQLite, so this output choice is fully
reversible.

See [the canonical schema](docs/canonical-schema.md) and
[Windows application instructions](docs/windows-application.md).

## Development

```powershell
python -m unittest discover -s tests -v
python -m llm_export_cleaner.cli --help
```
