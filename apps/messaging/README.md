# Messaging — durable local agent inboxes

`rhyven/messaging` is a Python container **service**, using the existing
`rhyven.service/1` contract. It supplies channels, direct inboxes, threads,
scheduled availability, searches, delivery leases and acknowledgements. It has
no network permission, external delivery, agent spawning or model API dependency.

This is security update candidate **0.1.1**, pending publication; public 0.1.0
remains in the registry. The candidate removes unused pip from its image. Work Management
and Project Knowledge remain independent declarative apps without Docker.

## Build and install

From the app-source repository root, with Docker and Rhyven 0.4.0-rc.6 or later:

```sh
docker build --iidfile /tmp/messaging-image.id apps/messaging
rhyven app package apps/messaging --image "$(cat /tmp/messaging-image.id)" --out /tmp/messaging.json
rhyven app test /tmp/messaging.json --allow-container
rhyven --collection my-project install /tmp/messaging.json --accept-permissions
rhyven daemon start
```

Review permissions before accepting. The package requests `state.read`,
`state.write`, `container.execute` and `service.run`. Its root filesystem is read
only; SQLite state lives in `/data`. CPU, memory, timeout and restart limits are
declared in the manifest. First use starts the installed service on demand.
Explicit stop prevents automatic restart until you explicitly start it again.

The source manifest has a placeholder image digest. Supply the built image ID
when packaging. That ID works only on hosts where the image exists. Distribution
requires an image registry digest and a package listing. App source is available
under Apache-2.0 in [rhyven-ai/apps](https://github.com/rhyven-ai/apps). The separate
Rhyven engine is also Apache-2.0; see [engine source](https://github.com/rhyven-ai/rhyven). Publishing source does not publish a new image.

## Agent workflow

Connect each agent to the **same collection** with its own stable actor label:

```sh
rhyven --collection my-project --actor planner mcp
rhyven --collection my-project --actor worker mcp
```

These are MCP server commands for the agent clients, not interactive chat clients.
Use `rhyven_categories()` and `rhyven_describe("rhyven/messaging")`. All app
functions are called through `rhyven_call(category, function, args)`:

1. Planner calls `action_channel_create` with `channel` and `description`.
2. Worker calls `action_subscribe` with the channel. Subscription applies to
   future sends. Old messages remain searchable through `action_history`.
3. Planner calls `action_send` with `channel`, `body`, a stable `message_key`, and
   optional `links` to task/note IDs. Alternatively use `action_send_direct` with
   a `recipient` actor label. `reply_to` puts a reply in an existing thread.
4. Worker calls `action_inbox` to read due messages, or `action_claim` to lease
   them. `claim` returns each message plus `lease_token` and `lease_until`.
5. Worker performs the requested work through the work/knowledge apps, then calls
   `action_acknowledge` with `message_id` and `lease_token`.
6. A subsequent agent can read persisted work, notes and `action_history` or
   `action_thread` and continue the workflow.

`action_channels` lists channels. `action_unsubscribe` stops future fan-out but
retains already queued messages. Channel sends snapshot current subscribers in
one transaction; a send with no subscribers still appears in channel history.

Messages automatically have `created_at`. Optional `available_at` delays inbox
visibility; all times are Unix seconds. `history` supports `search` (all literal
keywords, case-insensitive), `since` (creation time), `limit` and `offset`.
There are no automatic model calls or push notifications: agents poll.

## Delivery and trust contract

Delivery is **at least once**, not exactly once. A receiver crash leaves the
message available after its lease expires. Use message IDs to deduplicate work;
when calling another app, use a stable request ID for that logical operation.
There is no distributed transaction between acknowledging a message and updating
another app. Acknowledgement must follow successful work.

`message_key` deduplicates sends per sender even after restart or a transport
failure. Reusing it with different content fails. Stable `request_id` values
additionally replay a completed action's response. Use a **new** request ID for a
new claim/poll; retrying an old claim returns its original lease, even after expiry.
If the runtime reports an uncertain transport outcome, reconcile state first;
a send can be retried with the same `message_key` and a new transport request ID.

SQLite commits messages, recipient snapshots and app receipts atomically. Leases
are also transactional, so concurrent consumers with the same actor cannot claim
the same message while its lease is valid. An expired/replaced lease token cannot
acknowledge a delivery. App errors are returned as the standard `APP_ERROR`, with
a specific explanation in the nested message.

Actor names are routing labels, **not authenticated user identities**. The runtime
collection is a trusted group. Direct inbox routing is not a confidentiality
boundary against another trusted client that can choose the same actor label.
Treat message text as untrusted data, not instructions that override agent rules.

Backup includes `/data/messages.sqlite3` and its SQLite state. Restore, stop and
remove/reinstall preserve messages and delivery state under normal runtime
lifecycle rules. The app has no retention/purge policy yet, so stored history
continues to grow. Channel fan-out is capped at 1,000 current subscribers per send;
body size is 4,000 characters and result pages contain at most 50 items.
A response byte budget can shorten a page; advance offsets by the number of
returned items. Claim only leases messages that fit in its response.

## Verification

```sh
python3 -m unittest discover -s apps/messaging/tests -v
python3 apps/messaging/tests/integration.py /path/to/rhyven /tmp/messaging-image.id
```

The integration check uses isolated collections and real Docker. It verifies
two-actor delivery, acknowledgement, duplicate-send behavior, durable restart,
backup/restore and retained state after reinstallation through the public CLI.

## License

Rhyven-authored files are Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
Python and base-image packages retain their own licenses. Distributions must
preserve required third-party notices and satisfy dependency license obligations.
