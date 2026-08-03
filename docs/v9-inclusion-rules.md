# V9 Dataset Inclusion Rules

## Clean Reviewed Inclusion

A record can enter `v9_clean_reviewed_dataset.csv` only when:

- The predictor-time record is an older VUS under the strict project normalization.
- The later automatic or explicitly corrected outcome is clearly benign-direction or
  pathogenic-direction.
- The frozen match used the same biological variant with high match confidence.
- Condition and classification scope are sufficiently comparable for this task.
- The classification is germline or clearly within project scope.
- Required identity fields are present.
- No serious automatic flag remains unresolved.
- A reviewer selects `match_correct_model_wrong` or `match_correct_model_right`,
  explicitly includes the record in the clean dataset, and does not exclude it.
- Only predictor-time fields are model features.

## Clean Reviewed Exclusion

A record stays outside the clean reviewed dataset when:

- The match is bad or uncertain.
- Condition or classification scope changed too much.
- The later aggregate classification is conflicting or unusable.
- The record is non-germline or outside project scope.
- An old or new label is missing.
- Required identity fields are missing.
- A reviewer marks it as needing expert review.
- A severe automatic flag remains unresolved.
- Manual review is still pending.

Pending review is not a scientific exclusion. The exclusion ledger distinguishes
`manual_review_pending` from an explicit data-quality or scope exclusion.

## Label And Evidence Preservation

The messy dataset always retains the original automatic outcome. A corrected outcome
is a separate field and is used by the clean dataset only after explicit review. V8
predictions, labels, metrics, and source artifacts are never rewritten.

Excluded and expert-needed records remain in their own output tables with reasons.
Difficulty or model error alone is not a valid exclusion reason.

## Anti-Cherry-Picking Reporting

Any future V9 evaluation must report all-record, clean-reviewed, and excluded or
ambiguous performance where labels permit. It must show exclusion percentage, excluded
false positives and false negatives, class distributions before and after cleaning,
and whether cleaning disproportionately removes one V8 error type.

> Clean-dataset performance is not directly comparable to messy all-record performance
> if many hard or ambiguous records were excluded.
