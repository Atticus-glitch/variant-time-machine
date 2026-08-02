# Methods

## Current Scientific Milestone

The current milestone is Temporal Validation and Error Analysis. Frozen V1 through V7 artifacts remain unchanged. The registry standardizes metrics, leakage audits, baselines, provenance, error-analysis rows, and known missing information.

## AI Temporal V7

V7 uses all 8,818 V2 development records, including previously opened V4-V6 tests.
Model selection compares four regularized logistic models and four shallow histogram
gradient-boosting models in five-fold connected-gene-group cross-validation. Rows are
weighted by the inverse square root of development group size. Logistic calibration and
the balanced-accuracy threshold are fit only to selected-model out-of-fold predictions.

The selected model scores every exact January 2024 germline VUS Variation ID absent
from the complete January 2022 snapshot. All 761,235 probabilities are persisted and
hashed before the July 2026 archive is downloaded. Safe answer matching requires exact
Variation ID, an unchanged nonempty Allele ID set, exclusively germline scope, and one
clear aggregate classification. A frozen hash selects exactly 1,000 eligible resolved
records without using probabilities or correctness.

V7 scored 78.5% accuracy, 79.1% balanced accuracy, 72.3% macro F1, and ROC AUC 0.885
(`TN 629, FP 176, FN 39, TP 156`). Development/test Variation ID overlap was zero;
same-gene overlap was 69.9%.

## AI Holdout V6

V6 retains V5's 14 older-only features, scaling, training-only class balancing, network
shape, and 0.5 threshold, but it is a separately trained model with a new frozen
partition. Complete V4/V5 test-connected groups are excluded from all V6 use. A
label-independent SHA-256 rule selects 1,000 additional connected groups and one test
representative per group; companions are quarantined. Only records in remaining fresh
groups enter training.

The resulting split contains 2,518 training records, 1,000 test records, 4,672
quarantined companions, and 628 prior-test-group exclusions. Recorded train/test ID and
connected-group intersections are zero. V6 scored 75.6% accuracy, 74.4% balanced
accuracy, and 72.9% macro F1 (`TN 535, FP 154, FN 90, TP 221`). The larger test is still
internal to the outcome-selected V2 cohort.

## AI Holdout V5

V5 retains the eleven older clue states and adds numeric classification age in days, maximum older submitter count, and missing-core-field count. A `StandardScaler` is fit only on training records. Training-only deterministic oversampling balances pathogenic and benign outcomes before fitting a neural network with hidden layers of 32 and 16 units.

The fresh holdout excludes every V4 test group. To reduce quarantine while preserving gene isolation, candidate test groups contain at most two records. A frozen label-independent SHA-256 rule selects 100 groups and one test record from each; any companion record is quarantined. All other records are available for V5 training.

V5 was designed after seeing V4 aggregate performance, so its architecture addresses the documented class-recall weakness. Its test was opened once after training: accuracy was 82.0%, balanced accuracy was 82.2%, and macro F1 was 80.9%. No architecture, feature, balancing, threshold, or partition decision may now be changed and presented as the same V5.

## Model Registry And Audits

`scripts/build_model_registry.py` reads existing artifacts without training. It writes one record per version, a combined index, standardized V4-V7 evaluations, deterministic baselines, leakage audits, reconstructed logs, comparison files, and error-analysis tables. Historical gaps remain `unknown/not recorded`. Reconstructed logs are explicitly labeled and never presented as original runtime logs.

## AI Holdout V4

V4 supplies all eleven older-only clue `applied` indicators to an `MLPClassifier` with one eight-unit hidden layer. During supervised training, cross-entropy loss penalizes incorrect probability estimates and backpropagation adjusts learned weights. Hand-selected clue points, V1/V2 scores, previous predictions, newer fields, and outcomes are never model inputs.

The partition is label-independent. A frozen SHA-256 salt ranks connected older-gene groups, selects 100 groups, and chooses one deterministic test record from each. Every other record in a selected group is quarantined, so no connected gene group can appear in both training and test data. All remaining groups train the model. Training uses an internal training-only validation fraction for early stopping.

Training writes the model and partition manifest but does not calculate hidden-test metrics. The Prediction Results page exposes a separately approved action that evaluates exactly those 100 records once, saves accuracy and balanced accuracy, and refuses a second evaluation. This protects the “unseen by the model” boundary but cannot make the already inspected 2022-to-2024 cohort independent temporal validation.

## Statistical Model V3

Version 3 uses logistic regression with fixed regularization, balanced class weights, and a 0.5 decision threshold. Its only model inputs are nine binary indicators reconstructed from older `clues_json`: five molecular-consequence indicators, expert-panel review, multiple agreeing submitters, criteria without conflict, and conflict warning. Assigned points, total score, prior predictions, confidence, newer fields, and outcome fields are prohibited as model inputs.

Partition assignment does not inspect outcome labels. Older gene symbols are normalized into tokens; records sharing any token form a connected component. A frozen salt and SHA-256 assign each complete component to approximately 80% training or 20% test. Records without a usable gene symbol group by Variation ID. Training and test IDs, group keys, source/config hashes, model coefficients, and package version are saved for audit.

The model, feature handling, regularization, class weighting, and threshold were fixed before held-out evaluation. Existing output is not overwritten by default. The frozen model trained on 6,933 records and was evaluated on 1,885 records with no shared Variation IDs or connected gene groups. It achieved 58.2% accuracy, 70.6% balanced accuracy, and 0.788 ROC AUC. Because aggregate Version 2 outcomes were already inspected before Version 3 was designed, this split is a disciplined internal holdout rather than independent temporal validation.

## Resolved Direction V2

Version 2 reuses the permanently frozen Version 1 points, so newer fields still cannot alter the score. The later snapshot is used to select a conditional cohort: exact older VUS, exact Variation ID, equal nonempty Allele ID sets, exclusively germline scope, and a newer normalized outcome of pathogenic direction or benign direction. Records that remained uncertain, conflicted, had unusable classifications, or failed safe matching are excluded.

The binary conversion was frozen before calculating Version 2 metrics: scores of +1 or higher predict pathogenic direction, scores of -1 or lower predict benign direction, and score zero receives no prediction. `remain_uncertain` is forbidden. This answers “which direction among variants known to have resolved?” It does not answer “will this VUS resolve?”

Version 2 was designed after inspecting Version 1 aggregate results and uses the same 2024 answer snapshot. Its reported performance is exploratory and not independent validation.

## Clue Score V1

Eligibility requires an aggregate classification exactly equal to `Uncertain significance` in the January 6, 2022 `variant_summary` snapshot. The prediction function receives an explicit whitelist of older fields only: Variation and Allele IDs, variant type, name/HGVS, gene, older classification and `LastEvaluated`, review status, submitter-count text, conditions, coordinates, guideline label, origin scope, and older release date. Automated tests reject declared scoring fields containing newer, outcome, answer-key, actual, or 2024 names. Changing newer classification, review, submitter, or date values cannot change a stored prediction.

`config/clue_score_v1.yaml` is JSON-compatible YAML and is read without an additional parser dependency. The file is frozen and content-addressed by SHA-256. Provisional points were selected before the complete outcome evaluation: frameshift/stop +4, canonical splice +3, missense +1, synonymous -3, weak noncoding -1, expert panel +2, multiple agreeing submitters +1, and criteria without conflict +1. Conflict, classification age, and completeness are warnings or explanatory zero-point clues. Consequence rules use conservative older HGVS text because archived `variant_summary` has no modern consequence annotation field.

Scores of +3 or higher predict pathogenic direction, -2 or lower benign direction, and -1 through +2 remaining uncertain. A record with no nonzero clue receives no prediction. Confidence uses older evidence amount and quality, not score magnitude alone.

The runner has two committed stages. First it queries only older rows, calculates every score, and commits all predictions. Only afterward does it query newer rows, verify exact Variation ID and equal nonempty Allele ID sets plus exclusively germline scope, normalize the newer answer, and compare directions. This ordering prevents the answer key from entering scoring.

Newer classifications map only through strict categories. Exact pathogenic/likely-pathogenic combinations, benign/likely-benign combinations, and exact uncertain significance are scorable. Conflict, protective, risk factor, drug response, association, somatic, oncogenic, mixed, missing, and unrecognized values remain unscorable. No-prediction and unscorable records are not counted automatically as wrong.

Accuracy is `correct / (correct + wrong)`. Balanced accuracy is mean recall across pathogenic, benign, and uncertain normalized outcomes. Directional precision is the correct fraction among scorable predictions in that direction. The uncertain metric is recall among actual still-uncertain records. All metrics come from stored real results.

## Historical Time Separation

The planned study asks what could have been predicted at an earlier date. The older release therefore defines the information cutoff, and the newer release supplies outcomes. This separation is necessary because a random split of current records would not recreate the historical question. It could mix evidence from the same scientific period into both training and testing.

## Preventing Future Information Leakage

Future information leakage occurs when a predictor contains information that was not available at the prediction date. Examples include a later review status, a newer submitter count, or a current annotation added after the older snapshot. Leakage can make a weak method look accurate. For this reason, newer fields are retained only to check outcomes and matches. Any future predictor will need a documented source and availability date no later than the older release.

## Active VCV Version-History Pilot

The original XML pilot considered official VCV releases dated 2024-02-01 and 2025-02-06. Their compressed sizes total about 7.89 GB. That full-archive strategy remains paused because streaming can still consume the complete transfer.

The dashboard's Version History Explorer is the normal workflow. Its optional ESearch/ESummary helper finds at most five current candidates through individual current requests. History uses EFetch instead: an unversioned VCV request establishes the latest official version, followed by exact `.version` requests in `all`, custom inclusive-range, or endpoint mode. Strict canonical VCV validation and exact returned-version checks prevent a different record or version from being accepted silently.

## Transfer Protection

Planning is local and does not contact NCBI. Every operation shows its official source, purpose, request count, maximum transfer, and storage estimate before explicit approval. The initial latest-version request does not count toward the maximum 25 historical requests. Historical EFetch requests are individual, sequential, and paced by 0.34 seconds; they use a 10-second connect timeout, a 30-second read timeout, and two limited retries for connect/read failures and selected transient HTTP statuses.

Each response has a 10 MiB hard cap (approximately 10 MB), and the complete exploration has a 50 MiB hard cap. Cancellation is observed between requests, not during the active request. Only official NCBI endpoints are used, only one dashboard exploration runs at once, and no archive action is exposed.

Partial or complete results with received historical data are saved under the ignored `data/manual_review/vcv_history/<VCV>/` tree. Individual JSON and XML replacements are bounded and atomic, symlinks are refused, and readers use the same lock as writers so they do not observe an in-progress refresh. An interrupted process can still leave a mixed generation across files, so manifests and source records must be checked during review.

## Automatic Parsing and Comparison

Each EFetch record preserves accession/version, Variation ID, record type, genes, name, HGVS expressions, record dates, conditions, record status, replacement/deletion metadata, and warnings. Germline, somatic clinical impact, and oncogenicity are parsed into separate classification blocks; each block has independent classification, review status, last-evaluated date, and submission count where supplied.

Only `available` versions are compared, sorted by version. The comparison skips unavailable holes and warns when the two available versions are not numerically consecutive. Automatic germline change labels are:

- `No_Classification_Change`
- `VUS_to_Pathogenic`, `VUS_to_Likely_Pathogenic`, `VUS_to_Benign`, `VUS_to_Likely_Benign`
- `Pathogenic_to_VUS`, `Benign_to_VUS`
- `Became_Conflicting`, `Conflict_Resolved`, `Other_Germline_Change`
- `Non_Germline_Change`, `Missing_Classification`

`Non_Germline_Change` means the normalized germline classification was unchanged but a somatic or oncogenicity block differed. The timeline also reports review-status values, whether known germline submission counts changed, warnings, and `high` or `limited` confidence. `Unable_to_Compare` and `unable` confidence are declared schema values but are not currently emitted by this comparison path. These are automatic labels, not manually verified scientific outcomes.

## Manual Pilot Review

Version histories begin `unreviewed` and can become `needs_review`, `ambiguous`, `manually_verified`, or `excluded`. Ambiguous and excluded histories require notes. `manually_verified` requires all ten checks: VCV identity, Variation ID, gene, classification type, old/new versions, relevant dates, official source requests, manually checked classification change, documented missing/conflicting information, and acknowledgement that versions are not monthly snapshots.

Reviewer decisions, notes, sources, verification flags, and manual corrections are stored only in `review.json`. Manual corrections are annotations and never mutate `metadata.json`, `versions.json`, `comparisons.json`, `manifest.json`, or raw XML. This separation keeps automatic extraction reproducible and human interpretation auditable.

The manifest and review store the same SHA-256 digest of the automatic evidence. If a
refresh changes that evidence, a previously verified case returns to `needs_review`
with all checks false. Human notes, sources, and corrections remain preserved.

## Parsing

The parser reads CSV, TSV, or compressed TSV input and selects ClinVar fields by header name rather than column position. It creates a standardized table while preserving Variation ID, Allele ID, assembly, genomic representation, classification text, review status, submitter count, RCV accessions, and phenotype text. Missing values remain missing. Classification text is not simplified during parsing.

## Why Matching Is the First Scientific Challenge

A wrong cross-release match creates a wrong outcome label. Later modeling cannot repair that error. The same allele can appear on more than one genome assembly, identifiers can participate in complex records, and records may be merged, replaced, deleted, or remapped. Conditions and aggregate classifications can also change independently of the underlying DNA allele.

The current matcher:

1. Limits the older group to exact supported VUS terms.
2. Combines duplicate rows with the same Allele ID and Variation ID.
3. Prefers an exact Allele ID and Variation ID pair.
4. Allows a unique Allele ID candidate with a changed Variation ID but labels that rule separately.
5. Refuses to choose among multiple candidates or conflicting identifiers.
6. Detects a numeric Variation ID linked to multiple Allele IDs and keeps it as one unsupported complex record.
7. Requires the older release date to be earlier than the newer release date.
8. Does not use coordinates, genes, rs numbers, phenotypes, or RCV accessions as sole keys.

## Outcome Mapping

Only exact later classification terms map to directional outcomes. `Pathogenic`, `Likely pathogenic`, `Benign`, `Likely benign`, and supported VUS terms each receive their stated labels. Explicit conflict text becomes `VUS_to_Conflicting`. A still-uncertain record becomes `VUS_to_Still_Uncertain`. Missing, unfamiliar, ambiguous, or unreliable information becomes `Unable_to_Verify`.

This conservative rule avoids pretending that a mixed aggregate has one clear direction. It may place some usable records into an ambiguous group, which is acceptable until manual review supports a more detailed rule.

For the XML pilot, germline, somatic clinical impact, and oncogenicity are separate columns. Only exact Variation IDs are compared automatically. Germline values can be labeled unchanged, changed, or unable to verify. Missing records, non-current statuses, and replacement metadata are flagged. Every automatic result remains `requires_manual_review`.

## Validation Before Scale

The included CSV is synthetic test data and is not a ClinVar extract. It tests parsing, matching, missing data, output labels, and command-line formatting. Before full-release processing, a small real sample from every match category must be checked against the archived records and, when necessary, VCV or RCV history.

One real three-version history, `VCV000014026`, has been retrieved and automatically compared. All three aggregate germline classifications were `Pathogenic`; review status and submission counts changed, but no germline classification change was detected. The case remains `needs_review` with zero completed verification checks. The next validation step is to build and manually verify approximately 10–25 genuine histories, preserving unsuccessful, ambiguous, deleted/replaced, missing, and parsing-failure cases. Only then will the project evaluate whether VCV history is sufficient or whether archived monthly summaries/releases are required.
