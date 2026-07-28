# First Real VCV History Pilot Results

> Real pilot data from official ClinVar records. Not yet suitable for model training or clinical use.

## Purpose

This pilot tested whether individual official ClinVar VCV histories could be collected
and compared with low bandwidth. It is a descriptive methods result, not a prediction
model or clinical analysis.

## Method

The sample was fixed before historical retrieval. It included the existing
`VCV000014026` case, then the two lowest Variation IDs among previously identified
candidates with a canonical multi-version VCV, visible gene, aggregate germline
classification, and no dominant somatic, oncogenicity, drug-response, protective, or
risk-factor category.

The dashboard displayed and confirmed a plan for three candidates. It reused the
existing complete `VCV000014026` history and made at most three new requests for each
other candidate: current, first, and newest VCV. The approved plan allowed six new
requests and at most 62,914,560 new response bytes. Requests used official NCBI
ClinVar EFetch, ran sequentially, and retained their small XML responses and exact
provenance.

Aggregate germline classification was analyzed separately from somatic clinical
impact and oncogenicity. `VCV000000002` and `VCV000000005` used endpoint sampling, so
unsampled intermediate versions remain an explicit limitation. Automatic comparisons
were not changed using manual annotations. All three histories still require manual
review and have 0 of 10 verification checks complete.

## Results

Three candidates were attempted and all three were retrieved successfully. Seven
official VCV versions were included. One history had a detected germline wording
change, two had no detected germline change, and zero were unable to compare. No
history is manually verified.

| VCV | Gene | Versions | First germline classification | Newest germline classification | Automatic category | Confidence | Manual status |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| `VCV000000002` | AP5Z1 | 1, 5 | Pathogenic | Pathogenic/Likely pathogenic | `Other_Germline_Change` | limited | needs review |
| `VCV000000005` | FOXRED1 | 1, 11 | Pathogenic | Pathogenic | `No_Germline_Change` | limited | needs review |
| `VCV000014026` | TACR3; TACR3-AS1 | 1, 2, 3 | Pathogenic | Pathogenic | `No_Germline_Change` | high | needs review |

The candidate-screening requests transferred 113,027 response bytes. The three saved
history evidence sets contain 244,705 response bytes, including 148,735 bytes from the
new approved batch and 95,970 bytes from the reused earlier history. Total measured
pilot response-body transfer was 357,732 bytes. HTTP protocol overhead is not included.
The three local history trees used 281,259 bytes when the outputs were generated.

## Interpretation

The pilot demonstrates that small official requests can produce an auditable,
downloadable comparison across genuine VCV versions without a full ClinVar archive.
It also shows why a version increment is not the same as a classification change: two
histories changed review or submission information while retaining the same germline
classification.

The AP5Z1 record is the only automatic germline change in this sample. Its aggregate
wording changed from `Pathogenic` to `Pathogenic/Likely pathogenic`. This is not a VUS
to pathogenic result, and it has limited automatic confidence because versions 2–4
were not retrieved. A person must inspect the retained records and classification
scope before confirming it.

## Limitations

- The sample has only three variants and was selected by a non-random methods rule.
- VCV versions are not identical to complete monthly ClinVar release snapshots.
- Two histories sampled only first and newest versions; intermediate changes may be missing.
- Records may have missing fields or changing XML structure.
- Automatic XML parsing and category mapping may be imperfect.
- Manual verification is incomplete for all three histories.
- The measured byte count excludes HTTP protocol overhead.
- No predictive model has been trained or tested.
- These results cannot estimate ClinVar-wide reclassification rates or support clinical use.

## Next Step

Manually verify all three histories, especially the AP5Z1 aggregate wording change and
the unsampled intermediate-version limitation. Then expand to approximately 25–50
suitable, manually reviewed histories before deciding whether this method can support
model development.
