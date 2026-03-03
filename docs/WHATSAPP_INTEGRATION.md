# WhatsApp Integration (Meta Cloud API)

StudyBuddy supports a WhatsApp channel using the **Meta WhatsApp Business Platform (Cloud API)**.

## What’s implemented (v1)

- **Inbound messages + outbound replies (text only)**
- **In-app connect flow** using a short code:
  - In StudyBuddy: call `POST /whatsapp/link/code` (requires StudyBuddy auth token)
  - In WhatsApp: user sends `LINK <code>` to your WhatsApp number

## Backend endpoints

- `POST /whatsapp/link/code`
  - Requires `Authorization: Bearer <STUDYBUDDY_SESSION_TOKEN>`
  - Returns `{ code, expires_at, expires_in_seconds }`

- `GET /whatsapp/webhook`
  - Used by Meta to verify the webhook subscription

- `POST /whatsapp/webhook`
  - Receives inbound WhatsApp messages
  - Verifies the `X-Hub-Signature-256` signature
  - Handles `LINK <code>` (connect flow) and normal chat messages

## Environment variables

Copy from `backend/env.example` (or configure in your hosting provider):

- `WHATSAPP_VERIFY_TOKEN`: used for Meta webhook verification handshake
- `WHATSAPP_APP_SECRET`: used to validate incoming webhook signatures
- `WHATSAPP_ACCESS_TOKEN`: bearer token used to send messages via Graph API
- `WHATSAPP_PHONE_NUMBER_ID`: phone number id used in the Graph API messages endpoint

## Local development (webhook testing)

Meta must reach your webhook URL over the public internet.

1) Run the backend locally.

2) Expose it with a tunnel (example using ngrok):

```bash
ngrok http 8000
```

3) In Meta webhook settings, set the callback URL to:
- `https://<your-ngrok-domain>/whatsapp/webhook`

4) Set `WHATSAPP_VERIFY_TOKEN` and enter the same value in Meta’s webhook verification UI.

## Notes / constraints

- Webhooks can be retried; inbound messages are deduplicated by message id.
- v1 ignores non-text WhatsApp messages (images, audio, interactive buttons, etc.).
- Proactive outbound messaging (outside WhatsApp’s customer care window) typically requires **template messages**. That’s intentionally out of scope for v1.

