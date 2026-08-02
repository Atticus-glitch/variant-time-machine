# MIT Activity Draft

## Activity Name

Independent computational genetics research: Variant Time Machine

## Role

Student researcher and software developer

## Short Description

Built a historical ClinVar pipeline to test whether 2022 information predicts the
direction of VUS classifications by 2024. Designed leakage controls, baselines,
group-disjoint holdouts, model comparisons, and a local results dashboard. Reported
negative and mixed findings, not only the best score.

## Longer Draft

I started Variant Time Machine to study how genetic variants labeled uncertain can
change as evidence develops. I built Python tools to retrieve and compare ClinVar
records, document provenance, preserve ambiguous matches, and prevent 2024 information
from entering 2022 predictors. I tested a hand-written clue score, logistic regression,
and two small neural networks.

The most important lesson was that a headline number can be misleading. V4 reached
76% accuracy on 100 records but only 62.5% balanced accuracy; its confusion matrix was
TN 68, FP 0, FN 24, TP 8. V5 reached 82% accuracy and 82.1978% balanced accuracy on a
different 100 records. I then froze V6 around 1,000 test records before training. V6
excluded every test-connected group from fitting and reached 75.6% accuracy and 74.4%
balanced accuracy. The larger, more modest result was more useful than another polished
small score.

For V7, I moved the dates forward instead of retrying V6. I sealed 761,235 January 2024
predictions before downloading July 2026 outcomes. On 1,000 new Variation IDs, V7
reached 79.1% balanced accuracy and 80% pathogenic recall. The remaining errors were
mostly missense variants, which turned a result into the next research question.

I then preregistered V8 and excluded every test gene component touching development.
On 1,000 records in 559 components, it reached 87.1212% balanced accuracy. Frozen V7
reached 86.6688% on the same records; the +0.4524-point difference had a bootstrap
interval from -2.45 to +3.31 points, so I reported no overall superiority. The test was
retrospective and its hidden membership reconstructible, limitations I preserved with
the result.

I kept dated notes, frozen designs, limitations, and failed approaches. I paused a
multi-gigabyte data route when it was not justified and used bounded official requests
before scaling. My next step is structured V8 error and calibration review, followed by a
genuinely later untouched cohort rather than another rearrangement of the same data.

This is an internal historical research project using a conditional 2022-to-2024
cohort. It is not independent or medical validation, does not predict whether a VUS
will resolve, and should not guide care.

## Details to Fill In Before Submission

- Weekly hours: [enter actual average]
- Weeks per year: [enter actual count]
- Grades or dates of participation: [enter exact range]
- Mentor or organization: [enter only if applicable]
- Link: [include only after access and public visibility are verified]

Do not convert planned work, repository configuration, or a local dashboard into a
claim of publication, deployment, mentorship, or public impact.
