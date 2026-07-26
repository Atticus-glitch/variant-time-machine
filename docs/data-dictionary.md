# Data Dictionary

This is a preliminary schema for discussion. Exact names and types will be finalized only after the selected ClinVar archive formats are examined.

| Field | Proposed meaning | Leakage or quality note |
| --- | --- | --- |
| `variant_id` | Stable ClinVar identifier selected after archive research | Must be verified across both releases |
| `older_release_date` | Date of the predictor ClinVar release | Defines the information cutoff |
| `newer_release_date` | Date of the outcome ClinVar release | Must be later than the cutoff |
| `older_classification` | Classification in the older release | Inclusion should require an explicit uncertain definition |
| `newer_classification` | Classification in the newer release | Used to derive the outcome, never as a feature |
| `outcome` | Harmful, harmless, remained uncertain, or unusable/ambiguous | Mapping rules must be documented before analysis |
| `match_method` | Identifier or genomic evidence used to connect records | Needed for auditing match reliability |
| `match_status` | Verified, ambiguous, conflicting, or unusable | Ambiguous cases should not silently enter training |
| `review_status_at_cutoff` | ClinVar review status in the older release | Must come only from the older snapshot |
| `submitter_count_at_cutoff` | Earlier count of relevant submitters | Definition and historical availability require verification |

Future feature fields will include a source, release, units, missing-value meaning, transformation, and evidence that they existed by the cutoff date.
