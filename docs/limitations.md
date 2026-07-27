# Limitations

- ClinVar is a submission database, not an error-free ground truth. Submitters can disagree, evidence quality varies, and classifications change.
- A variant can have different interpretations for different conditions or inheritance patterns. Collapsing these records may hide meaningful distinctions.
- Archive formats, identifiers, genomic assemblies, and representations may change over time, creating matching errors or selection bias.
- “Remained uncertain” at one later date does not mean a variant will remain uncertain forever.
- Reclassification can reflect new evidence, changed criteria, laboratory policy, record merging, or correction rather than a newly discovered biological fact.
- Historical external annotations may be unavailable, making leakage-free reconstruction difficult.
- Outcome classes may be strongly imbalanced, so raw accuracy can be misleading.
- A model trained on included ClinVar records may not generalize to unsubmitted variants, other databases, clinical populations, or future scientific practices.
- Explainable associations are not proof of biological causation.
- Public, non-identifiable records reduce privacy risk but do not make predictions suitable for individual medical use.
- The current parser is designed for archived `variant_summary` headers but has not yet been run against the selected full files.
- The current matcher does not resolve coordinate-only matches, record replacements, or deletions through XML.
- Exact outcome mapping is intentionally conservative. Explicit conflict text becomes `VUS_to_Conflicting`, while unfamiliar mixed terms become `Unable_to_Verify`.
- The synthetic timeline verifies software behavior only. Its counts and outcomes say nothing about real ClinVar reclassification rates.
- The current parser reads a release table into memory. Memory use and a possible chunked approach must be tested before processing the full archives.
- The five to ten pilot variants will be manually selected. They will not be representative of ClinVar and cannot estimate a reclassification rate.
- Streaming saves local disk, but a missing late record can still require transferring an entire 3.33 GB or 4.56 GB compressed archive.
- The two pilot releases use VCV schema revisions 2.0 and 2.2. Named fields can still be absent or change meaning, so extraction tests do not replace source review.
- Official MD5 values identify the complete source files. A stream that stops early cannot calculate and verify the complete archive MD5 from transferred bytes.
- An exact Variation ID is a conservative automatic link, not proof that condition scope, aggregation, or scientific meaning stayed the same.
- Replacement and non-current record metadata are flagged but never followed automatically.
- Current ESummary values were retrieved on 2026-07-26 and may change later. They do not prove values in either archived release.
- No archived pilot extraction will be run in the current strategy. Dashboard historical cells remain empty until a small source-backed record is reviewed.
- A versioned VCV EFetch record is not automatically the record active in an arbitrary monthly release. Version dates and classification scope require manual verification.
- Browser validation and checklists reduce mistakes but cannot prove that a person interpreted a source correctly.
- Gene search returns at most five current candidates and is not a complete gene-level analysis.
- Actual transfer size is measured from returned API bodies when available; it is not a full network-traffic meter for protocol overhead.
- The local JSON backup stores only the immediately previous workspace state. It is not a complete audit-history system.
- A record marked `verified` means the project checklist was completed. It does not mean ClinVar is ground truth or that the classification is medically correct.
- The Pilot Workspace is local and intended for one researcher. It does not implement user accounts or multi-user conflict resolution.

All conclusions will be restricted to the chosen releases, matching rules, feature availability, and evaluation design. These limitations will be updated as empirical problems are discovered.
