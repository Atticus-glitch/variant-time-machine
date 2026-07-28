# Data Dictionary

The repository contains three older release-pipeline artifacts plus the active bounded VCV history artifacts. The parser creates a standardized release table, the matcher creates a historical timeline table, and the downloader creates a JSON provenance record. The Version History Explorer separately stores one artifact tree per VCV. Exact ClinVar meanings must still be checked against the documentation for each source and version.

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

`data/manual_review/pilot_variants.csv` begins with five empty rows. It may contain at most ten manually selected variants.

| Field group | Meaning |
| --- | --- |
| `variant_id` | Numeric ClinVar Variation ID chosen manually |
| `VCV_accession` | Current VCV accession and version returned by ESummary |
| `gene` | Current gene symbol or symbols |
| `reason_selected` | Student-written reason for including this variant |
| `current_classification` | Current aggregate germline classification from ESummary |
| `historical_classification` | Classification from one explicit historical source; blank until retrieved |
| `source` | Exact official current and historical record URLs used |
| `verification_status` | What was retrieved and what still needs manual checking |
| `notes` | Retrieval date, version warning, and unresolved questions |

## VCV History Artifacts

The active Version History Explorer saves each result below the Git-ignored
`data/manual_review/vcv_history/<VCV>/` directory. See
`data/manual_review/README.md` for the exact tree. Automatic files are bounded and
written atomically; manual review remains separate.

### Parsed VCV Record

| Field | Meaning |
| --- | --- |
| `accession`, `version`, `accession_version` | Canonical base VCV, positive integer version, and combined exact identifier |
| `variation_id`, `record_type` | `VariationArchive` identifiers and type when present |
| `genes`, `name`, `hgvs`, `conditions` | Parsed variant and condition context; lists preserve unique source values |
| `date_created`, `date_last_updated`, `date_deleted` | Record-level dates supplied by ClinVar; missing dates remain null |
| `germline` | Independent classification block with `classification`, `review_status`, `date_last_evaluated`, and `submission_count` |
| `somatic_clinical_impact` | Separate block with the same four fields; never folded into germline |
| `oncogenicity` | Separate block with the same four fields; never folded into germline |
| `record_status`, `replaced_by`, `replacements`, `deleted` | Status, record-history links, and calculated deletion flag |
| `warnings` | Missing-field, deletion/replacement, or source warning text |

Each requested outcome also records `requested_identifier`, exact `source_request`,
`retrieved_at_utc`, `response_bytes`, `status`, parsed `record`, and `message`.
Status is `available`, `missing`, `deleted/replaced`, `request failure`, or
`parsing failure`. Raw XML is retained in a separate file when a response body was
received rather than embedded in the JSON.

### Version Comparison

| Field | Meaning |
| --- | --- |
| `earlier_version`, `later_version` | Two available versions being compared; unavailable holes are skipped and warned about |
| `earlier_identifier`, `later_identifier` | Exact VCV accession versions |
| `earlier_germline_classification`, `later_germline_classification` | Unmodified germline descriptions |
| `earlier_review_status`, `later_review_status` | Germline review-status text |
| `detected_classification_change` | Automatic comparison label |
| `submissions_changed` | Boolean when both germline counts exist; otherwise null |
| `warnings`, `confidence` | Comparison caveats and `high` or `limited` confidence |

Implemented detected labels are `No_Classification_Change`,
`VUS_to_Pathogenic`, `VUS_to_Likely_Pathogenic`, `VUS_to_Benign`,
`VUS_to_Likely_Benign`, `Pathogenic_to_VUS`, `Benign_to_VUS`,
`Became_Conflicting`, `Conflict_Resolved`, `Other_Germline_Change`,
`Non_Germline_Change`, and `Missing_Classification`. `Unable_to_Compare` and
`unable` confidence are declared schema values but are not currently emitted by
the consecutive-available-version comparison path.

### Saved JSON Files

| File | Contents |
| --- | --- |
| `metadata.json` | Requested accession, latest identifier, exact version plan, current-result metadata, summary, byte total, and cancellation state |
| `versions.json` | Historical request outcomes and parsed records, without embedded raw XML |
| `comparisons.json` | Automatic consecutive-available-version comparisons |
| `manifest.json` | Exact requests, statuses, response sizes, retrieval times, application/Git versions, warnings, total bytes, automatic-artifact digest, and manual-verification flag |
| `review.json` | Independent reviewer status, decision, notes, corrections, sources, timestamps, matching automatic-artifact digest, and ten verification booleans |
| `raw/<identifier>.xml` | Decoded unversioned-current or versioned XML response text when a body was received |

The five review statuses are `unreviewed`, `needs_review`, `ambiguous`,
`manually_verified`, and `excluded`. All ten verification values must be true for
`manually_verified`; ambiguous and excluded reviews require notes. Manual
corrections are annotations and do not alter any automatic file.
If refreshed automatic evidence has a different digest, an earlier manual verification
is reset to `needs_review` and all checks become false. Existing notes, sources, and
manual corrections remain separate and are preserved.

The older `pilot_review.json` belongs to the paused archive pilot and stores a
status, notes, and update time for reviewed Variation IDs.

## Real Pilot Results

`data/pilot_results/pilot_results.csv` contains one real row per attempted candidate
and labels every row `Real pilot data from official ClinVar records. Not yet suitable
for model training or clinical use.` Automatic and manual fields remain separate.

| Field group | Meaning |
| --- | --- |
| Identity | VCV accession, Variation ID, gene, first/newest version, versions retrieved |
| Automatic comparison | First/newest aggregate germline classification, detected category, change count, confidence, review/submission changes, warnings |
| Manual review | Status, reviewer decision, confirmed result, notes, and checklist count; blank until actually reviewed |
| Provenance | Measured response bytes, official request URLs, and local raw-record filenames |

`pilot_summary.json` stores actual sample counts, category counts, candidate-screening
bytes, unique history bytes, new-batch bytes, total represented response bytes, and
local history storage. `transfer_manifest.json` preserves per-candidate transfer and
source details. `manual_review.csv` is the separate review worksheet.

## Single Pilot Variant JSON

`data/manual_review/pilot_variant_001.json` starts empty and stores one selected
current record only after two confirmations.

| Field | Meaning |
| --- | --- |
| `variant_id` | Numeric ClinVar Variation ID |
| `vcv_accession` | Current VCV accession and version |
| `gene` | Current gene symbol or symbols |
| `selected_date` | Date the researcher accepted the pilot record |
| `selection_reason` | Written method-based reason for choosing the variant |
| `current_classification` | Current aggregate germline classification |
| `current_review_status` | Current aggregate germline review status |
| `conditions` | Current germline condition names returned by ESummary |
| `historical_records_found` | Possible historical source identifiers; empty until found |
| `verification_status` | Clear statement of completed and pending checks |
| `notes` | Limitations and manual research notes |
| `sources` | Exact current and future historical source URLs |

## Browser Pilot Workspace JSON

`data/manual_review/pilot_workspace.json` is the canonical browser pilot list. Its
top-level fields are `version`, `updated_at_utc`, and `records`. It starts with zero
records and is limited to ten.

Each record contains:

| Field group | Meaning |
| --- | --- |
| `variant_id`, `vcv_accession`, `gene`, `conditions` | Current official identifiers and context |
| `selection_reason`, `selected_date`, `created_at_utc` | Why and when the record entered the pilot |
| `current_classification`, `current_review_status` | Unchanged current ESummary wording |
| `current_source_url`, `current_retrieved_at_utc`, `current_transfer_bytes` | Current source and retrieval metadata |
| `intended_historical_date` | Optional date the researcher plans to investigate |
| `older_release_date`, `older_classification` | Manually entered past point; both remain empty until sourced |
| `newer_comparison_date`, `newer_classification` | Manually entered later comparison point |
| `historical_source_url` | Official HTTPS NCBI source supporting the past classification |
| `historical_classification_type` | Germline, somatic clinical impact, oncogenicity, other, or unable to determine |
| `notes`, `verification_notes`, `ambiguity_reason` | General work, evidence checks, and unresolved problems |
| `review_status` | `unreviewed`, `reviewing`, `verified`, `ambiguous`, or `excluded` |
| `verification_checklist` | Seven required human confirmation flags |
| `updated_at_utc` | Time of the latest saved change |

Manual classification options are `uncertain significance`, `pathogenic`, `likely
pathogenic`, `benign`, `likely benign`, `conflicting`, `protective`, `risk factor`,
`drug response`, `oncogenic`, `likely oncogenic`, `other`, and `unable to determine`.
These are never collapsed into a binary harmful/harmless field.

The API adds a calculated `timeline` to responses. This value is not stored and never
fills a missing classification. If the older point is absent, the change category is
`Historical classification not yet verified.`
