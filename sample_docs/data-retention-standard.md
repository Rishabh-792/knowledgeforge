# Larkspur Dynamics — Data Retention Standard (DRS-7)

_Fictional sample document for KnowledgeForge demos. Larkspur Dynamics is an
invented company and these schedules are illustrative only._

## 1. Purpose

This standard defines how long each class of Larkspur Dynamics data is kept,
how it is destroyed, and how destruction is suspended when a legal hold is in
force. It is owned by the records management office.

## 2. Retention Schedule by Data Class

| Class | Contents | Retention period |
|------|------|------|
| A — Financial records | Invoices, ledgers, tax filings, contracts | Seven years after close of fiscal year |
| B — Employment records | Offer letters, reviews, payroll history | Six years after end of employment |
| C — Operational logs | Application and infrastructure logs | Eighteen months |
| D — Debug and trace data | Verbose traces, request dumps | Forty-five days |
| E — Marketing and web analytics | Campaign and site engagement data | Twenty-four months |
| F — Recruitment records | Applications from candidates not hired | Twelve months |

Anything not listed above defaults to Class C. Teams may not extend a retention
period unilaterally; extensions require an approved records exception.

## 3. Deletion Procedures

Scheduled purges run on the first Sunday of each month at 02:00 platform time.
Deletion of Class A or Class B data requires two-person approval — the records
officer plus the system owner.

Encrypted stores are destroyed by crypto-shredding: the data-encryption key is
destroyed and the ciphertext is left to age out. A certificate of destruction
is issued within fifteen business days of any bulk deletion.

## 4. Legal Hold

A legal hold is issued only by the general counsel's office and immediately
suspends every scheduled purge touching the named custodians or systems. Holds
are reviewed every six months and can be lifted only in writing by the issuing
attorney. Deleting data known to be under hold is treated as gross misconduct.

## 5. Backup Schedule

Nightly incremental backups are retained for thirty-five days. Weekly full
backups are retained for six months. A yearly archive snapshot is written to
immutable storage and retained for seven years.

Restore rehearsals are performed twice per year against a randomly selected
backup set; the recovery point objective is one hour and the recovery time
objective is four hours for tier-one systems.

## 6. Media Disposal

Decommissioned drives are wiped to the approved sanitisation standard and then
physically shredded by a bonded vendor. Serial numbers are recorded in the
asset register before the drives leave the building.

## 7. Exceptions

Exception requests go to records-office@larkspur.example. Approved exceptions
expire after twelve months and must be renewed with fresh justification.
