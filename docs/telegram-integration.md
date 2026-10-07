# Business Setup follow-up

The `feat/business-setup` branch adds shared database-backed authentication and
Product ownership, integrates the existing Telegram auth bridges, and assigns
Alembic 0002 to the Telegram schema handoff before ownership revision 0003.
See [Business Setup migration notes](business-setup.md) before deploying or
adopting manually created Telegram tables. Earlier handoff/pending statements
below describe the Telegram integration commit before this follow-up.

# Telegram integration MVP

Branch: `feat/telegram-integration`, starting at
`3a84276a6528bc9eb188291d61ca7f09ccad6c84`. This work does not change Agent
contracts, prompts, scoring or the cross-business acceptance criteria.

## Implemented path and current deployment gate

The root webhook verifies the Telegram secret, normalizes normal group text,
then atomically writes an existing `Message`, one existing `AnalysisRun` queue
job and a Telegram receipt. It never invokes Agent/LLM HTTP. The existing worker
claims the existing queue and uses the Telegram adapter to call the production
`analyze_agent(AgentInput)` once for that receipt's target. Existing CSV runs keep
their existing adapter. Qualification/evidence/scoring are implemented only in
the existing Agent. Complete input/output snapshots preserve source quotes,
nullable versions and actual attempt usage. PostgreSQL remains the production DB;
SQLite/fake HTTP is used only for offline regression tests.

Each chat maps to one existing Product and one authenticated owner. No global
product or provider fallback is used. Each topic gets an independent import
batch/conversation; context is selected through the existing context selector
from messages present before the target. Runs process only their target, rather
than reanalyzing the growing chat batch. Unique update IDs and chat/message pairs
prevent duplicate messages/jobs/analyses. Concurrent insertion conflicts return
a retryable error rather than spawning another job.

**This checkout has no implemented authentication or organization/product
ownership.** Backend integration must supply its existing audited services:

```python
app.state.telegram_auth_service = backend_auth_service
# Implements app.auth.contracts.AuthService.current_user(token) -> CurrentUser.
app.state.telegram_product_access = backend_can_access_product
# Callable (CurrentUser, UUID) -> exactly True only for an owned product.
```

No token is treated as a user ID. Missing credentials return 401; absent Backend
auth or product-ownership integration returns 503. Other owners cannot read or
reply to a mapped lead. The mapping's owner is server-derived, never accepted in
the request body. No development authentication adapter ships in production.

The three additive ORM tables are isolated in
`backend/app/integrations/telegram/models.py`. Their exact PostgreSQL DDL is in
[schema.sql](../backend/app/integrations/telegram/schema.sql). **No Alembic
revision was added or migration applied**, to avoid choosing an ownership FK or
revision that conflicts with Roham's integration branch. Roham must incorporate
these tables in his migration chain and connect `owner_user_id`/`approved_by` to
his actual user or organization membership schema. One bot per deployment is
supported; chat IDs are globally unique within that bot's mapping namespace.
Do not deploy this as a public multi-tenant MVP until shared Backend routes also
have ownership enforcement. Existing `/ready` still expects revision `0001` and
must be updated by Backend alongside its approved migration chain.

Telegram-specific UI endpoints below return the frozen public AgentOutput.
Existing shared `/api/v1/leads` schemas still restrict provider_mode to Mock;
Backend must finish its broader real-output/nullable-version contract alignment.
Legacy Analysis columns get `not_executed` for absent versions, whereas the
authoritative Telegram AgentOutput snapshot keeps the true nullable versions.
Existing Usage rows store nullable costs; snapshot usage also preserves nullable
model/price_version/latency. No unknown cost is converted to zero.

## Human approval and delivery

Suggested reply generation is explicit and uses the existing
`generate_suggested_reply()`. Repeating a request returns the stored draft unless
`regenerate=true`. It never qualifies again or sends. Failed provider attempts
are retained in usage and no fake reply is saved.

Only the separate authenticated reply POST sends the exact text approved/edited
by the human. Neither RESPOND nor generating a draft authorizes sending. Sending
never alters qualification, score, decision, evidence or usage. The bot replies
to the original message using `reply_parameters.message_id` and
`allow_sending_without_reply=false`; the topic is included when present. No
parse mode is used, and previews are disabled. These parameters and webhook
secret verification follow the [official Bot API](https://core.telegram.org/bots/api#sendmessage).

Delivery states are `not_sent`, `sending`, `sent`, `failed`. A row records the
approving user, approved text, returned Telegram message ID and failure category.
Repeated identical send after confirmed success returns the existing delivery;
different text after success returns 409. A send is claimed/committed before HTTP,
so concurrent requests cannot both send. Timeouts, malformed success responses,
5xx or process interruption can leave delivery uncertain: never automatically
retry. A human must check the original Telegram thread and Backend must reconcile
the delivery row before explicitly allowing another send. A stuck draft_busy flag
after process interruption likewise needs operator reconciliation. Telegram has
no transaction with our DB; exactly-once external delivery cannot be guaranteed
after a crash. There are no transport retries or automatic outreach.

The failure-handling extension adds hashed send keys, approved-text/status recovery,
server-enforced 429 cooldowns and an explicit analysis retry API. See
[failure handling](failure-handling.md) for migration 0004 and current UI/API
semantics. Use an `Idempotency-Key` on new approval requests; replays never resend
a recorded failed attempt. Uncertain delivery still requires operator reconciliation.

## Fatima's exact API contract

All user endpoints use `Authorization: Bearer <backend-session-token>` and the
existing error envelope: `{"error":{"code":"...","message":"...","details":[]}}`.
Telegram secrets/tokens are never returned to the browser. These endpoints are
additive; UI implementation is out of scope.

| Method/path | Request | Response |
| --- | --- | --- |
| `POST /integrations/telegram/webhook` | Bot update JSON plus `X-Telegram-Bot-Api-Secret-Token` | `{"ok":true,"status":"queued"}`; status may also be ignored/unmapped/duplicate |
| `POST /api/v1/integrations/telegram/chats` | `{"product_id":"<UUID>","telegram_chat_id":-100123}` | 201 mapping: id/product_id/telegram_chat_id/enabled |
| `GET /api/v1/integrations/telegram/leads?limit=20&offset=0` | Authenticated owner | items/total/limit/offset; completed REVIEW/RESPOND leads only |
| `GET /api/v1/leads/{lead_id}/telegram` | Authenticated owner | TelegramLeadOut, including original_message/analysis/delivery |
| `POST /api/v1/leads/{lead_id}/telegram/suggested-reply` | `{"regenerate":false}` | TelegramLeadOut with draft and appended actual reply usage; nothing sent |
| `POST /api/v1/leads/{lead_id}/telegram/reply` | `{"text":"Approved or edited reply"}` | TelegramLeadOut with delivery status and Telegram returned message ID |

Synthetic response shape (values below are illustrative, not a live result):

```json
{
  "id": "<analysis UUID>", "run_id": "<run UUID>", "product_id": "<product UUID>",
  "source": "telegram", "message_id": "<internal message UUID>", "context": [],
  "original_message": {
    "source": "telegram", "update_id": 10, "chat_id": -100123,
    "message_id": 7, "chat_type": "supergroup", "chat_title": "Test group",
    "sender_id": 8, "sender_username": "test_user", "sender_display_name": "User",
    "text": "I need a beginner course", "timestamp": "2026-10-07T09:00:00Z",
    "reply_to_message_id": null, "message_thread_id": 3
  },
  "analysis": {
    "screening": {"is_candidate": true, "reason": "direct_signal"},
    "qualification": {
      "intent":"searching_for_course", "need":"Beginner course search",
      "purchase_intent":0.8,"product_fit":0.9,"need_strength":0.8,
      "urgency":0.0,"confidence":0.9,"response_opportunity":0.8,
      "evidence":[{"message_id":"<internal message UUID>","quote":"I need a beginner course","reason":"Author states a need"}],
      "limitations":[]
    },
    "scoring": {"score": 76, "decision": "RESPOND"},
    "decision_reason": "<actual deterministic reason>",
    "prompt_version": "qualify_real_v1", "scoring_version": "score_v1",
    "usage": [], "suggested_reply": null
  },
  "delivery": {"status":"not_sent","telegram_message_id":null,
    "failure_category":null,"delivery_uncertain":false,"draft_busy":false}
}
```

For a schema-valid synthetic fixture, see
[`contracts/examples/telegram_lead.json`](../contracts/examples/telegram_lead.json).
UI uses analysis.scoring.score/decision, analysis.decision_reason,
analysis.qualification.evidence, analysis.suggested_reply, original_message
sender/chat/text and delivery status. Show the draft, permit editing, and invoke
the reply POST only for an explicit **Approve & Reply** action. Disable sending
while sending/uncertain and after confirmed success. Refresh detail after a 502
to inspect persisted delivery state. Do not label REVIEW as approved.

## Configuration and manual commands — prepared, not executed

Local Telegram settings read root `.env`, then backend `.env`, with environment
variables taking precedence. Keep both files untracked. Required values are
TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET; webhook path is
`/integrations/telegram/webhook`. Production API/worker additionally need
`PROVIDER_MODE=real`, `LLM_PROVIDER=avalai`, OPENAI_API_KEY,
`OPENAI_BASE_URL=https://api.avalai.ir/v1`, `OPENAI_MODEL=gpt-5.6-luna` in their
process environment. Optional pricing stays endpoint-specific. No AI selector
default or production prompt is changed here.

Run in PowerShell; these helpers redact secrets and suppress raw HTTP errors:

```powershell
Set-Location 'C:\git\shared\SignalX'
.\backend\.venv\Scripts\python.exe scripts/telegram.py get-me
```

After Backend auth, migration, queue and HTTPS hosting are ready, replace the
placeholder with the actual public domain and explicitly register:

```powershell
.\backend\.venv\Scripts\python.exe scripts/telegram.py set-webhook --url 'https://<public-backend-domain>/integrations/telegram/webhook'
.\backend\.venv\Scripts\python.exe scripts/telegram.py get-webhook-info
# Recovery: stops webhook delivery; does not discard pending updates.
.\backend\.venv\Scripts\python.exe scripts/telegram.py delete-webhook
```

setWebhook sends url, secret_token, allowed_updates=[message] and
drop_pending_updates=false. No helper sends a chat message. Never interpolate
the real token into PowerShell command text or print it. Telegram's API embeds
the token in its URL; centralized client logging filters redact that URL and
errors never echo it. An operator still owns monitoring and credentials rotation.

## Test-group procedure after Backend gates

1. Verify getMe identifies the expected bot.
2. Create a Telegram test group; add the bot.
3. In BotFather, use `/setprivacy` and disable privacy for this bot if needed.
   Re-add it if Telegram requires that setting to take effect. Grant only the
   permissions needed to read text and send replies. See the [official FAQ](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get).
4. Obtain that group's chat_id from an authenticated update/operator tooling.
5. As the product owner, call the mapping POST with that chat_id/product_id.
6. Register the public HTTPS webhook with the configured secret; inspect info.
7. Send one English/Persian test lead. Check one Message/receipt/queued run exists.
8. Run the existing `python -m app.worker`; verify one target is processed via
   real Agent, exact evidence, score, actual usage and persisted output.
9. Fetch the Telegram leads/detail endpoints; verify correct product/chat/topic.
10. Explicitly request Suggested Reply; verify language/grounding and no send.
11. Edit if needed, then explicitly click Approve & Reply to call the reply POST.
12. Verify the bot replied to the original message in its topic, with the returned
    Telegram message ID, unchanged score/decision and delivery=sent.
13. Redeliver an update offline or through controlled tooling; verify no duplicate
    job/analysis. Do not provoke paid LLM or Telegram quota errors in a live group.

Offline tests use fake Telegram/AvalAI HTTP and SQLite. They verify software
behavior, not live Telegram permissions, PostgreSQL locking or public deployment.
