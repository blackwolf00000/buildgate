# Architecture Notes — Customer Portal

## Current portal stack

The customer portal is a server-rendered app backed by the primary
transactional database, fronted by a shared API gateway used by both the
portal and internal admin tools. There is no existing background-job queue
wired into the portal service today; long-running work is currently handled
by a separate internal ops service.

## Data access boundaries

Portal backend services have read access to the primary database but not to
the reporting replica; only the internal analytics service currently has a
replica connection. Wiring a new consumer to the replica requires a network
ACL change and is not a same-sprint change.

## Prior incidents

One of the two read-latency incidents mentioned in the engineering notes was
traced to an unindexed query against the usage-logs table for an account with
several years of history. Any new feature reading that table at export scale
should assume it needs a new index or a pre-aggregation step.

## Open architectural question

It has not yet been decided whether export generation should be synchronous
(held open request) or asynchronous (job queue plus notification). No job
queue currently exists in the portal service's dependency graph.
