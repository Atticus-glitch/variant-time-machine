# Historical ClinVar Data Plan

Date: 2026-07-26

## Immediate Goal

Validate the research method with five to ten manually selected variants. The pilot
tests identifiers, source recording, current lookup, historical version review, and
honest missing-data handling. It is not representative and will not be used for
machine learning.

## Paused Archive Pair

The previously considered VCV XML releases were February 2024 at 3,334,050,859
compressed bytes and February 2025 at 4,556,267,423 bytes. A scan could transfer about
7.89 GB. The files are valid fixed historical sources, but they are not appropriate
for this small pilot. No archive body has been requested or retained.

`scripts/extract_pilot_history.py` is now metadata-only. It can check headers and tiny
official MD5 files, but it cannot start the archive scan.

## Transfer Safety Rule

Before any project download, the software must show:

1. The exact source.
2. The estimated size.
3. Why the transfer is needed.
4. Whether it crosses the 500 MB large-download boundary.

The transfer waits for explicit confirmation. A ClinVar archive larger than 500 MB
must never begin silently. Unknown sizes receive the same protected treatment.

## Manual Pilot

`data/manual_review/pilot_workspace.json` is the active browser pilot list. It begins
with zero records and is limited to ten. A student chooses each variant for a written
reason. The dashboard first displays the transfer plan and requires approval before a
small official request. The five-row CSV and scripts remain optional developer tools.

Current data come from ESummary for one Variation ID. Historical information may come
from EFetch only when an explicit VCV accession version has been identified. The
historical response is capped at 10 MB. A VCV version must be dated and reviewed by a
person; it is not assumed to equal any monthly release.

## Inclusion Rule

A populated row must preserve the Variation ID, VCV accession, gene, reason selected,
current classification, exact sources, verification state, and notes. Historical
classification stays blank until a source-backed version has been retrieved and its
date and scope have been checked. Empty fields must never be replaced by guesses.

## Pilot Success Criteria

The pilot works when five to ten variants can be selected, retrieved in small requests,
stored reproducibly, and reviewed without confusing current and historical facts. Only
then should the project consider an indexed query, a summary file, or a larger archive.
Any later download still requires a scientific reason, a size review, and explicit
approval.
