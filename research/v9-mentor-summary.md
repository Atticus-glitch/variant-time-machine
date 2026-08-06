# V9 Mentor Summary

I tested V8 on 1,000 historical records. The result table contains 740 true negatives,
74 false positives, 31 false negatives, and 155 true positives. That means 105
predictions were wrong. None of those 105 records has completed the new structured
manual review, so I cannot responsibly train or announce a final V9 yet.

My next step is review, not a new score. I will keep the original source values, labels,
and V8 predictions unchanged. A reviewer will record identity, classification scope,
later label, predictor-date information, consequence context, conflicts, sources, and
notes in a separate record. I will also keep any proposed correction separate. If a
correction is accepted, I can use it only in a new dataset version that links back to the
original and the review.

Before I fit official V9 candidates, all 31 false negatives and all 6 high-confidence
false positives must be reviewed, along with at least 25 true negatives and 25 true
positives. I must keep all 119 V8/V7 disagreements accounted for and report every
exclusion reason. The current completed-review count is 0.

After review, I will freeze the cleaned dataset and keep connected gene groups together
during development. I plan to compare elastic-net logistic regression, calibrated
histogram gradient boosting, tree ensembles, clue-score, consequence-only, majority,
and frozen V8 baselines. I will use balanced accuracy, macro F1, pathogenic recall,
calibration, stability, interpretability, and simplicity for selection.

I will keep the final test off limits during cleaning, feature work, and model selection.
One pipeline and all final-test predictions must be frozen and hashed before I open the
final labels. The final cohort must be later and must not overlap development or earlier
opened tests by Variation ID or connected gene group. If I cannot meet those conditions,
there will be no valid V9 final result.

Right now, my builder produces a 1,000-row messy table and a zero-row clean reviewed
table. It transparently lists all 1,000 records as review-pending. There is no selected
V9 model, V9 prediction file, or valid final V9. V8 remains my latest completed
evaluation. This work studies historical aggregate records and model behavior; it does
not provide patient-level interpretation or medical advice.
