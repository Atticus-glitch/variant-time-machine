# V8 AI-Assisted Error Review

## Status

I used OpenCode GPT-5.6 to check all 105 frozen V8 errors against the committed January
2024 predictor evidence and the exact archived July 2026 answer rows. I stored the AI's
suggestions in `outputs/manual_review/v8_ai_review_suggestions.json`.

I am treating this as AI-assisted triage, not human genetics-expert review. Every
suggestion has `requires_human_confirmation: true`. I did not change the authoritative
manual ledger, the completed-human-review count remains zero, and these suggestions
cannot unlock final V9 training.

## Results

| Suggested disposition | FP | FN | Total |
| --- | ---: | ---: | ---: |
| Likely genuine V8 model error | 70 | 26 | 96 |
| Ambiguous condition scope | 4 | 4 | 8 |
| Needs expert provenance review | 0 | 1 | 1 |
| Total | 74 | 31 | 105 |

The archived-data checks passed for all 105 records:

- The January 2024 and July 2026 Allele-ID sets matched.
- July rows were exclusively germline under `OriginSimple`.
- July rows had one clear aggregate directional classification.

For 96 records, I found that an old RCV or meaningful condition scope persisted into
July 2026. I marked those records as likely genuine V8 errors because the frozen match,
task scope, and automatic outcome remain supported. This is still a dataset-review
judgment, not a clinical interpretation or an explanation of why ClinVar changed.

## Ambiguous Or Expert-Needed Records

I do not think the following records should enter the clean V9 dataset without human
confirmation:

| Variation ID | Gene | V8 error | AI suggestion | Reason |
| --- | --- | --- | --- | --- |
| 1676545 | GRIA1 | FN | ambiguous condition scope | Old generic RCV disappeared; later named disorder scope differs. |
| 2443957 | ACACA | FN | needs expert review | New disease-specific RCV and no-assertion-criteria provenance require source review. |
| 2573382 | LAMB3 | FN | ambiguous condition scope | Old generic RCV disappeared and new scopes were added. |
| 2137670 | SLC12A1 | FN | ambiguous condition scope | Generic RCV persisted while named Bartter scopes were added. |
| 1910224 | HTRA1 | FN | ambiguous condition scope | Generic RCV persisted while several disease scopes were added. |
| 1378717 | ASXL2 | FP | ambiguous condition scope | Generic old scope plus an added broad disease RCV. |
| 2192947 | FGD1 | FP | ambiguous condition scope | Generic old scope plus an added broad disease RCV. |
| 1347398 | LEPR | FP | ambiguous condition scope | Generic RCV persisted while a named LEPR scope was added. |
| 1401295 | ASXL2 | FP | ambiguous condition scope | Generic old scope plus an added broad disease RCV. |

I made this rule intentionally conservative. A human reviewer may determine that some
persisting RCVs provide sufficient continuity, but that decision should cite the exact
archived evidence instead of relying only on the variation-level aggregate.

## Independent Spot Check

I ran a separate AI-assisted archived-data spot check on twelve high-confidence
likely-error suggestions: six FN and six FP. This was not human or expert review. Every
sampled record kept the same Variation ID, Allele ID, germline scope, clear later label,
and an old RCV. SPAG1 and GP1BA had comparatively stronger later review status. Most of
the other sampled records relied on single-submitter evidence, so I am keeping them as
medium-confidence dataset-review suggestions.

## Limitations

- RCV continuity may still hide changes in submitter composition or assertion detail.
- Many aggregate rows use `not provided` or `not specified` condition text.
- VCV accessions were not retained in the frozen V8 artifacts.
- The review compares archived aggregate records, not patients or clinical truth.
- AI review cannot replace a qualified human reviewer for genetics, condition scope, or
  clinical interpretation.

## Next Step

My next step is to use the AI suggestions only to prioritize human review. The work still
requires confirmation of the 96 likely errors, resolution of the eight scope-ambiguous
records, and expert review for ACACA Variation 2443957. I will not copy these suggestions
into the manual ledger without checking the linked source evidence and recording a human
reviewer, confidence, and note.
