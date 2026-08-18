# Larkspur Dynamics — Engineering On-Call Handbook

_Fictional sample document for KnowledgeForge demos. Larkspur Dynamics and the
Atlas platform are invented._

## 1. Rotation Structure

Each rotation covers one calendar week and changes hands on Wednesday at 10:00
platform time. Every rotation staffs a primary and a secondary responder.

A rotation needs at least eight participating engineers before it may page
outside business hours, and no engineer is scheduled more than one week in any
five-week cycle. New engineers shadow two full rotations before taking a
primary shift of their own.

## 2. Handoff Protocol

The outgoing primary writes a handoff note covering open alerts, silenced
monitors and their expiry, in-flight changes, and anything expected to fire in
the coming week. The note is posted before a live thirty-minute handoff call.

Silences longer than twenty-four hours must name an owner and a ticket, or the
tooling refuses to create them.

## 3. Service Level Objectives

| Service | Objective |
|------|------|
| Routing API availability | 99.95 percent monthly |
| Routing API p95 latency | Under four hundred milliseconds |
| Plan generation success rate | 99.5 percent of submitted plans |
| Webhook delivery | Ninety-nine percent delivered within sixty seconds |

The monthly availability objective leaves an error budget of
twenty-one point six minutes per month. When sixty percent of the budget is
spent, the team reviews
reliability work at standup. When seventy-five percent is spent, feature
deployments freeze until the budget recovers.

## 4. Alert Triage

Only alerts that are urgent, actionable, and customer-visible may page. Anything
else becomes a ticket alert. A page must be acknowledged promptly and triaged
into a severity within fifteen minutes of acknowledgement.

Any alert that pages more than three times in a single week without producing a
fix is automatically muted and added to the alert review queue. The on-call
review meeting each Thursday deletes or rewrites at least one noisy alert.

## 5. Expectations While On Call

Stay within thirty minutes of a reliable network connection and keep the paging
app in the foreground overnight. Trade shifts freely, but record the trade in
the schedule tool — the tool, not a chat message, is the source of truth.

On-call work takes priority over planned sprint work. Managers plan for roughly
sixty percent capacity from an engineer during their on-call week.

## 6. Compensation

Primary responders receive a stipend of nine hundred dollars per week and
secondary responders four hundred fifty dollars per week. An engineer paged more
than four times between 22:00 and 06:00 in a single rotation earns one
additional recovery day, taken within the following month.

Schedule questions go to oncall-admin@larkspur.example or extension 4-7700.
