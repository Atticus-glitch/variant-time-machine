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

All conclusions will be restricted to the chosen releases, matching rules, feature availability, and evaluation design. These limitations will be updated as empirical problems are discovered.
