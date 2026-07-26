# Data Dictionary

This is a preliminary schema for discussion. Exact names and types will be finalized only after the selected ClinVar archive formats are examined.

| Field | Proposed meaning | Leakage or quality note |
| --- | --- | --- |
| `allele_id` | ClinVar Allele ID for an individual allele | Primary allele-level identifier; column context matters |
| `variation_id` | ClinVar Variation ID for a classified allele set | Can represent complex sets and can change through record lifecycle events |
| `older_release_date` | Date of the predictor ClinVar release | Defines the information cutoff |
| `newer_release_date` | Date of the outcome ClinVar release | Must be later than the cutoff |
| `older_classification` | Classification in the older release | Inclusion should require an explicit uncertain definition |
| `newer_classification` | Classification in the newer release | Used to derive the outcome, never as a feature |
| `outcome` | Harmful, harmless, remained uncertain, or unusable/ambiguous | Mapping rules must be documented before analysis |
| `match_method` | Identifier or genomic evidence used to connect records | Initial proof of concept uses identifiers only |
| `match_status` | Exact, changed Variation ID, ambiguous, conflicting, unsupported, or unmatched | Ambiguous cases must not silently enter training |
| `candidate_count` | Number of distinct later entities considered by the applied rule | A count above one prevents automatic matching |
| `source_row_count` | Number of older assembly rows collapsed into one identifier entity | Prevents GRCh37 and GRCh38 rows from being counted twice |
| `review_status_at_cutoff` | ClinVar review status in the older release | Must come only from the older snapshot |
| `submitter_count_at_cutoff` | Earlier count of relevant submitters | Definition and historical availability require verification |

Future feature fields will include a source, release, units, missing-value meaning, transformation, and evidence that they existed by the cutoff date.
