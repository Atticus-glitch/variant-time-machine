# 2026-07-26 Research Notebook

## Project Setup

### Work Recorded

- Created the initial repository structure, Python package, documentation, validation script, and automated setup tests.
- Defined the initial research question: can only historically available information predict whether a ClinVar VUS later moves toward harmful, moves toward harmless, or remains uncertain?
- Deliberately did not download data, select releases, implement matching, or train models during setup.

### Initial Assumptions

- Archived ClinVar releases provide enough information to identify a meaningful set of variants classified as uncertain at an older date.
- At least one stable identifier or a carefully normalized genomic representation can support cross-release matching.
- Classification categories and review status will require explicit, version-aware definitions.
- The date on which each candidate feature became available can be determined well enough to avoid using future information.

### Next Actions

1. Choose two scientifically useful ClinVar release dates.
2. Compare available archive formats and fields, especially identifiers and classification dates.
3. Design and manually inspect a small proof-of-concept cross-release match.

### Unresolved Questions

- Which release interval provides enough reclassifications without making historical fields incomparable?
- Should classifications be analyzed at the variant, condition, or variant-condition level?
- Which ClinVar identifier remains most stable across the selected formats and dates?
- How should conflicting submissions, multiple conditions, withdrawn records, and merged records be labeled?
- What evidence proves that a feature was available by the older cutoff date?

## ClinVar Archive and Matcher Research

### Work Recorded

- Reviewed official NCBI documentation for ClinVar release cadence, archive formats, tab-delimited fields, and identifier relationships.
- Provisionally selected monthly `variant_summary` releases dated 2022-01-06 and 2024-01-04. No release files were downloaded.
- Implemented an identifier-only proof-of-concept matcher and tests using explicitly synthetic TSV fixtures.
- Required ambiguity, conflict, unsupported-complex-record, and unmatched outcomes to remain visible rather than forcing matches.

### Evidence and Assumptions

- Both selected files exist in official NCBI archive listings and are exactly two years apart.
- Both snapshots precede a documented 2024-01-29 `variant_summary` schema expansion for somatic classifications.
- `AlleleID + VariationID` is treated as the strongest key available in `variant_summary`, while neither identifier is assumed to be permanently simple or one-to-one.
- The selected interval is a starting choice until I examine the actual headers, class counts, missing values, and manually reviewed matches.

### Next Actions

1. Download the two selected files deliberately and record retrieval metadata and checksums.
2. Inspect headers and count exact historical VUS tokens without assigning model outcomes.
3. Run the matcher on a small real sample and manually audit exact, changed, ambiguous, conflicting, and unmatched cases.

### Unresolved Questions

- Should VUS subtiers (`VUS-high`, `VUS-mid`, and `VUS-low`) be included in the initial cohort?
- How often does `AlleleID` stay the same when `VariationID` changes, and what fraction requires XML record-history checks?
- What manually reviewed error rate is acceptable before full-release matching?
- Should the final study remain variant-level or move to condition-specific RCV records?

## 2026-07-26 Historical Pipeline Foundation

### Current Milestone

Produce a verified table connecting variants labeled uncertain in one archived ClinVar release with their classifications in a later release.

### What Was Attempted

- Wrote a focused ClinVar data plan for the selected 2022-01-06 and 2024-01-04 `variant_summary` files.
- Added an explicit downloader that records URL, release date, retrieval time, filename, size, and SHA-256 checksum. No large file was downloaded.
- Added a parser that converts ClinVar summary fields to a standardized table without deleting ambiguity fields.
- Added a conservative historical VUS matcher and a two-input command-line tool.
- Added clearly labeled synthetic data and tests for exact outcomes, conflicts, missing identifiers, missing later records, parsing, and CSV output.

### What Was Learned

- Release date and retrieval date are different facts and both must be recorded.
- Variation ID and Allele ID are useful together, but their relationship is not always one-to-one.
- An exact classification mapping is safer than guessing the direction of mixed ClinVar terms.
- Software tests can verify expected behavior, but they cannot verify whether the matching rules are accurate on real ClinVar history.

### Next Step

Download the two selected files only after checking storage and provenance settings. Then inspect their actual headers and run the pipeline on a small real sample. Manually review every match category before processing the full older VUS group.

## 2026-07-26 First Live ClinVar Connection

### Date

2026-07-26

### Milestone

Created first connection to real genetic data.

### What Was Attempted

- Connected to the official NCBI ClinVar E-utilities `esummary` JSON endpoint.
- Added a single-variant client that accepts a Variation ID or VCV accession.
- Added clear error categories for invalid input, missing records, network failure, and malformed responses.
- Added a command-line connection test and a local dashboard lookup page.
- Kept the request limited to one current record and downloaded no large database.

### What Was Learned

- A small official API request is enough to test real data connectivity and interface behavior.
- Current API data cannot answer the historical research question because it is not a fixed archived snapshot.
- ClinVar ESummary provides useful aggregate fields but not the complete evidence behind every submission.

### Next Step

Use several manually selected Variation IDs to check missing fields and classification formats. Keep these connectivity checks separate from the later archived-release matching dataset.

## 2026-07-26 First Historical Comparison Workflow

### Date

2026-07-26

### Milestone

Created first historical comparison workflow.

### What Worked

- Created a dedicated manual-review folder and a header-only CSV template.
- Defined seven conservative VUS outcome categories.
- Kept ambiguous, complex, missing, and unfamiliar cases as `Unable_to_Verify`.
- Added a review command that shows current ClinVar information and the fields that still need archived verification.
- Added dashboard counts that remain zero until complete source-backed rows exist.

### What Is Still Unknown

- Which first real variants will have clear records in both selected snapshots.
- How often identifiers changed because of merging, replacement, or complex variant sets.
- Whether condition-level differences will require RCV XML instead of variant-level summary data.
- How many manually reviewed examples are needed before full archive processing is justified.

### Why Historical Matching Is Difficult

A current record does not prove what ClinVar showed in 2022 or 2024. Identifiers, assemblies, condition groupings, review status, submissions, and aggregate classifications can all change. A wrong match would create a wrong outcome, so uncertainty must be kept instead of resolved by guessing.

### Next Step

Select one candidate Variation ID, inspect its current record with `scripts/review_variant.py`, and verify the same record independently in both selected archived releases. Add the row only after every checklist item and source reference is complete.

## 2026-07-26 Bounded Historical XML Pilot

### Date

2026-07-26

### What Was Attempted

- Checked the VM interpreter, disk, archive listings, file sizes, official MD5 files, XML family, and schema revisions.
- Selected VCV XML releases dated 2024-02-01 and 2025-02-06.
- Added a confirmation-gated incremental gzip and XML reader with record, transfer, and output limits.
- Retrieved current ESummary facts for 16 active low-numbered Variation IDs and left all historical fields blank.
- Added manifests, exact-ID comparison, missing-record states, record-history flags, and persistent manual review.
- Added a Historical Pilot dashboard page and mocked tests. No archive body was requested during development tests.

### Environment Finding

The active `.venv` uses Python 3.14.4. Python 3.12 and `uv` were not installed, and the configured Ubuntu 26.04 APT repositories did not list Python 3.12 packages. The existing environment was kept. The repository now documents a separate `.venv312` route, but migration is not confirmed.

### What Was Learned

- Streaming prevents large local archive storage but can still use several gigabytes of bandwidth.
- VCV schema 2.0 and 2.2 are in the same current family, but fields still need tolerant parsing and manual checks.
- Germline classification, somatic clinical impact, and oncogenicity must remain separate.
- An exact Variation ID is a useful pilot match, but record status, replacements, conditions, and aggregation can still change its meaning.
- Software tests can show safe failure behavior. They cannot certify a historical scientific match.

### What Is Still Unknown

- Whether all 16 requested records occur in both selected archives.
- How many compressed bytes an actual early-stopped scan will transfer.
- Whether the extracted XML field paths cover every real pilot record shape.
- Which automatic comparisons will pass human review.

### Next Step

This earlier next step was superseded by the small pilot decision below. The archive scan is paused; only metadata inspection remains available.

## 2026-07-26 Small Pilot Strategy

### Decision

The full archive approach was paused because the two selected compressed XML files
could transfer about 7.89 GB. Internet data use is limited and not measured reliably,
so that transfer is not justified for a five-record methods test.

### Changes

- Removed the command-line option that could start the XML archive body scan.
- Added a 500 MB large-download protection rule that shows source, estimated size,
  and purpose before requiring explicit confirmation.
- Replaced the populated candidate table with five empty manual pilot slots.
- Added `scripts/pilot_mode.py` for one-record ESummary requests and optional explicit
  VCV-version EFetch requests.
- Limited a historical VCV response to 10 MB and kept historical verification manual.
- Added transfer safety status to the dashboard.
- Compared XML, summary, VCF, API, and indexed-query options without downloading data
  files.

### Why This Is Better

The smaller pilot improves reproducibility because every selected record, request,
source, reason, and verification state can be inspected. It prevents unnecessary
downloads and tests the most error-prone parts of the method before scale. Empty
historical cells are scientifically preferable to values inferred from current data.

### Next Step

Choose the first real variant for a clear written reason. Run pilot mode without the
confirmation flag to inspect its transfer plan. Approve the small API request only
after checking the source and estimate, then manually investigate whether an explicit
historical VCV version can be dated and interpreted safely.

## 2026-07-26 First Pilot Variant Workflow

### Date

2026-07-26

### Milestone

First pilot variant workflow created.

### Work Recorded

- Added a preview-only selection tool for a Variation ID, VCV accession, or gene.
- Added a declared JSON format for one selected pilot variant.
- Added an interactive workflow that confirms the API request and confirms selection
  separately before saving.
- Added a Current Pilot Variant dashboard section and an empty timeline state.
- Left historical records empty and manual verification pending.

### Why One Example Is Useful

One carefully checked example can reveal identifier problems, missing fields, unclear
condition scope, source-recording mistakes, and dashboard errors before those problems
are repeated across many variants. It tests whether the full path is understandable
and reproducible.

### Why This Is Not a Result

Selecting and displaying one current ClinVar record does not show that its
classification changed. It cannot estimate a reclassification rate or support a
biological conclusion. Historical evidence has not been verified, and the variant may
not represent other ClinVar records.

### Why Manual Verification Comes First

Automation can quickly repeat a wrong identifier match or misunderstand a versioned
record. A person must first confirm the identifier, classification type, condition
scope, source, and historical date. The rules should be automated only after this
single example passes the manual checklist.

### Next Step

Preview several reasonable candidates without saving them. Choose one for a written,
method-based reason. Run the workflow, confirm the current record, and then investigate
one official low-bandwidth historical source while keeping unverified fields empty.

## 2026-07-26 Browser Pilot Workspace

### Date

2026-07-26

### Milestone

The dashboard became the main pilot research interface.

### Work Recorded

- Added a browser Pilot Workspace for planning and approving small current ClinVar
  lookups.
- Added browser controls for adding unique pilot variants, saving reasons and notes,
  filtering records, opening review, and updating current metadata.
- Added manual older and newer dates, exact classification categories, source links,
  classification type, verification notes, and ambiguity notes.
- Added `unreviewed`, `reviewing`, `verified`, `ambiguous`, and `excluded` states.
- Required all checklist items and source-backed historical fields before a record can
  be marked verified.
- Added a simple timeline that leaves missing history missing.
- Added measured API response bytes and kept 500 MB large-download protection active.
- Added validated local JSON storage with a backup and atomic replacement.
- Kept command-line tools as optional reproducibility and developer tools.

### Scientific Boundary

A successful current lookup is still only current information. Adding it to the pilot
does not show a classification change. A record marked verified means a person
completed this project's source, date, identifier, category, and ambiguity checklist;
it does not make ClinVar an error-free ground truth.

The pilot list is not representative, contains too few records for modeling, and is
not suitable for machine learning. No full ClinVar archive route or browser control
was added.

### Next Step

Use the browser to select the first real pilot variant for a written method-based
reason. Record one official low-bandwidth historical source, verify its date and
classification type, complete the checklist, and inspect the resulting timeline. Then
repeat the exact same manual process on a few more records before automating any rule.

## 2026-07-27 Bounded VCV Version History Implementation

### Date

2026-07-27

### Implementation Recorded

- Added the Version History Explorer as the dashboard startup target and normal pilot workflow.
- Kept current candidate discovery separate: gene ESearch returns at most five identifiers and ESummary retrieves each current candidate individually.
- Added strict canonical VCV validation, an unversioned EFetch lookup for the latest official accession version, and exact `.version` requests in all, custom inclusive-range, or endpoint mode.
- Limited each plan to 25 historical requests after the current lookup, each response to 10 MiB (approximately 10 MB), and each exploration to 50 MiB.
- Used official NCBI endpoints only, 0.34-second sequential pacing, 10-second connect and 30-second read timeouts, two limited retries, and cancellation checks between requests.
- Parsed record identity, genes, HGVS, dates, conditions, status/replacement fields, warnings, and separate germline, somatic clinical impact, and oncogenicity blocks.
- Added automatic consecutive-available-version comparison labels while preserving holes and warnings.
- Saved raw XML, parsed versions, comparisons, metadata, and provenance below the ignored `data/manual_review/vcv_history/<VCV>/` tree.
- Kept reviewer decisions, notes, sources, manual corrections, and the ten-item verification checklist in a separate `review.json`; manual edits do not overwrite automatic artifacts.

### Scientific Boundary

The first live dashboard demonstration used `VCV000014026` (Variation ID 14026;
TACR3). The current request returned `VCV000014026.3` in 27,828 bytes. The approved
history plan then requested versions 1, 2, and 3 separately. All three were available
and transferred 16,806, 23,508, and 27,828 bytes. Total current-plus-history response
bytes were 95,970.

All three parsed aggregate germline classifications were `Pathogenic`, so the
comparison correctly reported `No_Classification_Change` for both transitions. The
aggregate review status changed from `no assertion criteria provided` in version 1,
to `criteria provided, single submitter` in version 2, to `criteria provided, multiple
submitters, no conflicts` in version 3. Aggregate submission counts were 2, 3, and 4.
No parser warnings remained after correcting aggregate classification scope to avoid
using condition-specific RCV classifications.

This is a real multi-version timeline, but it is not manually verified and does not
show that the variant was formerly a VUS. The review checklist remains unchecked. The
implementation and automatic comparison can establish what the parser detected, not
that the method is scientifically sufficient.

VCV history is useful because it can expose exact changes to one aggregate record
without a multi-gigabyte archive transfer. It is not a monthly snapshot series and
cannot by itself prove what all of ClinVar showed at an arbitrary date. Archived
monthly summaries or releases may eventually still be needed.

### Environment Finding

The system is Ubuntu 26.04 LTS. `python3.12` is not installed, the existing `.venv`
uses Python 3.14.4, and migration was not successful. The documented recovery uses a
reviewed user-level `uv` installer and a separate `.venv312`; no privileged commands
were run.

### Next Milestone

Build and manually verify a pilot set of approximately 10–25 genuine VCV histories, then evaluate whether this version-history method is sufficient for selecting and validating the first historical examples.

## 2026-07-27 First Real Pilot Result

### Method

The candidate rule was fixed before historical retrieval. The sample included the
existing `VCV000014026` case and the two lowest qualifying Variation IDs from the
previously identified canonical multi-version germline candidates: `VCV000000002`
and `VCV000000005`. The dashboard plan reused one history and approved at most six
new sequential EFetch requests with a 62,914,560-byte maximum.

### Actual Result

- Three candidates were attempted and all three were retrieved.
- Seven official versions were included.
- `VCV000000002` changed from `Pathogenic` at version 1 to
  `Pathogenic/Likely pathogenic` at version 5. It was labeled
  `Other_Germline_Change` with limited confidence because versions 2–4 were not
  sampled.
- `VCV000000005` remained `Pathogenic` between sampled versions 1 and 11.
- `VCV000014026` remained `Pathogenic` across versions 1, 2, and 3.
- One history had an automatic germline change, two were unchanged, and zero were
  unable to compare.
- All three histories require review and have zero completed verification checks.

Candidate screening used 113,027 response bytes. The saved history evidence contains
244,705 response bytes, including 148,735 bytes from the newly approved batch and
95,970 bytes from the reused history. Total measured pilot response-body transfer was
357,732 bytes. No full archive was downloaded.

### Boundary And Next Step

This is a real descriptive pilot result, not evidence that future reclassification can
be predicted. It is too small, non-random, partly endpoint-sampled, and unverified for
model training or clinical use. Manually verify all three histories, then expand to
approximately 25–50 suitable histories before deciding whether model development is
justified.

## 2026-07-28 Clue Score V1 Full Baseline

### Frozen Method

Version 1 was frozen before complete outcome evaluation. The prediction stage used
only January 6, 2022 fields and committed every score before the runner queried the
January 4, 2024 answer key. A deterministic 500-record development sample was checked
first. Ten correct, ten wrong, ten no-prediction/unsafe, and ten unscorable examples
had arithmetic and labels consistent with the rules. No weights were changed after
that inspection.

### Actual Full Result

- Eligible exact older VUS records: 439,409
- Predictions made: 421,578
- Formula no-predictions: 17,831
- Correct directional comparisons: 298,090
- Wrong directional comparisons: 70,053
- Not scorable: 65,175
- Accuracy among correct/wrong records: 81.0%
- Balanced accuracy: 47.5%
- Pathogenic-direction precision: 1.3%
- Benign-direction precision: 16.1%
- Uncertain-outcome recall: 80.8%
- Full runtime: 336.54 seconds
- Final indexed result database: 1,891,164,160 bytes
- Output bundle: 3,448,775,132 bytes

### Interpretation

The 81.0% raw accuracy is dominated by variants that remained uncertain. Balanced
accuracy and directional precision show that this provisional formula is weak at the
more useful pathogenic and benign directions. This is an honest baseline result, not
a medical model. Version 1 remains unchanged; future work must use a separately named
Version 2 and an independent validation design.

## 2026-07-29 Resolved Direction V2

### Revised Question

The main view now excludes records that remained uncertain. Resolved Direction V2
keeps only safely matched variants that were exactly VUS in the 2022 snapshot and had
a clear pathogenic or benign normalized outcome in the 2024 snapshot. It asks which
direction a known resolution took, not whether resolution occurred.

### Frozen Binary Rule

Version 2 reuses the unchanged Version 1 score calculated from 2022 fields. Scores of
+1 or higher predict pathogenic direction, -1 or lower predict benign direction, and
zero receives no prediction. Remaining uncertain is not an allowed prediction.

### Actual Result

- Resolved directional records: 8,818
- Actual pathogenic outcomes: 2,531
- Actual benign outcomes: 6,287
- Predictions made: 7,859
- Correct: 4,595
- Wrong: 3,264
- No prediction: 959
- Accuracy: 58.5%
- Balanced accuracy: 65.1%
- Pathogenic precision: 42.7%
- Benign precision: 99.1%
- Pathogenic recall: 95.5%
- Benign recall: 34.6%
- Final rerun runtime: 133.71 seconds

### Boundary

The later snapshot is used to select this resolved cohort, although it never changes
the older-only score. Version 2 was designed after Version 1 aggregate results were
known and uses the same answer snapshot. These metrics are exploratory and are not an
independent validation or a medical prediction result.

## 2026-07-29 Statistical Model V3 Frozen Design

Version 3 stops assigning clue points by hand. It fits a logistic regression using
only nine binary older-snapshot clue indicators. Points, scores, prior predictions,
newer fields, and outcome fields are forbidden model inputs.

Before held-out evaluation, the feature list, estimator, 0.5 threshold, balanced class
weights, source database hash, split salt, and 80/20 rule were frozen in
`config/statistical_model_v3.yaml`. Records linked through any older gene token remain
in one connected group, and SHA-256 assigns complete groups without inspecting labels.

The test partition is an internal holdout, not independent validation. Version 2
aggregate outcomes were already visible and both partitions use the same 2022-to-2024
conditional resolved cohort. A genuinely later untouched answer snapshot is still
needed for independent temporal validation.

## 2026-07-30 Statistical Model V3 Held-Out Result

The frozen design trained on 6,933 records and evaluated once on 1,885 held-out
records. The partitions shared zero Variation IDs and zero connected gene groups. The
source database hash remained unchanged after evaluation.

- Accuracy: 58.2%
- Balanced accuracy: 70.6%
- Pathogenic precision: 35.8%
- Benign precision: 96.3%
- Pathogenic recall: 94.2%
- Benign recall: 47.0%
- ROC AUC: 0.788
- Pathogenic average precision: 0.546
- Brier score: 0.171

The held-out result will not be used to retune Version 3. High pathogenic recall came
with low pathogenic precision, and benign recall remained below 50%. A later untouched
snapshot is still required before making any independent validation claim.

## 2026-07-31 AI Holdout V4 Frozen Design

The hand-scored V2 predictor and completed V3 experiment remain unchanged. V4 is a
small supervised neural network using the binary applied state of all eleven
older-only hints. Training loss penalizes wrong probability estimates and
backpropagation adjusts model weights; this is supervised learning, not reinforcement
learning or human-like reward.

A frozen label-independent SHA-256 rule selects 100 connected older-gene groups and
one hidden test record from each. Companion records from selected groups are
quarantined, and all other groups are available for training. Training saves the model
without calculating test accuracy. The dashboard requires separate approval to open
the hidden 100 once and then displays the saved accuracy.

The source cohort is still conditional on clear resolution by 2024 and its aggregate
outcomes were already inspected. The 100 records are unseen by the fitted model but do
not constitute independent temporal or clinical validation.

## 2026-07-31 AI Holdout V4 Trained, Test Unopened

The frozen neural network trained on 8,325 records for 23 iterations. Exactly 100
records remain in the hidden test, 393 related-gene companions are quarantined, and
train and test share zero connected gene groups. The model uses all eleven older-only
hint indicators.

Training completed with a final loss of 0.4197. No hidden-test metrics or predictions
exist yet. The dashboard now provides the separate approved action that will evaluate
the fixed model once on the 100 unseen records and save its accuracy.

## 2026-08-01 AI Holdout V4 Result

V4 correctly classified 76 of 100 records, but the class-specific result was weak. It
classified all 68 benign outcomes correctly and only 8 of 32 pathogenic outcomes.
Ordinary accuracy was 76.0%; balanced accuracy was 62.5%. The result is preserved and
V4 will not be retrained from its hidden answers.

## 2026-08-01 AI Holdout V5 Frozen Design

V5 was specified after the V4 aggregate result. It adds numeric age, submitter-count,
and missing-field inputs; training-only class balancing; feature scaling; and hidden
layers of 32 and 16 units. A fresh 100-record holdout excludes every V4 test group and
uses only connected groups containing at most two records, reducing quarantine and
making more unique records available for training.

All V5 choices are frozen before training and testing. The new hidden answers cannot
be used to change the network, features, balancing, threshold, or partition. V5 remains
an internal conditional experiment, and its result must be reported even if it is
worse than V4.

## 2026-08-01 AI Holdout V5 Trained, Test Unopened

V5 trained on 8,683 unique records. Deterministic training-only oversampling produced
12,396 class-balanced rows. The larger network ran for 172 iterations with final loss
0.4311. It uses 14 older-only inputs.

Exactly 100 fresh records remain hidden and only 35 companion records were
quarantined. Train and test share zero connected groups, and V4 and V5 share zero test
groups. No V5 test metrics or hidden predictions exist yet. The website now provides
the separately approved one-time V5 evaluation.

## 2026-08-01 V5 Result And Model Registry

The saved V5 test contains 100 records: 82 correct and 18 wrong. Accuracy was 82.0%,
balanced accuracy was 82.2%, and macro F1 was 80.9%. The confusion matrix was 53 true
benign, 12 false pathogenic, 6 false benign, and 29 true pathogenic. This result does
not alter the earlier training note; it records the later one-time evaluation.

The project now has evidence-backed V1-V5 registry records, standardized evaluations,
deterministic baselines, name-based leakage audits, reconstructed run logs, error
analysis, and planning milestones. All five declared feature lists passed the current
audit, but source-date review remains required. V3's original source database hash is
not available, and V4/V5 freeze timestamps occur after their recorded training times;
both provenance problems are retained as warnings. No stable winner is claimed because
V4 and V5 used different internal tests of only 100 records each.

## 2026-08-01 V6 1,000-Record Test

Expanding V5 directly was not valid because its training set already contained nearly
all remaining V2 records, including every V4 test record. I froze V6 instead. It kept
the V5 feature design but selected 1,000 new connected-group representatives before
training, quarantined 4,672 companions, excluded 628 records in prior test groups, and
trained on the remaining 2,518 records. All recorded ID/group overlap checks are zero.

V6 scored 75.6% accuracy, 74.4% balanced accuracy, and 72.9% macro F1. The confusion
matrix was `TN 535, FP 154, FN 90, TP 221`. The result did not reproduce V5's 82.2%
balanced accuracy, which is useful evidence against overreading the small test. V5 has
the higher point estimate on its own cohort; V6 has the larger internal test. Neither
creates a stable winner, and the next stronger question requires a later untouched
cohort rather than another rearrangement of V2.

## 2026-08-02 V7 Sealed Temporal Test

V6 error analysis showed that the strict group split had left only 2,518 training
records and that missense variants caused 214 of 244 errors. Reusing V6's opened answers
as a final V7 test would not have been honest, so V7 moved both dates forward.

Before downloading the July 2026 answer, V7 used grouped development cross-validation
on all 8,818 older records, selected shallow histogram gradient boosting, calibrated
from out-of-fold predictions, and sealed 761,235 predictions for January 2024 VUS IDs
absent from January 2022. The sealed prediction hash was recorded first. The fixed July
2026 archive was then downloaded and hashed, and 1,000 safe clear outcomes were selected
by the frozen hash rule.

V7 scored 78.5% accuracy, 79.1% balanced accuracy, and ROC AUC 0.885, with `TN 629, FP
176, FN 39, TP 156`. Test ID overlap with development was zero. Same-gene overlap was
69.9%, so the result is temporal at the record level rather than gene-independent.
Missense still caused 186 of 215 errors. The strongest result did not come from retrying
the old test; it came from preserving the boundary and waiting for a later answer.
