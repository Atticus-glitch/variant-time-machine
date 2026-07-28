# Real ClinVar History Pilot Report

> Real pilot data from official ClinVar records. Not yet suitable for model training or clinical use.

## Research question

Can official versioned ClinVar VCV records support a small, auditable assessment
of aggregate germline classification changes?

## Method

Up to ten attempted candidates were aggregated from bounded local VCV history
artifacts. Consecutive retrieved aggregate germline classifications were compared
without applying manual corrections; somatic clinical impact and oncogenicity were
not treated as germline outcomes.

## Official source

The records and transfer provenance come from official NCBI ClinVar E-utilities
requests retained in each history manifest.

## Sample size

Candidates attempted: 3.
Successfully retrieved: 3.
Official versions retrieved: 7.

## Results

Germline change: 1.
No germline change: 2.
Unable to compare or missing data: 0.
Manually verified: 0.
Needs review: 3.

## Transfer accounting

Candidate selection requests: 4.
Candidate selection response bytes: 113027.
Unique history response bytes: 244705.
Actual bytes newly transferred in this batch: 148735.
Total pilot response bytes represented: 357732.
The total adds candidate selection responses once to each unique row's source-history
responses. New-batch bytes are shown separately and are not added again.

## Examples

- VCV000000002: Other_Germline_Change (Pathogenic to Pathogenic/Likely pathogenic)
- VCV000000005: No_Germline_Change (Pathogenic to Pathogenic)
- VCV000014026: No_Germline_Change (Pathogenic to Pathogenic)

## Limitations

This is a small real-data pilot based on available official record versions, not
monthly snapshots. Missing versions, changed record structure, retrieval failures,
and unreviewed automatic classifications limit interpretation.
This pilot is not the final paper.

## Next step

Manually verify every pilot history against retained official sources, then expand
to approximately 25–50 suitable histories before deciding whether this method can
support model development.
