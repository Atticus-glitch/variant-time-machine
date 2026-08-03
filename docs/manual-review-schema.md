# V8 Manual Review Schema

## Purpose

This schema supports the manual-review stage between frozen V8 and any future V9.
It separates genuine model mistakes from questionable matches, ambiguous aggregate
labels, condition-scope changes, missing fields, and records that need expert review.
It does not alter V8, make a clinical claim, or treat a computer suggestion as truth.

The machine-readable definition is `config/manual_review_schema.yaml`.

## Immutable And Manual Values

Every saved review retains the original automatic fields and stores all reviewer
decisions separately. A corrected outcome is an annotation used only by a new derived
dataset. It never replaces the frozen V8 label or prediction.

Each review contains:

- Review provenance: `review_id`, `reviewed_at`, `reviewer`, and `model_version`.
- Identity: Variation ID, VCV accession when recorded, Allele ID when recorded, gene,
  match method, and match confidence.
- Timeline: old/new snapshot dates, original classification text, normalized outcomes,
  condition text, and review status.
- Frozen model evidence: V8 prediction, probability, confidence, correctness, V7
  prediction on the same record, old consequence fields, and V8 feature values.
- Audit context: official source links and automatic warning flags.
- Flag adjudication: `cleared_automatic_flags` records suggestions explicitly resolved
  by the reviewer; the note must explain the supporting evidence.
- Manual values: decision, error category, V9 inclusion/exclusion booleans, label
  correction, corrected outcome, note, and reviewer confidence.

Unavailable fields are stored as `not recorded`; they are not inferred from unrelated
identifiers. Predictor-time fields rejoined from the committed January 2024 index are
explicitly marked by provenance. Later-snapshot fields absent from the frozen V8
artifacts remain unavailable.

## Manual Decisions

- `not_reviewed`
- `match_correct_model_wrong`
- `match_correct_model_right`
- `ambiguous_condition_scope`
- `ambiguous_aggregation`
- `bad_match`
- `possible_label_problem`
- `conflicting_classification_scope`
- `missing_critical_fields`
- `exclude_non_germline_or_wrong_scope`
- `duplicate_or_related_record_problem`
- `uncertain_manual_review`
- `needs_expert_review`

## Manual Error Categories

- `genuine_model_error`
- `false_positive_pathogenic_direction`
- `false_negative_pathogenic_direction`
- `condition_scope_changed`
- `aggregate_label_ambiguous`
- `poor_match`
- `missing_features`
- `misleading_consequence`
- `weak_old_evidence`
- `review_status_shift`
- `gene_or_component_generalization_failure`
- `label_noise`
- `non_germline_scope`
- `unknown`

Reviewer confidence is `high`, `medium`, or `low`.

Each saved review also carries a monotonically increasing `revision`. A stale editor
cannot overwrite a newer revision, and superseded versions remain in review history.

## Required Notes

A non-empty note is required for `bad_match`, `possible_label_problem`,
`uncertain_manual_review`, `needs_expert_review`, any corrected outcome, or any record
excluded from the V9 clean dataset. Notes should state the scientific or data-quality
reason; difficulty alone is not an exclusion reason.

## V9 Inclusion Meaning

`include_in_v9_messy_dataset` records the reviewer recommendation, but cannot silently
remove the original row from the mandatory all-record audit table.
`include_in_v9_clean_dataset` means the reviewer considers identity, scope, and
label sufficiently clear under the documented V9 rules. `exclude_from_v9_clean_dataset`
requires a reason and does not hide the row: it remains in the review ledger and
excluded-record report.

No final V9 model is valid until the minimum review gate in
`research/v9-model-selection-plan.md` is satisfied.
