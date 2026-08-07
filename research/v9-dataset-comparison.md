# V8, Original V9, And V9.1 Dataset Comparison

## Important Boundary

V8 and original V9 used the same 1,000 outcome rows for evaluation, but not in equivalent
ways. V8 reached them as a sealed component-disjoint retrospective test after training on
9,818 other records. Original V9 reused the already opened labels in nested validation.
V9.1 retains those same 1,000 rows for internal development and does not call them a new
test.

## Current Counts

| Dataset | Records | Benign direction | Pathogenic direction | Components | Review state | Expected difficulty |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Frozen V8 sealed test | 1,000 | 814 | 186 | 559 | Not manually reviewed at evaluation | Honest temporal/component-disjoint test |
| Original V9 opened dataset | 1,000 | 814 | 186 | 559 | 1,000 pending | Same cases, but labels already opened |
| V9.1 all eligible | 1,000 | 814 | 186 | 559 | 1,000 pending | Same all-record cohort; internal validation only |
| V9.1 clean reviewed | 0 | 0 | 0 | 0 | No completed reviews | Too small to evaluate |
| V9.1 strict clean | 0 | 0 | 0 | 0 | No completed reviews | Too small to evaluate |
| V9.1 ambiguous/pending | 1,000 | 814 | 186 | 559 | Review pending | Contains every current case, including all errors |
| V9.1 explicitly excluded | 0 | 0 | 0 | 0 | No explicit exclusion decisions | No scientific exclusions yet |

The clean and strict-clean datasets are not empty because difficult cases were deleted.
They are empty because no human review has been completed. Every source record remains in
the all-eligible and ambiguous/pending files.

## Feature Completeness

All three 1,000-row views use the same authenticated 64-feature January 2024 schema.

| Check | Count |
| --- | ---: |
| High match confidence under frozen temporal rule | 1,000 |
| Missing gene indicator | 0 |
| Missing coordinate indicator | 0 |
| Missing phenotype-ID indicator | 0 |
| Unrecognized/missing consequence | 15 |
| Missense chemistry available | 230 |
| Constant feature columns in this cohort | 11 |

The high match-confidence field comes from the frozen identity rule. It does not by itself
prove comparable later condition scope. Condition/scope comparison was not retained for
all 1,000 rows, so automatic promotion into strict clean would overstate the evidence.

## Match And Ambiguity Distribution

| Item | Count |
| --- | ---: |
| Human reviews completed | 0 |
| Review pending | 1,000 |
| V8 errors among pending rows | 105 |
| V8/V7 disagreements among pending rows | 119 |
| High-confidence V8 errors among pending rows | 19 |
| AI suggestions requiring confirmation | 105 |
| AI-suggested scope/expert concerns | 9 |

AI suggestions are not used to accept, reject, relabel, or train a row. Using suggestions
that were generated only for V8 errors as exclusion rules would disproportionately filter
mistakes and create a cherry-picking risk.

## Did Cleaning Change Class Balance Or Difficulty?

No cleaning has happened yet. All-eligible V9.1 has the exact same 81.4% benign-direction
and 18.6% pathogenic-direction distribution as the V8 test and original V9 dataset. No
label changed and no FP or FN was explicitly excluded.

The current all-eligible V9.1 task is therefore not cleaner or harder than the V8 cohort.
Its evaluation is weaker because the labels are opened, not stronger because the records
changed. Future clean subsets may become smaller or harder after review; if that occurs,
the project must report class shifts, removed FP/FN counts, ambiguity, and all-record
results beside every clean result.

## Training Data Difference

V9.1 also authenticates the prior V8 development matrix of 9,818 records across 1,792
components. Those records are not additional V9.1 review cases and are not written into
the five requested review-state CSV files. They are eligible prior development data with
audited zero component overlap with the 1,000-row outer validation cohort. The frozen
V9.1 plan compares an original-V9-style 1,000-row regime with an augmented regime that
adds this prior development matrix to each training fold.

## Warnings

- V9.1 clean reviewed and strict clean are too small for any metric or model selection.
- A high score on a future filtered subset cannot be directly compared with V8's
  all-record score unless the same records are used.
- Pending review is not a scientific exclusion.
- The 1,000 all-eligible labels are opened and cannot serve as a final V9.1 test.
- None of these datasets supports clinical-use claims.
