# User Questions

A declarative app for durable questions and answers. It supports the optional
Starter Runner for users without a harness. Existing harnesses can also use it
when they need a shared queue of questions. It requires no Docker or model API.

Install `rhyven/user-questions` in the collection shared with its callers.
Use the same three MCP tools as any Rhyven app. Discover the exact input schemas
with `rhyven_describe` before calling actions.

- `action_ask`: save a question, optional context/choices, run/task references,
  recipient and expiry timestamp (Unix seconds; zero means no deadline).
- `object_question_query`: filter pending questions, search text or select a run.
- `object_question_get`: read a question and its current revision.
- `action_answer`: record a nonempty answer using `id` and `expected_revision`.
- `action_cancel`: cancel a pending question.
- `action_expire`: mark a question expired after its declared deadline.

Status, answer and actor metadata cannot be changed through generic updates.
The asking actor cannot answer its own question. Answers after a deadline or
terminal state are rejected. Revision checks reject stale writes. Expiry is
checked at answer time; marking an expired status is an explicit action.

Actor labels are provenance, not authenticated human identity. These questions
collect information; they must not authorize installations or privileged actions.
Starter Runner can ask and read, but its runtime grants cannot answer questions.

A human can use `starter-client.py questions` and `starter-client.py answer ID
"answer"` without running the model service. Include `--collection NAME` before
the command. State follows the collection and its ordinary backup/restore policy.
Source is Apache-2.0.
