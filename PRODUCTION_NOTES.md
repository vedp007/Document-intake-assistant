# Production Considerations

This document outlines what would be added to make this application production-ready.

---

## Data & Persistence
- Persist sessions in a database (PostgreSQL or similar) with a session ID keyed to an authenticated user.
- Store conversation history per session with timestamps.
- Add soft-delete and archival for completed documents.

## Security & Privacy
- Encrypt personally identifiable information (PII) at rest and in transit.
- Add authentication and authorisation (OAuth 2.0 / JWT).
- Implement GDPR-compliant data retention and deletion policies.
- Add rate limiting to the API to prevent abuse.

## LLM
- Replace the deterministic mock with a production LLM provider (e.g. Google Gemini, OpenAI).
- Add structured output / function-calling constraints to enforce the `ModelIntakeResponse` schema from the model side.
- Add retry logic and exponential backoff for transient LLM API failures.
- Stream LLM responses token-by-token for better perceived latency.

## Audit & Compliance
- Log all state changes with timestamps and the source of each change (conversation vs. manual edit).
- Add a human review step before any document is presented as final.
- Legal disclaimer escalation: route completed documents to a qualified legal reviewer before dispatch.

## Monitoring & Reliability
- Add structured application logging (e.g. structlog).
- Instrument with metrics (e.g. Prometheus / Grafana): LLM latency, extraction success rate, field completion rates.
- Health check endpoint for orchestration / load balancer.
- CI/CD pipeline with automated test runs on every push.
