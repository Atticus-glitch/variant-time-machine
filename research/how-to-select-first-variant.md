# How to Select the First Pilot Variant

Date: 2026-07-26

## Purpose

The first variant tests whether one real ClinVar record can move through selection,
current lookup, metadata recording, historical investigation, manual verification,
and dashboard display. It is a methods test, not a scientific result.

## A Good First Variant

A good first pilot variant should:

- have a stable numeric ClinVar Variation ID and VCV accession,
- have clear current gene, classification, review status, and condition information,
- not have extreme conflicts among current classifications,
- be understandable enough to explain in a student project,
- have enough visible version or record-history information to investigate manually,
- have a written reason for selection that does not depend on a desired outcome.

## Avoid at First

Avoid:

- variants with many contradictory classifications,
- records with missing or unclear identifiers,
- haplotypes, genotypes, or other complex records unless they are the research topic,
- mixed germline, somatic clinical impact, and oncogenicity classifications unless
  those different classification types are being studied separately,
- variants chosen because they appear to show an impressive change,
- records whose condition scope cannot be understood.

## Preview Candidates

Preview by Variation ID:

```bash
python scripts/select_pilot_variant.py --variation-id 14206
```

Preview by VCV accession:

```bash
python scripts/select_pilot_variant.py --vcv VCV000014206
```

Preview up to five current candidates for one gene:

```bash
python scripts/select_pilot_variant.py --gene BRCA1
```

These commands first show the API source, maximum estimated transfer, and reason. No
request starts until `--confirm-api-requests` is added. The tool only previews current
records and never accepts or saves a research example.

## Selection Checklist

Before running the workflow, write down:

1. Why this variant is useful for testing the method.
2. Whether its Variation ID and VCV accession agree.
3. Whether the current classification type is germline and understandable.
4. Whether the review status and condition scope are clear.
5. What possible historical source could be checked later.

Then run `scripts/run_pilot_workflow.py`. Confirm the small API request, inspect the
returned preview, and separately confirm that it should be saved. Historical fields
must remain empty until official evidence is found and checked manually.
