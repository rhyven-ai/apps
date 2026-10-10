# Customer Onboarding Monitor

Track required documents, incoming replies and deadlines. The service records
work for an agent; it does not decide whether a document is acceptable or send
customer messages automatically.

1. `action_open` creates a customer with named requirements and a Unix-second deadline.
2. Your agent or authorized connector calls `action_ingest` for a document or
   reply. Use a stable event ID and source reference. Arrival marks a requirement
   as needing review, never accepted.
3. The agent calls `action_claim`, reads the referenced material and uses
   `action_review` to record a finding. Use the current revision to avoid races.
4. Save questions as drafts, link tasks or knowledge records, then acknowledge
   the event after work succeeds.
5. `action_handoff` succeeds only when requirements are accepted and questions
   are resolved. External delivery needs separate user authorization.

The service monitors deadlines while running. It does not scrape email or watch
host folders: connectors or agents submit incoming documents and replies. Start
the Rhyven daemon and configure service autostart if monitoring must survive a
reboot. A stopped computer or daemon cannot detect deadlines until it restarts.

The default package uses an offline durable inbox. Claim leases expire and work
can be retried by another agent. Deduplicate by event ID. `action_pause` pauses
new claims, deadline checks and notifications while preserving incoming events.
State persists under managed `/data`; backup and restore include it. At most
1,000 customers and 10,000 events are retained per collection. A collection is a
trusted group; actor labels are not separate access-control identities.

## Optional runner webhook

MCP cannot wake an agent by itself. A configured runner may receive HTTPS
notifications containing only event ID, customer ID and kind, then claim the
inbox through the normal agent interface. The runner must authenticate the
request and deduplicate its `Idempotency-Key` before scheduling work.

The marketplace package is network-disabled. For a reviewed local deployment,
copy the source package and add `network.connect` and `secrets.read` permissions,
then add these names to `execution.secrets`:

- `RHYVEN_SECRET_ONBOARDING_WEBHOOK`: operator-controlled HTTPS runner URL.
- `RHYVEN_SECRET_ONBOARDING_TOKEN`: bearer token for that runner.

Set both secrets in the runtime daemon environment, rebuild/package the modified
manifest with the same reviewed image digest, and review the new permissions
before installation. Never put secret values in manifests or source. The endpoint
cannot be set through incoming events. Redirects and proxy environment discovery
are disabled. Failed notifications retry at most five times with backoff; they
never remove inbox work. Polling remains available after notification failure.
Do not infer successful task completion from a delivered notification.

```sh
python3 -m unittest discover -s apps/onboarding-monitor/tests -v
docker build -t onboarding-monitor ./apps/onboarding-monitor
```
