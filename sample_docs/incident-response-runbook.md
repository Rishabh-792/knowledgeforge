# Larkspur Dynamics — Incident Response Runbook

_Fictional sample document for KnowledgeForge demos. Larkspur Dynamics and its
Atlas platform are invented._

## 1. Severity Levels

| Level | Definition | Paging | Customer comms |
|------|------|------|------|
| SEV1 | Full outage or data loss affecting multiple customers | Immediate page, day or night | Status page within fifteen minutes |
| SEV2 | Major feature degraded, no workaround | Immediate page during extended hours | Status page within one hour |
| SEV3 | Degraded performance with a workaround | Ticket only, next business day | Note in weekly digest |
| SEV4 | Cosmetic or low-impact defect | No paging | None |

Anyone at Larkspur Dynamics may declare a SEV1. Nobody is ever penalised for
declaring a severity that is later downgraded.

## 2. Roles

Every declared incident has an incident commander, a communications lead, and
an operations lead. The incident commander must be assigned within ten minutes
of declaration and never also acts as the operations lead.

## 3. Escalation Ladder

If the primary responder does not acknowledge a page within eight minutes, the
alert routes to the secondary responder. If the secondary does not acknowledge
within a further eight minutes, the engineering manager on duty is paged. Any
SEV1 unresolved after ninety minutes escalates to the vice president of
engineering automatically.

The incident bridge is reachable at extension 4-9110 and is opened for every
SEV1 and SEV2.

## 4. Communications Cadence

SEV1 incidents require a status update every thirty minutes until mitigation is
confirmed, even when the update is "no change". SEV2 incidents are updated
every two hours. SEV3 incidents are updated once per business day.

The communications lead owns the status page and the customer mailing list. No
engineer posts externally without routing the wording through that lead.

## 5. Mitigation Before Diagnosis

Restore service first, understand it second. Rollback is always an acceptable
first move. Preserve logs and heap dumps before restarting a process so the
investigation is not starved of evidence.

## 6. Postmortems

A written postmortem is mandatory for every SEV1 and SEV2. SEV1 postmortems are
due within three business days of resolution; SEV2 postmortems are due within
ten business days. Postmortems are blameless and are published to the whole
engineering organisation.

Every action item carries a named owner and a due date no more than
twenty business days out. Open action items are reviewed at the monthly reliability
council chaired by the director of platform.

## 7. Practice

The reliability team runs a game-day exercise each quarter against a
non-production copy of Atlas. Participation is expected at least once per year
for every engineer on a paging rotation.

Contact incident-command@larkspur.example for runbook corrections.
