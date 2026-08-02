# Model V4 Through V7 Comparison

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
| V7 | 1,000 | 805 / 195 | 78.5% | 79.1% | 78.1% | 80.0% | 629 | 176 | 39 | 156 |

V4's accuracy looked promising until the confusion matrix showed that it found only 8
of 32 pathogenic outcomes. V5's own test had much more balanced errors. That result
raised the next question: would the pattern survive a test ten times larger? V6 found
221 of 311 pathogenic outcomes and 535 of 689 benign outcomes. Its result was stronger
than chance and majority baselines, but more modest than V5's 100-record point estimate.

V7 moved the prediction date to January 2024 and the answer date to July 2026. It
detected 156 of 195 pathogenic-direction outcomes. Unlike V4-V6, every V7 prediction
was sealed before the answer archive was downloaded, and all 1,000 test Variation IDs
were absent from development.

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

V7 used all 8,818 earlier development records, including opened V4-V6 records, because
none of those Variation IDs could enter the new temporal cohort. Five-fold grouped
development selection chose shallow histogram gradient boosting. Calibration and the
decision threshold used only out-of-fold development predictions. V7 then scored
761,235 eligible January 2024 candidates before any July 2026 answer was read.

The V4-V6 test sets contain distinct connected groups. They are not the same model
scored on the same records, and V6 necessarily trained on fewer records after reserving
the larger test. Raw score differences are therefore descriptive, not estimated model
improvements.

V7 is different again: it is record-level temporal validation, not a fourth internal
split. Its test IDs are new, but 69.9% share at least one gene with development. It is
therefore stronger evidence about later records, not gene-independent validation.

## Interpretation

V5 has the highest point balanced accuracy on its own test. V6 has the largest test and
the clearest uncertainty estimate: its 75.6% accuracy has a 95% Wilson interval from
72.8% to 78.2%. The larger experiment did not reproduce V5's 82.2% balanced accuracy;
it estimated 74.4%. That does not prove V5 is worse or V6 is better. It shows why the
small result needed a larger challenge before becoming a headline.

V7 reached 79.1% balanced accuracy and ROC AUC 0.885 on its temporal test. Its 78.5%
raw accuracy was lower than the 80.5% majority-benign baseline, but that baseline had
0% pathogenic recall and 50% balanced accuracy. V7's evidence is stronger because of
the date boundary and sealed predictions, not because every displayed number is larger.

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

On V7, the majority baseline scored 80.5% raw accuracy and 50% balanced accuracy. The
seeded stratified baseline scored 67.6% and 48.4%. No V2 same-record baseline exists
because V7 test IDs were absent from the old V2 cohort.

V4 through V7 pass the current declared-feature leakage audit. The audit is
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

V7 made 176 false-pathogenic and 39 false-benign predictions. Missense variants
accounted for 186 of all 215 errors. The clearest research target is therefore better
older-only missense evidence, not a threshold chosen after seeing the temporal test.

> V7 is temporal at the record level, but not gene-independent or clinical validation.
> All comparisons remain conditional on records that later reached a clear outcome.

## Next Evidence Needed

Manually review a structured sample of V7 missense errors and inspect the middle-range
calibration. Any changed model needs a new version and another future sealed answer
snapshot; the July 2026 answers cannot become both tuning data and V7 validation.
