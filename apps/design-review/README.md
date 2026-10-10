# Design Review

Collect up to three proposals through your existing agent harness, then record
the agent's decision. The app stores review state; it does not call a model API
or start agents itself. It runs as a Python script without Docker or dependencies.

1. Call `action_start` with a question, selected context and constraints.
2. Have the connected harness delegate the returned tasks once, within its model,
   spending and permission limits. Use the returned deadline and output budget.
3. Call `action_submit` for each proposal, including actual usage when available.
4. Call `action_decide` with selected task IDs and a rationale, or reject all.
5. Another agent can retrieve the review through `action_get`.

Proposals cover an approach, assumptions, tradeoffs and checks. Disagreements are
retained. The app checks reported output against the requested budget, but only
the harness can limit model generation or billing. Missing usage is unknown;
reported totals are not a full cost measurement. Cancelled or expired reviews
reject new submissions. Decisions may use a partial set of proposals.

No claims about lower token use or better results are made. Run executable checks
with Change Verifier and store report references in work or knowledge apps.
A harness without delegation can submit its own review, identified honestly as
the same agent. It must not invent independent reviewers.

State is SQLite in the collection's managed app data. Review actions use retry
receipts. Collections are trusted groups; actor labels are not authentication.
The script requests `host.execute`, which is unsandboxed OS-user access. Review
source before installation. At most 1,000 reviews are retained per collection.

```sh
python3 -m unittest discover -s apps/design-review/tests -v
rhyven app validate apps/design-review
rhyven app package apps/design-review --out design-review.rhyven.json
```
