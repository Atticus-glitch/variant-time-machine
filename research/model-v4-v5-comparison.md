# Model V4, V5, and V6 Comparison

## Question

Do the frozen neural-network experiments show that one model is clearly better at
predicting whether a variant that resolved by 2024 moved toward a benign or pathogenic
classification?

## Results

Pathogenic is treated as the positive class in both confusion matrices.

| Model | Test records | Benign / pathogenic | Accuracy | Balanced accuracy | Benign recall | Pathogenic recall | TN | FP | FN | TP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| V4 | 100 | 68 / 32 | 76.0% | 62.5% | 100.0% | 25.0% | 68 | 0 | 24 | 8 |
| V5 | 100 | 65 / 35 | 82.0% | 82.2% | 81.5% | 82.9% | 53 | 12 | 6 | 29 |
| V6 | 1,000 | 689 / 311 | 75.6% | 74.4% | 77.6% | 71.1% | 535 | 154 | 90 | 221 |

V4's accuracy looked promising until the confusion matrix showed that it found only 8
of 32 pathogenic outcomes. V5's own test had much more balanced errors. That result
raised the next question: would the pattern survive a test ten times larger? V6 found
221 of 311 pathogenic outcomes and 535 of 689 benign outcomes. Its result was stronger
than chance and majority baselines, but more modest than V5's 100-record point estimate.

## Design Differences

V4 used 11 older-only hint indicators in one hidden layer. V5 retained those hint
states, added numeric classification age, maximum submitter count, and missing-field
information, scaled features using training data, balanced classes within training,
and used hidden layers of 32 and 16 units. V5 was designed after the aggregate V4
result was known.

V6 kept the V5 feature set and network shape but created a new partition and retrained
from scratch. Before fitting, it excluded complete V4/V5 test groups, selected one
representative from each of 1,000 new connected groups without using labels, and
quarantined every companion in those groups. This left 2,518 training records, 4,672
quarantined companions, and 628 prior-test-group records excluded from all V6 use.
Recorded overlap checks are zero for train/test Variation IDs, train/test connected
groups, V6 training versus prior test groups, and V6 testing versus prior test groups.

All three test sets contain distinct connected groups. They are not the same model
scored on the same records, and V6 necessarily trained on fewer records after reserving
the larger test. Raw score differences are therefore descriptive, not estimated model
improvements.

## Interpretation

V5 has the highest point balanced accuracy on its own test. V6 has the largest test and
the clearest uncertainty estimate: its 75.6% accuracy has a 95% Wilson interval from
72.8% to 78.2%. The larger experiment did not reproduce V5's 82.2% balanced accuracy;
it estimated 74.4%. That does not prove V5 is worse or V6 is better. It shows why the
small result needed a larger challenge before becoming a headline.

Both results are internal tests from a conditional cohort: records were uncertain in
the January 6, 2022 ClinVar snapshot and were selected because they had a clear benign
or pathogenic aggregate outcome in the January 4, 2024 snapshot. The experiments do
not predict whether a variant will resolve. They are not independent temporal,
clinical, or medical validation and must not be used for patient decisions.

## Baselines And Audits

V6 exceeded its majority baseline (68.9% accuracy, 50.0% balanced accuracy) and seeded
stratified baseline (59.0%, 52.2%). The V2 clue baseline reached 76.1% balanced accuracy
on 865 of the 1,000 V6 rows, but abstained on 13.5%. Coverage differences prevent a
simple V2-versus-neural winner claim. The generated comparison table reports each
baseline only on the test cohort where it was calculated.

V4, V5, and V6 pass the current declared-feature leakage audit. The audit is
name-and-lineage based and still recommends source-date review. Their configuration
freeze timestamps occur after their recorded training timestamps, which weakens the
freeze chronology and is preserved as a registry warning.

## Error Pattern

V4's dominant error was over-predicting benign: 24 pathogenic outcomes were called
benign. Its strength was perfect benign recall in this test, but that came with only
25% pathogenic recall. V5 reduced false-benign errors to six and reached 82.9%
pathogenic recall, while introducing 12 false-pathogenic errors. V5 therefore improved
class balance at the cost of losing V4's perfect benign recall.

V6 made 154 false-pathogenic and 90 false-benign predictions. Its 71.1% pathogenic
recall is far above V4's own-test recall but below V5's own-test recall. Those are error
patterns on different cohorts, not paired gains. No stable winner is declared.

> V6's 1,000 records were not in V6 training, but all three evaluations remain internal
> to the outcome-selected 2022-to-2024 cohort. Larger is more informative, not magically
> independent.

## Next Evidence Needed

Manually review a structured sample of V6 errors, inspect calibration, and precommit
any changed model as a new version. The next major evaluation should use a genuinely
later untouched ClinVar snapshot or an external cohort whose IDs and connected groups
were absent from training. That would answer a stronger question than another random
split of the same resolved cohort.
