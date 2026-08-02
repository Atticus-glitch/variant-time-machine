# V8 Error Analysis

## Error Total

V8 was wrong on 105 of 1,000 sealed test records: 74 false positives and 31 false negatives. A false positive means V8 predicted movement toward pathogenic when the later aggregate classification moved toward benign. A false negative means V8 predicted movement toward benign when the later aggregate classification moved toward pathogenic. V8 predicts the pathogenic direction at `P(pathogenic) >= 0.315`. Confidence is the recorded probability assigned to the recorded predicted direction: `P(pathogenic)` for a pathogenic-direction prediction and `1 - P(pathogenic)` for a benign-direction prediction, not the maximum of those probabilities. All 105 error rows remain `unreviewed`; VCV accession, review status, and match confidence are `not recorded`, and warning flags are blank. These absences are review needs, not evidence that a record is safe or erroneous.

## Highest-Confidence Wrong Records

The review queue defines high-confidence wrong as a wrong prediction with confidence at least 0.8. Exactly 19 records meet that rule, listed below in queue order.

| Order | Variation ID | Gene | Error | Actual direction | Predicted direction | Confidence | Consequence | Suggested category |
| ---: | --- | --- | --- | --- | --- | ---: | --- | --- |
| 1 | 1676545 | GRIA1 | FN | pathogenic | benign | 0.9989 | missense | predicted benign but later pathogenic |
| 2 | 1338214 | GP1BA | FP | benign | pathogenic | 0.9951 | loss of function | predicted pathogenic but later benign |
| 3 | 1804720 | CFHR4 | FP | benign | pathogenic | 0.9369 | canonical splice | predicted pathogenic but later benign |
| 4 | 2151981 | DVL3 | FP | benign | pathogenic | 0.9332 | loss of function | predicted pathogenic but later benign |
| 5 | 1508577 | SLC24A5 | FN | pathogenic | benign | 0.9294 | noncoding | predicted benign but later pathogenic |
| 6 | 2635421 | TBR1 | FN | pathogenic | benign | 0.9205 | noncoding | predicted benign but later pathogenic |
| 7 | 2179139 | SPAG1 | FN | pathogenic | benign | 0.9204 | noncoding | predicted benign but later pathogenic |
| 8 | 1917357 | PTH | FN | pathogenic | benign | 0.9157 | noncoding | predicted benign but later pathogenic |
| 9 | 2125741 | EXOC6B | FN | pathogenic | benign | 0.9144 | noncoding | predicted benign but later pathogenic |
| 10 | 1510471 | FECH | FN | pathogenic | benign | 0.9098 | noncoding | predicted benign but later pathogenic |
| 11 | 1481314 | GLI2 | FP | benign | pathogenic | 0.8707 | missense | predicted pathogenic but later benign |
| 12 | 1518918 | DEAF1 | FN | pathogenic | benign | 0.8669 | missense | predicted benign but later pathogenic |
| 13 | 1516358 | SERPINF1 | FN | pathogenic | benign | 0.8446 | missense | predicted benign but later pathogenic |
| 14 | 1444570 | HMCN1 | FP | benign | pathogenic | 0.8400 | canonical splice | predicted pathogenic but later benign |
| 15 | 2184261 | TSEN54 | FP | benign | pathogenic | 0.8271 | missense | predicted pathogenic but later benign |
| 16 | 2443383 | KATNIP | FN | pathogenic | benign | 0.8210 | missense | predicted benign but later pathogenic |
| 17 | 2443957 | ACACA | FN | pathogenic | benign | 0.8157 | missense | predicted benign but later pathogenic |
| 18 | 2573382 | LAMB3 | FN | pathogenic | benign | 0.8151 | missense | predicted benign but later pathogenic |
| 19 | 1993961 | MTFMT | FN | pathogenic | benign | 0.8119 | missense | predicted benign but later pathogenic |

## Suggested Categories: Unverified Counts

The `suggested_category` field is a deterministic triage suggestion, not a reviewed explanation or verified cause. No category below should be presented as a biological conclusion.

| Suggested, unverified category | FP | FN | Total |
| --- | ---: | ---: | ---: |
| possible weak feature signal | 64 | 17 | 81 |
| predicted benign but later pathogenic | 0 | 13 | 13 |
| predicted pathogenic but later benign | 6 | 0 | 6 |
| possible missing consequence | 4 | 1 | 5 |
| **Total** | **74** | **31** | **105** |

## Warning Patterns to Investigate

- **Missense concentration:** 86 of 105 errors were missense (64 FP, 22 FN). This is a count, not proof that missense status caused the errors.
- **Noncoding false negatives:** all six noncoding errors were FN. Six of the 19 highest-confidence errors were noncoding FN. This pattern warrants label, consequence, and feature review but is not yet an explanation.
- **Severe-consequence false positives:** both canonical-splice errors and both loss-of-function errors were FP; all four had confidence at least 0.8. Review whether the recorded consequence is appropriate for the relevant transcript and record.
- **Unrecognized consequences:** five errors had `unrecognized` consequence (four FP, one FN), matching the five unverified `possible missing consequence` suggestions.
- **In-frame indels:** four errors split evenly between FP and FN.
- **Missing context:** all 105 errors lack recorded VCV accession, review status, and match confidence, and all have blank warning flags. Manual review must not infer clean provenance from blank fields.
- **Model disagreement:** the full review queue contains 119 V8/V7 disagreements, including errors and correct V8 records. Disagreement is useful for review prioritization, not evidence that either model is correct.

## Exact Manual Review Priorities

The frozen queue contains 198 rows and applies these rules in order:

1. **High, bucket 0:** every wrong record with confidence at least 0.8, sorted by descending confidence and then numeric Variation ID. There are 19 records.
2. **High, bucket 1:** every remaining false negative, sorted by descending confidence and then Variation ID. There are 18 records; together with bucket 0, the high tier contains 37 rows.
3. **Medium, bucket 2:** every remaining false positive, sorted by descending confidence and then Variation ID. There are 68 records.
4. **Medium, bucket 3:** remaining V8/V7 disagreements, including correct V8 predictions, sorted by descending confidence and then Variation ID. There are 75 records; together with bucket 2, the medium tier contains 143 rows.
5. **Low, bucket 4:** remaining members of a deterministic 20-record correct sample, sorted by descending confidence and then Variation ID. The low tier contains 18 rows because two sampled correct records also disagreed with V7 and were raised to medium.

The correct control sample is selected independently of correctness interpretation by ranking correct TN/TP records with a fixed hash rule. It is included so review does not examine only failures. Within each reviewed row, check the cross-snapshot identity and scope, later aggregate label, relevant transcript/consequence, review status, submitter or condition conflict, and whether predictor fields were truly available at the predictor date. Record findings separately; do not overwrite frozen predictions or convert these suggestions into verified labels without evidence.

## Boundary

This error analysis describes patterns in one outcome-selected retrospective test. It does not determine clinical truth, explain the cause of reclassification, or justify changing V8 against the already-opened July 2026 outcomes. Any revised model requires a new version and a genuinely later untouched evaluation cohort.
