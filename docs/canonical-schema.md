# Canonical Clean Schema

The cleaner retains only fields with a direct preservation, search, incremental
merge, branching, Project, or export purpose.

## Conversation

- `provider`
- `conversation_id`
- `title`
- `created_at`
- `updated_at`
- `project_id`
- `active_leaf_message_id`
- `messages`

## Message

- `message_id`
- `parent_message_id`
- `role`
- `text`
- `created_at`
- `is_active_path`
- `is_alternative`
- optional `attachment_count`

User and assistant text is mandatory. Account objects, provider settings,
feature flags, model UI state, internal tool records, and empty content are not
part of the clean schema.

Filtering never mutates this representation. A saved profile creates a separate
included/excluded decision with explicit reasons.

