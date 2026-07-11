# Real Export Validation

Validation date: 2026-07-11. Raw exports and transcript text remained external
and are not committed.

| Provider | Raw bytes | Conversations seen | Conversations retained | Messages seen | Messages retained |
|---|---:|---:|---:|---:|---:|
| ChatGPT | 208,651,547 | 1,762 | 1,761 | 54,340 | 24,645 |
| Grok | 67,398,833 | 612 | 611 | 4,405 | 4,340 |
| Claude | 70,385,508 | 469 | 441 | 8,855 | 8,626 |

Combined results under the default profile:

- 2,813 canonical cleaned conversations;
- 37,611 retained messages;
- 1,770 included conversations;
- 1,043 reversibly filtered conversations;
- 55,806,295-byte included JSONL output from 346,435,888 source bytes;
- exact re-import of the ChatGPT source confirmed as a hash-based no-op;
- FTS search confirmed against the combined library;
- no normalization warnings.

The large ChatGPT message reduction primarily removes non-user/non-assistant
nodes and records without readable text. Exclusion counts remain available in
each import's audit ledger.
