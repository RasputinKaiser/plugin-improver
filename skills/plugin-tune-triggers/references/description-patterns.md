# Description patterns for skill triggering

The `description` is the ONLY signal the router sees before deciding to load a skill. Optimize it like an API contract, not ad copy.

## Anatomy of a strong description

```
<Verb phrase: what it does, on what> <WHEN: "Use when..." with verbatim
trigger phrases users say>. <Optional: coverage nouns that aid matching>.
<NOT clause: nearest sibling or lookalike task it must NOT claim>.
```

## Before / after examples

**Too vague — never fires or misfires**

- Before: `Helps with database stuff.`
- After: `Write and optimize PostgreSQL queries and migrations. Use when asked to write SQL, speed up a slow query, design a schema, or create a migration. Not for MongoDB or application-level ORM configuration.`

**Marketing copy — router can't match words users say**

- Before: `Your one-stop shop for world-class deployment excellence!`
- After: `Deploy this repo to staging or production. Use when asked to deploy, ship, roll out, or roll back a release. Not for local dev servers.`

**Collision pair — both claim "review"**

- Before A: `Review code changes.` / Before B: `Review pull requests.`
- After A: `Review uncommitted local changes for bugs and style before commit. Not for opened pull requests.`
- After B: `Review an opened GitHub pull request and post review comments. Not for uncommitted local changes.`

**Missing negative scope**

- Before: `Work with PDF files.`
- After: `Extract text and tables from PDFs and fill PDF forms. Use when a .pdf file is the input or output. Not for Word documents or scanned-image OCR quality restoration.`

## Anti-patterns

- First person ("I can help you...") — routers match capabilities, not chat.
- Trigger words only in the body — the body is not loaded at routing time.
- Restating the skill name and nothing else.
- Lists of 15 trigger synonyms — 3 or 4 that users actually say beat 15 generic ones.
- Growing past ~400 chars — every char is paid in every session's context.

## Test matrix template

| # | Prompt | Expected skill | Passes before | Passes after |
|---|--------|----------------|---------------|--------------|
| S1–S5 | should-trigger prompts | this skill | | |
| N1–N5 | near-miss prompts | sibling / none | | |

Store the matrix in the target plugin at `.plugin-improver/trigger-matrix.md` so future passes rerun it.

## Opting out of implicit invocation

`skills/<name>/agents/openai.yaml`:

```yaml
policy:
  allow_implicit_invocation: false
```

Use for destructive operations, expensive workflows, or skills with unavoidably generic descriptions. Explicit `$skill` invocation still works.
