# V8 Case Studies

## Purpose and Selection

These 20 examples describe recorded V8 outcomes; they are not clinical interpretations. Selection was deterministic, not hand-picked and not randomized at page load. Within each frozen confusion group, records were ranked by ascending `SHA-256(salt + ':' + variation_id)` using salt `v8-case-studies-2026-08-02`, and the first five were taken. The source artifact records five cases each for TN, TP, FP, and FN.

## Plain-Language Labels

- **TN (true negative):** V8 predicted movement toward benign, and the later aggregate classification moved toward benign.
- **TP (true positive):** V8 predicted movement toward pathogenic, and the later aggregate classification moved toward pathogenic.
- **FP (false positive):** V8 predicted movement toward pathogenic, but the later aggregate classification moved toward benign.
- **FN (false negative):** V8 predicted movement toward benign, but the later aggregate classification moved toward pathogenic.

Pathogenic direction is the positive class. `P(pathogenic)` is V8's recorded probability of movement toward pathogenic, and V8 predicts the pathogenic direction at `P(pathogenic) >= 0.315`. Confidence is the recorded probability assigned to the recorded predicted direction: `P(pathogenic)` for a pathogenic-direction prediction and `1 - P(pathogenic)` for a benign-direction prediction. It is not `max(P(pathogenic), 1 - P(pathogenic))`, so a pathogenic-direction prediction can have confidence below 0.5. All records began as `Uncertain significance`. VCV accession, match confidence, and review status were not recorded for these cases; therefore VCV is unavailable rather than inferred.

## True Negatives

| Variation ID | Gene | Consequence | Later classification | Predicted direction | P(pathogenic) | Confidence | VCV |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| [2646459](https://www.ncbi.nlm.nih.gov/clinvar/variation/2646459/) | SETD1A | missense | Likely benign | toward benign | 0.2119 | 0.7881 | unavailable |
| [1478553](https://www.ncbi.nlm.nih.gov/clinvar/variation/1478553/) | CLTC | noncoding | Likely benign | toward benign | 0.0931 | 0.9069 | unavailable |
| [1519128](https://www.ncbi.nlm.nih.gov/clinvar/variation/1519128/) | TYROBP | synonymous | Likely benign | toward benign | 0.0127 | 0.9873 | unavailable |
| [1935539](https://www.ncbi.nlm.nih.gov/clinvar/variation/1935539/) | HEPACAM | synonymous | Likely benign | toward benign | 0.0122 | 0.9878 | unavailable |
| [1372659](https://www.ncbi.nlm.nih.gov/clinvar/variation/1372659/) | POLR3A | synonymous | Likely benign | toward benign | 0.0127 | 0.9873 | unavailable |

## True Positives

| Variation ID | Gene | Consequence | Later classification | Predicted direction | P(pathogenic) | Confidence | VCV |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| [1675625](https://www.ncbi.nlm.nih.gov/clinvar/variation/1675625/) | CETP | loss of function | Pathogenic | toward pathogenic | 0.9734 | 0.9734 | unavailable |
| [1480008](https://www.ncbi.nlm.nih.gov/clinvar/variation/1480008/) | KCNJ2 | loss of function | Pathogenic | toward pathogenic | 0.9797 | 0.9797 | unavailable |
| [2002672](https://www.ncbi.nlm.nih.gov/clinvar/variation/2002672/) | OSGEP | canonical splice | Likely pathogenic | toward pathogenic | 0.9397 | 0.9397 | unavailable |
| [1805124](https://www.ncbi.nlm.nih.gov/clinvar/variation/1805124/) | SORD | loss of function | Likely pathogenic | toward pathogenic | 0.9911 | 0.9911 | unavailable |
| [2058503](https://www.ncbi.nlm.nih.gov/clinvar/variation/2058503/) | TBXAS1 | loss of function | Pathogenic | toward pathogenic | 0.9320 | 0.9320 | unavailable |

## False Positives

| Variation ID | Gene | Consequence | Later classification | Predicted direction | P(pathogenic) | Confidence | VCV |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| [1444570](https://www.ncbi.nlm.nih.gov/clinvar/variation/1444570/) | HMCN1 | canonical splice | Likely benign | toward pathogenic | 0.8400 | 0.8400 | unavailable |
| [1508049](https://www.ncbi.nlm.nih.gov/clinvar/variation/1508049/) | SOX9 | missense | Likely benign | toward pathogenic | 0.3922 | 0.3922 | unavailable |
| [2153622](https://www.ncbi.nlm.nih.gov/clinvar/variation/2153622/) | PEPD | missense | Likely benign | toward pathogenic | 0.4800 | 0.4800 | unavailable |
| [1358885](https://www.ncbi.nlm.nih.gov/clinvar/variation/1358885/) | MYO15A | missense | Likely benign | toward pathogenic | 0.3707 | 0.3707 | unavailable |
| [2530789](https://www.ncbi.nlm.nih.gov/clinvar/variation/2530789/) | PEX16 | missense | Likely benign | toward pathogenic | 0.5451 | 0.5451 | unavailable |

## False Negatives

| Variation ID | Gene | Consequence | Later classification | Predicted direction | P(pathogenic) | Confidence | VCV |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| [2179139](https://www.ncbi.nlm.nih.gov/clinvar/variation/2179139/) | SPAG1 | noncoding | Pathogenic | toward benign | 0.0796 | 0.9204 | unavailable |
| [2085378](https://www.ncbi.nlm.nih.gov/clinvar/variation/2085378/) | DEAF1 | missense | Pathogenic | toward benign | 0.2672 | 0.7328 | unavailable |
| [1403780](https://www.ncbi.nlm.nih.gov/clinvar/variation/1403780/) | PEPD | missense | Pathogenic/Likely pathogenic | toward benign | 0.2160 | 0.7840 | unavailable |
| [1367200](https://www.ncbi.nlm.nih.gov/clinvar/variation/1367200/) | DRAM2 | missense | Pathogenic | toward benign | 0.2205 | 0.7795 | unavailable |
| [2125741](https://www.ncbi.nlm.nih.gov/clinvar/variation/2125741/) | EXOC6B | noncoding | Likely pathogenic | toward benign | 0.0856 | 0.9144 | unavailable |

## Interpretation Boundary

These are examples from a sealed gene-component-disjoint retrospective temporal test. They show how the recorded prediction labels map to later aggregate ClinVar classifications. They do not establish why any classification changed, validate the suggested consequence interpretation, or support clinical use.
