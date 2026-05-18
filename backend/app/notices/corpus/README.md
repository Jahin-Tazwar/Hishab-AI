# Citation corpus markdown format

Each clause is a separate file: `{source}_{ref}_{language}.md` (lowercase,
underscores, no spaces). The seed script (`scripts/seed_citation_corpus.py`)
parses front-matter and body, embeds the title+body, and upserts a row in
`citation_corpus_chunks`.

## Required front-matter

````yaml
---
source: vat_act_2012   # one of: vat_act_2012 | vat_rules_2016 | sro | general_order
source_ref: Section 46 # e.g. "Section 46", "Rule 23", "SRO 134/2026"
subsection: ""         # e.g. "(2)(a)" or empty
language: en           # bn | en
title: Conditions for input tax credit
topic_tags: [itc, eligibility, documentary_evidence]
---
````

The body follows the closing `---` line and contains 4–10 lines of formal
statutory-style prose in the appropriate language. English bodies use Roman
numerals and `(a) (b) (c)` enumerators; Bangla bodies use Bangla numerals
(`১ ২ ৩`) and `(ক) (খ) (গ)` enumerators.

## File naming

- `vat_act_2012_s46_en.md` — Section 46, English
- `vat_act_2012_s46_bn.md` — Section 46, Bangla (ধারা ৪৬)
- `vat_rules_2016_r23_en.md` — Rule 23, English
- `vat_rules_2016_r23_bn.md` — Rule 23, Bangla (বিধি ২৩)

## Provenance — IMPORTANT

**The V1 seed is DRAFT text** capturing the substantive legal content of each
clause for retrieval purposes. It has NOT yet been audited against the
NBR-published official Bangla/English texts of the VAT and SD Act 2012 and
Rules 2016. A Bangladeshi CA must review and (where necessary) replace each
clause body with the verbatim official text before this corpus is used in
production drafts. See `corpus_review.md` for the per-chunk audit checklist.

## Re-seeding

```
cd backend && python -m scripts.seed_citation_corpus
```

The seeder is idempotent — it upserts on
`(source, source_ref, subsection, language)`. Editing a clause file and
re-running updates the row and its embedding in place.
