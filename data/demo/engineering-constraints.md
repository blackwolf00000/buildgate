# Engineering Constraints — Q3 Platform Notes

## Current export pipeline

The existing manual export script reads directly from the primary
transactional database during business hours, which has caused two
brief read-latency incidents in the past quarter when run against large
accounts. Any self-service version of this must read from the reporting
replica, not the primary, or it will need a load test and a DBA sign-off
first.

## File delivery

We do not currently have infrastructure for generating pre-signed, expiring
download links. The nearest existing capability is the internal file-storage
service used for support-ticket attachments, which was not designed for
customer-facing delivery and has no link-revocation feature today.

## Team capacity

The platform team that owns the reporting replica and the file-storage
service is currently staffed at 60% due to two open backend roles. Any work
touching either system should assume reduced review bandwidth through the
end of the quarter.

## Prior related work

A similar "download my invoices" feature shipped last year took roughly
6 engineer-weeks end to end, including a security review cycle, and that
feature only touched billing data (not usage logs or account metadata).
