# QA History — Related Features

## Download My Invoices (shipped last year)

This is the closest prior feature to the proposed data-export button. Notable
issues found during QA:

- Initial implementation generated the file on the primary database and was
  rejected in review before reaching QA, per the same primary-vs-replica
  concern raised in the engineering notes.
- QA found that large accounts (500+ invoices) caused the synchronous
  generation request to time out at the API gateway's 30-second limit. The
  shipped version was reworked to be asynchronous with an email notification.
- A field-classification bug let one internal billing-adjustment note leak
  into a small number of generated invoice PDFs before it was caught in QA;
  this is the specific incident that led to the Data Governance sign-off step
  now required in the security policy.

## Regression risk

Any new export feature that reuses the same "generate file, deliver a link"
shape should explicitly test the 30-second gateway timeout path and the
field-classification boundary, since both have caused real production issues
in the one prior comparable feature.
