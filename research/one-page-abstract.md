# Variant Time Machine: One-Page Abstract

## Question and Significance

ClinVar records aggregate interpretations of genetic variants, including variants of uncertain significance (VUS), and these classifications can change as submitted evidence changes. Variant Time Machine asks a narrow historical question: among records that were VUS in an earlier snapshot and are known to have a clear later aggregate outcome, can information available at the earlier date predict whether the later classification moves toward benign or pathogenic? Direction matters as a research target because raw accuracy can hide failure on the less common pathogenic-direction class, and because directional errors can reveal where historical features or matching rules need scrutiny. The task does not predict whether a VUS will resolve and does not determine clinical pathogenicity.

## Data and Methods

The project uses official NCBI ClinVar archived `variant_summary` releases. Development used January 6, 2022 predictors and January 4, 2024 answers; V7 and V8 used January 2024 predictors and July 2026 answers. Records were conservatively matched by Variation and Allele IDs, restricted to germline scope, and included only when the later aggregate classification had one safe, clear benign- or pathogenic-direction outcome. Thus, evaluation is conditional on an outcome-selected resolved subset.

Leakage prevention was central. Predictors were limited to fields available in the earlier snapshot; Variation ID, gene identity, absolute coordinate, condition identity, newer fields, earlier model predictions, and prior correctness were forbidden as model inputs. V8 excluded every candidate predictor-time gene component touching the 9,818-record development ledger and every V7 test ID. Its preregistered logistic regression (`C=1`, `l1_ratio=0`) and threshold (0.315), together with 378,552 eligible candidate predictions, were committed before the label vault was opened. The final 1,000-record test covered 559 components and had zero development/test Variation ID overlap, zero development/test gene-component overlap, and zero V7-test-ID overlap. A post-evaluation protocol audit passed all recorded checks.

## Results

The V8 test contained 814 benign-direction and 186 pathogenic-direction outcomes. V8 recorded 89.5% accuracy, 87.1212% balanced accuracy, 84.0371% macro F1, 90.91% benign recall, 83.33% pathogenic recall, ROC AUC 0.94594, average precision 0.83895, and Brier score 0.06332. Its confusion matrix was `TN 740, FP 74, FN 31, TP 155`, for 895 correct and 105 wrong predictions. The same-record majority-benign baseline recorded 81.4% accuracy, 50% balanced accuracy, and 0% pathogenic recall.

Frozen V7 predictions were also scored on these 1,000 records. V7 recorded 86.6688% balanced accuracy, compared with 87.1212% for V8, a difference of +0.4524 percentage points. The 95% paired component-bootstrap interval was -2.45 to +3.31 percentage points. Because it includes zero, the comparison does not establish that V8 improved on or outperformed V7. The preregistered 230-record missense comparison also had a paired interval crossing zero.

## Limitations and Next Step

V8 is a sealed gene-component-disjoint retrospective test, not prospective, external, independent, or clinical validation. The July 2026 archive had already been accessed for V7; V8 membership was hidden during development but is reconstructible from the published salt and archive. The 1,000 records are not 1,000 independent gene samples. Aggregate ClinVar classifications can combine conditions, submitters, and imperfect evidence. Component separation reduces one defined leakage risk but does not prove biological independence or broad generalization. In addition, fitting weights were not strictly equal in total per component, the simplicity tie-break did not rank regularization strengths within the selected family, and grouped out-of-fold labels were reused for selection, calibration, and threshold choice.

The immediate next step is structured manual review of V8 errors and calibration, especially high-confidence false predictions, missense records, noncoding false negatives, and V8/V7 disagreements. Any revised model should receive a new version and be evaluated on a genuinely later untouched snapshot. The project provides no diagnosis, medical advice, clinical utility claim, or basis for patient care.
