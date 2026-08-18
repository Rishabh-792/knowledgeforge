# Atlas Routing Platform — Release Notes

_Fictional sample document for KnowledgeForge demos. Atlas is an invented
logistics SaaS product by the invented company Larkspur Dynamics._

## 4.3 "Meridian" — released 14 May 2026

**Features**
- Multi-depot balancing: Atlas now spreads stops across depots by projected
  finish time rather than straight-line distance. Pilot fleets saw average plan
  computation drop by thirty-eight percent.
- Curbside time windows can be set per customer in fifteen-minute granularity.
- New `route.sealed` webhook event fires once a plan is locked for the day.

**Fixes**
- Fixed a defect where a driver rejecting the final stop of a route left the
  vehicle marked as active overnight.
- Corrected daylight-saving drift in the shift-planning calendar.

## 4.2 "Kestrel" — released 3 February 2026

**Features**
- Webhook delivery now retries with exponential backoff up to six attempts over
  roughly two hours before a payload is parked in the dead-letter queue.
- Dispatcher console adds a heat overlay for chronic late-delivery clusters.
- Driver app offline cache extended to seventy-two hours of pre-planned routes.

**Fixes**
- Resolved an issue where importing more than ten thousand stops in one CSV
  truncated the final batch silently.
- Reduced dispatcher console memory use on long sessions by about forty percent.

## 4.1 — released 21 October 2025

**Features**
- SCIM provisioning for single sign-on, so directory changes flow into Atlas
  within five minutes instead of at nightly sync.
- Per-vehicle CO2 estimates on completed routes.

**Fixes**
- Fixed incorrect distance rounding on routes crossing a metric/imperial
  regional boundary.

## 4.0 — released 8 July 2025

**Breaking change.** The `/v1/routes` endpoint is deprecated in favour of
`/v2/plans`. Version 1 continued to answer requests for twelve months after
this release and was switched off on 8 July 2026.

**Features**
- New constraint solver, replacing the heuristic planner used since 2.x.
  Benchmarks show a nine percent reduction in total distance driven on fleets
  above one hundred vehicles.
- Live re-planning latency target lowered to under ninety seconds from the
  moment a disruption is reported.

## 3.9 — released 4 March 2025

**Features**
- Depot-level holiday calendars.
- Bulk driver import from spreadsheet.

**Fixes**
- Fixed a crash in the mobile app when a route contained zero stops.

## Support Windows

Each major version receives security fixes for eighteen months after the next
major version ships. Customers on the Enterprise plan may request a single
six-month extension through their account team at atlas-support@larkspur.example.
