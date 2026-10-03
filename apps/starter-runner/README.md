# Starter Runner — optional, for users without a harness

If you already use Codex, Claude Code, Cline, Cursor or another harness, keep
using it. Connect Rhyven through `rhyven_categories`, `rhyven_describe` and
`rhyven_call` to add apps. This runner is not required.

Starter Runner connects a model API to a small planning and knowledge workflow:

1. Split a goal into up to twelve phases with completion criteria.
2. Save the project and tasks in Work Management.
3. Search and write Project Knowledge notes.
4. Pause for a user answer through User Questions.
5. Complete phases and retain results for another agent to inspect.

It does not spawn agents, execute code, browse the web or install apps. A model
can draft and reason over the supplied information; its conclusions still need
review. This is an optional starter harness, not a replacement for a coding agent.

## Requirements and setup

Rhyven 0.5.0, Python 3 for the terminal client, a compatible Docker host, and an
OpenAI-compatible Chat Completions endpoint that returns JSON when instructed.
A hosted model needs your own credentials. Compatible local model servers can
omit `api_key`. Selected goals, answers and retrieved notes go to that endpoint.

Install these apps in the same collection, reviewing their permissions:

```sh
rhyven registry-sync rhyven-ai/registry --anonymous
rhyven --collection starter install rhyven/work-management
rhyven --collection starter install rhyven/project-knowledge
rhyven --collection starter install rhyven/user-questions
rhyven --collection starter install rhyven/starter-runner
```

Each install prints the permission review. Repeat it with `--accept-permissions`
after reviewing that app.

The runner pins Work Management and Project Knowledge to **0.4.0**, and User
Questions to **0.1.0**. A different peer version requires a reviewed runner update.
Dependencies are not installed automatically.

Create a private file, for example `model-config.json`, with mode `600`:

```json
{
  "endpoint": "https://api.openai.com/v1/chat/completions",
  "model": "YOUR_MODEL",
  "api_key": "YOUR_KEY",
  "token_parameter": "max_completion_tokens"
}
```

Use the full endpoint URL. Local servers may require `max_tokens` instead.
HTTP is allowed only for private/local hosts; public endpoints require HTTPS.
A local server must be reachable from the container: container `localhost` is
not the host. Configure a private host address and its listening/firewall settings.
Redirects and ambient HTTP proxies are disabled.

The supervisor must receive the explicitly declared secret when it starts:

```sh
export RHYVEN_SECRET_MODEL_CONFIG="$(cat model-config.json)"
rhyven daemon start
rhyven --collection starter service start rhyven/starter-runner
unset RHYVEN_SECRET_MODEL_CONFIG
```

If the supervisor is already running, arrange a stop/start with that environment
before starting this app. Stopping the supervisor affects its other services.
Never put credentials in goals, app arguments or source control.

Download `starter-client.py` from the
[0.5.0 release](https://github.com/rhyven-ai/rhyven/releases/tag/v0.5.0), or use
`apps/starter-runner/client.py` from this repository:

```sh
python3 starter-client.py --collection starter chat "Draft a release note; ask me about its audience first"
python3 starter-client.py --collection starter status RUN_ID
python3 starter-client.py --collection starter resume RUN_ID
python3 starter-client.py --collection starter cancel RUN_ID
```

The terminal prints pending questions and accepts answers. Closing it leaves the
service running; a pending question stays pending. `resume` reconnects to an
unfinished run. `cancel` prevents subsequent steps but retains committed records.
Existing agents can inspect tasks, notes and questions through the usual interface.

## Limits and state

One active run per instance. Defaults: 16 model requests, 300 seconds of measured
step time and 40,000 reported model tokens. Maximums: 64 requests, 900 seconds,
200,000 reported tokens. Resume does not reset budgets. Each request asks for at
most 2,048 output tokens and has a 20-second network timeout. Context is capped
at 48 KB; responses at 256 KB. A call may exceed a remaining soft time/token budget.
Token usage depends on provider reporting, so this is not a guaranteed spending
cap. Set provider-side spending limits when needed. There is no automatic model
retry. Invalid JSON or an unsupported operation pauses progress as a failed run.

Checkpoints live in the service's `/data/runs`; backup/restore includes them.
Peer mutations use durable request IDs to avoid duplication when retried.
Restart pauses active work until explicitly resumed. Waiting questions never imply
consent, including on expiry. The runner has ask/get grants, not an answer grant.
Actor labels do not authenticate humans; questions are not privileged approvals.

The image has no host mounts or shell grant. Network permission allows egress;
Rhyven does not enforce a per-domain container firewall. No model-supplied tool
name can add a new grant. This app has a 1,000-run retention limit; archive state
before reaching it. Docker image publication currently targets Linux x86-64.

## Develop and test

```sh
python3 -m unittest discover -s apps/starter-runner/tests -v
docker build --iidfile /tmp/starter.id apps/starter-runner
python3 apps/starter-runner/tests/integration.py target/release/rhyven /tmp/starter.id
```

Tests use a deterministic model endpoint and real Rhyven state, not paid model
credentials. The container test covers callbacks, human answers, service restart
and backup/restore. Source is Apache-2.0.
