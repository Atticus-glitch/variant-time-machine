# V9 Mentor Summary

V8 tested 1,000 historical records. Its result table contains 740 true negatives, 74
false positives, 31 false negatives, and 155 true positives. That means 105 predictions
were wrong. None of those 105 records has completed the new structured manual review,
so it would be premature to train or announce a final V9.

The next step is review, not a new score. The original source values, labels, and V8
predictions will stay unchanged. A reviewer will record identity, classification scope,
later label, predictor-date information, consequence context, conflicts, sources, and
notes in a separate record. Any proposed correction will also stay separate. If a
correction is accepted, it can be used only in a new dataset version with a link back to
the original and the review.

Before fitting official V9 candidates, the project requires all 31 false negatives and
all 6 high-confidence false positives to be reviewed, plus at least 25 true negatives
and 25 true positives. All 119 V8/V7 disagreements must remain accounted for, and every
exclusion reason must be reported. The current completed-review count is 0.

After review, the project will freeze the cleaned dataset and keep connected gene
groups together during development. It will compare elastic-net logistic regression,
calibrated histogram gradient boosting, tree ensembles, clue-score, consequence-only,
majority, and frozen V8 baselines. Selection uses balanced accuracy, macro F1,
pathogenic recall, calibration, stability, interpretability, and simplicity.

A final test remains off limits during cleaning, feature work, and model selection. One
pipeline and all final-test predictions must be frozen and hashed before final labels
are opened. The final cohort must be later and must not overlap development or earlier
opened tests by Variation ID or connected gene group. If those conditions cannot be
met, there will be no valid V9 final result.

At present the builder produces a 1,000-row messy table and a zero-row clean reviewed
table; all 1,000 records are transparently listed as review-pending. There is no
selected V9 model, V9 prediction file, or valid final V9. V8 remains the latest
completed evaluation. This work studies historical aggregate records and model
behavior; it does not provide patient-level interpretation or medical advice.
