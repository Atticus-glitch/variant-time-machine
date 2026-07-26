# Data Dictionary

The pipeline uses three related tables. The parser creates a standardized release table, the matcher creates a historical timeline table, and the downloader creates a JSON provenance record. Exact ClinVar header meanings must still be checked against the documentation for each selected release.

## Standardized Release Table

| Field | Meaning | Quality note |
| --- | --- | --- |
| `data_notice` | Label identifying synthetic or special-purpose input | Synthetic rows must say `SYNTHETIC TEST DATA - NOT SCIENTIFIC RESULTS` |
| `source_row_id` | Row identifier from the source table | Used for tracing a parsed row back to its input |
| `variant_id` | Internal primary variant identifier, currently copied from `VariationID` | Kept as text because identifiers are labels, not measurements |
| `allele_id` | ClinVar Allele ID for an individual allele | Can participate in more than one classified variant set |
| `variation_id` | Original ClinVar Variation ID | Can represent one allele or a more complex allele set |
| `gene` | Gene symbol reported by ClinVar | May be missing or contain more than one value |
| `assembly` | Genome assembly for the row, such as GRCh37 or GRCh38 | Separate assembly rows must not be counted as separate variants |
| `chromosome` | Chromosome reported by ClinVar | Not used as the sole match key |
| `chromosome_accession` | RefSeq accession and version for the genomic sequence | Important when coordinates are reviewed |
| `position` | One-based `Start` value from `variant_summary` | Uses ClinVar's reported right-shifted representation |
| `stop_position` | One-based `Stop` value from `variant_summary` | May be missing for incomplete records |
| `reference_allele` | Reference allele reported for `Start` and `Stop` | A dash may be a meaningful allele representation, not missing data |
| `alternate_allele` | Alternate allele reported for `Start` and `Stop` | Not yet normalized for coordinate matching |
| `classification` | Aggregate `ClinicalSignificance` text | Preserved as text and mapped only when it exactly matches a supported term |
| `review_status` | Aggregate ClinVar review status | Review strength may change over time |
| `submission_count` | Number of submitters reported by ClinVar | Parsed as a nullable integer |
| `condition_accessions` | RCV accessions reported for the variant | Supporting audit information, not a sole matching key |
| `phenotype_list` | Condition names reported by ClinVar | Names may change and may be shortened in summary files |
| `release_date` | Date of the fixed ClinVar snapshot | Different from the date the file was downloaded |

## Historical Timeline Table

| Field | Meaning | Quality note |
| --- | --- | --- |
| `variant_id` | Older release Variation ID | Never replaced by a later identifier |
| `allele_id` | Older release Allele ID | Retained for match auditing |
| `matched_variant_id` | Variation ID of the selected later record | May differ when a unique Allele ID match is found |
| `gene` | Gene information from the older release | Multiple distinct values are joined rather than discarded |
| `old_classification` | Classification in the older release | Timeline rows are limited to exact supported VUS terms |
| `new_classification` | Classification in the selected later record | Missing when no reliable later record is selected |
| `old_review_status` | Review status in the older release | Eligible as historical metadata only after validation |
| `new_review_status` | Review status in the newer release | Outcome audit information, not an older-date feature |
| `old_submission_count` | Submitter count in the older release | Multiple distinct values are preserved as joined text |
| `new_submission_count` | Submitter count in the newer release | Must never be used as a historical predictor |
| `old_release_date` | Date of the predictor snapshot | Defines the feature cutoff |
| `new_release_date` | Date of the outcome snapshot | Must be later than the older date |
| `classification_change` | Declared outcome mapping | Uses only the labels listed below |
| `match_status` | Rule or problem encountered during matching | Separates reliable matches from ambiguous cases |
| `candidate_count` | Number of distinct later entities considered by the selected rule | Counts above one prevent automatic selection |
| `old_source_row_count` | Number of older source rows combined into the entity | Helps identify duplicate assembly rows and complex records |
| `new_source_row_count` | Number of newer source rows combined into the selected entity | Missing when no later entity is selected |
| `old_source_row_ids` | Source row IDs from the older standardized table | Supports tracing a result back to parsed input |
| `new_source_row_ids` | Source row IDs from the selected newer entity | Missing when no later entity is selected |
| `old_assemblies` | Distinct genome assemblies in the older entity | Preserves evidence that assembly rows were combined |
| `new_assemblies` | Distinct genome assemblies in the selected newer entity | Missing when no later entity is selected |

Supported `classification_change` values:

- `VUS_to_Pathogenic`
- `VUS_to_Likely_Pathogenic`
- `VUS_to_Benign`
- `VUS_to_Likely_Benign`
- `VUS_to_Conflicting`
- `VUS_to_Still_Uncertain`
- `Unable_to_Verify`

Current `match_status` values include:

- `exact_identifier_match`
- `exact_variation_id_match`
- `allele_id_match_variation_changed`
- `ambiguous_multiple_candidates`
- `conflicting_identifiers`
- `unsupported_complex_identifier`
- `missing_identifier`
- `unmatched`

## Download Metadata JSON

| Field | Meaning |
| --- | --- |
| `source_url` | Exact official URL requested |
| `release_date` | Configured ClinVar snapshot date |
| `retrieval_date_utc` | Date and time the download completed in UTC |
| `filename` | Local archive filename |
| `size_bytes` | Number of bytes written |
| `checksum_algorithm` | Hash algorithm, currently SHA-256 |
| `checksum` | Calculated hexadecimal file hash |
| `expected_size_bytes` | Official file size configured before download, when available |
| `expected_sha256` | Published or independently verified expected hash, when available |

## Manual Review Table

`data/manual_review/test_variants.csv` contains no rows until real histories are checked.

| Field | Meaning |
| --- | --- |
| `variant_id` | Manually confirmed ClinVar Variation ID |
| `gene` | Gene confirmed for the same variant record |
| `old_release_date` | Exact older archived snapshot date |
| `new_release_date` | Exact newer archived snapshot date or clearly labeled current retrieval date |
| `old_classification` | Classification copied from the verified older source |
| `new_classification` | Classification copied from the verified newer source |
| `verification_source` | Official source URLs or archive file references for both dates |
| `notes` | Identifier changes, condition scope, conflicts, and unresolved uncertainty |

## Current Pilot CSV

`data/manual_review/pilot_variants.csv` contains current ESummary facts and empty historical placeholders.

| Field group | Meaning |
| --- | --- |
| `variation_id` | Numeric ClinVar Variation ID selected for extraction |
| `current_accession` | Current VCV accession and version returned by ESummary |
| `current_name` | Current variant title returned by ESummary |
| `current_gene` | Current gene symbol or symbols |
| `current_germline_classification` | Current aggregate germline classification only |
| `current_review_status` | Current aggregate germline review status |
| `current_conditions` | Current germline condition names, including literal `not provided` values |
| `current_source_url` | Official current ClinVar record URL |
| `current_retrieved_date` | Date the current summary was retrieved |
| `older_*`, `newer_*` | Historical placeholders; blank until archive extraction |
| `manual_review_status` | Initial review state; does not claim verification |
| `manual_review_notes` | Optional reviewer notes |

## Extracted VCV Record

| Field | Meaning |
| --- | --- |
| `variation_id` | `VariationID` on `VariationArchive` |
| `accession`, `version` | VCV accession and archive version |
| `record_type`, `record_status` | Archive record type and current, replaced, or other stated status |
| `name` | Name from the classified allele or allele set when present |
| `allele_ids`, `genes`, `conditions` | Lists found within that archive record |
| `germline_classification` | Aggregate germline description only |
| `germline_review_status` | Germline review status only |
| `germline_last_evaluated` | Germline evaluation date attribute when present |
| `germline_submission_count` | Germline submission count attribute when present |
| `somatic_clinical_impact` | Somatic clinical impact description only |
| `oncogenicity_classification` | Oncogenicity description only |
| `replaced_by`, `replacement_list` | Record-history accessions stated by ClinVar |

## Pilot Manifest and Comparison

Each release manifest records the exact URL, release date, schema revision, expected full-file size and MD5, compressed bytes read, requested and missing IDs, output hash, and whether the full scan completed. `source_archive_retained` is always false for this command. The expected full-file MD5 is provenance, not a claim that an early-stopped stream verified the entire archive.

Pilot comparisons include `match_status`, `classification_change`, separate old and new classification types, `record_history_flags`, and `automatic_verification_status`. Supported XML pilot match states are exact Variation ID, missing in older, missing in newer, and missing in both. Every automatic verification status is `requires_manual_review`.

`pilot_review.json` stores a status, notes, and update time for each reviewed Variation ID. Allowed states are `Not reviewed`, `Confirmed match`, `Needs follow-up`, and `Rejected automatic match`.
