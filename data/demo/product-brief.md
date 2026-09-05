# Product Brief — Customer Self-Service Data Export

## Summary

Enterprise customers currently request their account data exports by emailing
support, who manually run a script and email back a CSV. Support handles
roughly 40 of these requests per month. The ask is a self-service "Export My
Data" button in the customer portal that generates and emails the export
without a human in the loop.

## Target users

Portal admins at enterprise customer accounts (the account owner role and
above). Approximately 1,200 accounts currently qualify.

## Expected outcome

Reduce support ticket volume for data-export requests by at least 80%, and
cut the turnaround time from an average of 3 business days to under 10
minutes.

## Known constraints

- The export must include the same fields as the current manual CSV: account
  metadata, usage logs for the trailing 12 months, and billing history.
- Exports must be delivered as a downloadable link, not a raw email
  attachment, because some exports exceed 25MB.
- The feature must respect existing per-field data classification tags; some
  fields are marked "internal-only" and must never appear in a customer-facing
  export.

## Out of scope for this request

Scheduled/recurring exports, exports for sub-accounts, and any export format
other than CSV are explicitly out of scope for this iteration.
