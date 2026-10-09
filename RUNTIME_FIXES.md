# Runtime fixes

`python3 restore_workspace.py` verifies the original workspace, applies `RUNTIME_FIXES.patch`, and verifies all six resulting file hashes in `RUNTIME_FIXES.json`. `AWS_DEPLOY.sh` already invokes this restore command before starting a new main release, so these fixes are included in that deployment path. Repeated restore is supported; unexpected local source changes or a partial update stop the operation instead of being overwritten.

Changes: saved and accepted photo completion triggers the daily reward; failed requests can be retried without duplicating challenge logs; stale account/cycle/day responses are ignored; already-paid rewards do not show another credit. Logout, password change and password reset return an empty HTTP 204 body to avoid the JSON-null/Content-Length protocol error.

Validation on a fresh restored workspace: 22 frontend checks and 3 authentication response tests passed. Fresh and repeated restoration both passed. Earlier local synthetic HTTP verification passed 20 startup/signup/login/session/logout checks. AWS execution and external HTTPS are pending EC2 creation; these results do not claim server deployment is complete. Existing unrelated frontend tests have 11 baseline failures, recorded separately.

Run from the repository root after restore:

```sh
node --test tests/frontend/daily_reward_recovery.test.cjs tests/frontend/signup_payload.test.cjs tests/frontend/signup_validation.test.cjs tests/frontend/api_response_contract.test.cjs tests/frontend/session_recovery.test.cjs
.venv/bin/python -m unittest tests.test_auth_empty_responses -v
```

The existing modern UI is served at `/?workspace=home`; the default `/` still redirects to the separate retro entry page. No API keys, model binaries or databases are included in these fixes.
