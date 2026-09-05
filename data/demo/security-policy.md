# Security Policy Excerpt — Customer Data Handling

## Data classification

All customer-account fields are tagged `public-export`, `customer-visible`,
or `internal-only`. Fields tagged `internal-only` (examples: internal risk
score, support-agent notes, fraud-review flags) must never be included in any
export, report, or API response that a customer or their delegate can access,
directly or indirectly.

## Self-service export features

> Any self-service feature that lets a customer generate their own data
> export must pass a field-level classification review before launch, and
> that review must be signed off by the Data Governance team, not by
> Engineering alone. This applies regardless of how the export is triggered
> (manual button, API, or scheduled job).

## Bulk data movement

Any feature that produces a downloadable file containing more than 90 days of
historical customer data must run through the Bulk Export approval process,
which includes a rate-limit review and a takedown/revocation mechanism for
already-issued download links.

## Authentication for sensitive actions

Actions that generate or expose account-level data extracts require
step-up authentication (a fresh session, not a long-lived cookie) even for
already-authenticated users.
