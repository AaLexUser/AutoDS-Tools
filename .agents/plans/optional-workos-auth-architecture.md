# Optional WorkOS Auth Architecture Plan

## Status

- Draft
- Date: 2026-04-23

## Goal

Add an optional authentication and authorization layer backed by WorkOS.

When auth is enabled:

- every browser user must authenticate before using the system
- only users approved by a local administrator can interact with the system
- session ownership and access control remain predictable and explicit

When auth is disabled:

- current local and development behavior continues to work
- anonymous browser bootstrap and CLI principal token flow remain available

## Research-Validated Direction

Based on external references collected in [workos-auth-research.md](/Users/aleksejlapin/Work/AutoDS-Tools/.agents/references/workos-auth-research.md), the preferred minimal design is:

- Next.js owns the browser-facing WorkOS AuthKit flow
- FastAPI acts as a protected resource server plus local authorization layer
- AutoDS keeps a local `users` table for approval and admin state
- local `user.id` becomes the only downstream `principal_id` in auth mode

This is preferred over a larger custom server-side auth subsystem because it reuses more official WorkOS code paths and minimizes custom auth logic.

## Resolved Product Decisions

- pending users should see only a static approval screen
- allowlisted bootstrap admin emails should always become admins
- hosted CLI must share the same hosted session namespace as the browser
- auth and session persistence should use one sqlite database

## Current State

The current trust model is lightweight and local-first:

- browser identity is created by `POST /api/bootstrap`
- the backend stores a random `autods_pid` cookie
- the CLI persists a local principal token and sends it via `X-AutoDS-Principal`
- session access is scoped by `principal_id`

Relevant code:

- [apps/server/src/autods_web/api.py](/Users/aleksejlapin/Work/AutoDS-Tools/apps/server/src/autods_web/api.py)
- [apps/frontend/src/lib/api/client.ts](/Users/aleksejlapin/Work/AutoDS-Tools/apps/frontend/src/lib/api/client.ts)
- [apps/cli/src/autods_cli/main.py](/Users/aleksejlapin/Work/AutoDS-Tools/apps/cli/src/autods_cli/main.py)
- [packages/autods/src/autods/sessions/service.py](/Users/aleksejlapin/Work/AutoDS-Tools/packages/autods/src/autods/sessions/service.py)

## Design Decision

Do not introduce a separate standalone auth microservice in v1.

Instead:

- build an auth subsystem inside the existing FastAPI server
- keep clean module boundaries so it can be extracted later if needed
- treat WorkOS as the authentication provider
- keep authorization and approval logic local to AutoDS

Reasoning:

- the repo currently has a single backend trust boundary
- a real extra service would add distributed state, extra deployment complexity, and more failure modes
- the main system already uses `principal_id` as the ownership boundary, which is the correct place to attach approved user identity

## Principles

- performance first: auth checks must be cheap and avoid repeated remote calls
- reliability first: the system must fail closed when auth is enabled
- predictable behavior: access decisions must come from a small set of explicit rules
- local authorization: approval state must live in AutoDS, not only in WorkOS
- backwards compatibility: dev mode must remain simple

## Scope

### In Scope

- optional WorkOS login for browser users
- local approved-user registry
- admin approval workflow
- protected HTTP and WebSocket access
- auth mode toggle
- audit logging for access-control actions

### Out of Scope For V1

- separate deployable auth microservice
- full RBAC beyond `admin` and `approved user`
- SCIM provisioning
- multi-tenant organization support

## Target Modes

Two operating modes:

### `AUTH_MODE=disabled`

Use current behavior.

- browser can bootstrap anonymous identity
- CLI can use persistent local principal token
- no approval workflow

### `AUTH_MODE=workos`

Strict hosted mode.

- anonymous browser bootstrap is disabled
- browser users must authenticate through WorkOS
- only approved users can access protected endpoints
- raw `X-AutoDS-Principal` is not trusted for hosted browser traffic
- hosted CLI must resolve to the same local user identity as the browser

## High-Level Architecture

### Components

- `frontend`
  - WorkOS AuthKit integration
  - login redirect
  - auth state bootstrap
  - pending approval page
  - admin user approval UI
- `server auth subsystem`
  - bearer token or server-side identity validation
  - current-user resolution
  - approval enforcement
  - admin-only endpoints
- `local auth storage`
  - user records
  - approval status
  - admin flags
  - audit log
- `session subsystem`
  - unchanged ownership model
  - `principal_id` becomes stable approved local user id in auth mode

### Proposed Server Modules

- `apps/server/src/autods_web/auth/config.py`
- `apps/server/src/autods_web/auth/models.py`
- `apps/server/src/autods_web/auth/storage.py`
- `apps/server/src/autods_web/auth/provider.py`
- `apps/server/src/autods_web/auth/service.py`
- `apps/server/src/autods_web/auth/deps.py`

These modules should isolate auth concerns from the large `api.py` file and keep extraction feasible later.

## Identity Model

### WorkOS Responsibility

WorkOS is responsible for:

- authenticating the human user
- returning a stable external identity
- providing verified claims such as email and profile data

### AutoDS Responsibility

AutoDS is responsible for:

- mapping WorkOS identities to local users
- deciding whether the user is approved
- deciding whether the user is an admin
- issuing and validating the application session
- enforcing access control on HTTP and WebSocket routes

This separation is mandatory. Authentication and authorization must not be conflated.

## Data Model

Add local auth tables separate from the current session storage model.

### `users`

- `id`
  - internal UUID
- `workos_user_id`
  - unique, nullable for future extensibility
- `email`
  - unique normalized email
- `display_name`
- `status`
  - `pending | approved | disabled`
- `is_admin`
  - boolean
- `created_at`
- `updated_at`
- `approved_at`
  - nullable
- `approved_by`
  - nullable local user id

### `auth_sessions`

- `id`
  - opaque session id
- `user_id`
- `expires_at`
- `created_at`
- `last_seen_at`

Keep this table local so requests do not depend on live WorkOS validation after login.

### `cli_tokens`

- `id`
- `user_id`
- `token_hash`
- `label`
- `last_used_at`
- `expires_at`
- `created_at`

These tokens allow hosted CLI access while still resolving to the same local user as the browser.

### `audit_log`

- `id`
- `actor_user_id`
- `action`
  - for example `user.approved`, `user.disabled`, `auth.login`, `auth.logout`
- `target_user_id`
- `metadata_json`
- `created_at`

## User States

### `pending`

- user authenticated successfully
- user cannot create sessions
- user cannot upload files
- user cannot run jobs
- user cannot connect to session WebSockets
- user can only view a static pending-approval screen

### `approved`

- full normal access

### `disabled`

- login may succeed at WorkOS level
- AutoDS denies application access

## Bootstrap Admin Strategy

V1 needs a deterministic way to create the first administrator.

Use an email allowlist:

- `AUTH_BOOTSTRAP_ADMIN_EMAILS=admin@example.com,owner@example.com`

On successful login:

- if the email is in the bootstrap allowlist, mark the user as both `approved` and `is_admin=true`

This avoids manual database editing during first deployment and ensures designated operator accounts always retain admin access.

## Request Flow

### Browser Flow In `AUTH_MODE=workos`

1. Frontend requests `GET /api/auth/me`.
2. If there is no valid auth state, frontend redirects to the WorkOS login route.
3. WorkOS redirects back to the application callback route.
4. Next.js completes the AuthKit flow and resolves external identity.
5. AutoDS upserts the local user record.
6. AutoDS applies bootstrap-admin rule if eligible.
7. Frontend calls `GET /api/auth/me` again.
8. If user status is `pending`, show approval screen.
9. If user status is `approved`, allow normal app initialization.

### Protected API Request Flow

1. Resolve authenticated user from the WorkOS-backed session or validated bearer token.
2. Load local user.
3. Require `status=approved`.
4. Use local `user.id` as `principal_id`.
5. Continue to session service and existing ownership logic.

### WebSocket Flow

1. Resolve local app session using the same auth dependency logic.
2. Require `approved` status.
3. Load session by local `principal_id`.
4. Reject with explicit close code on failure.

The current WebSocket path must not trust raw principal cookies directly in auth mode.

## API Plan

### Public Auth Endpoints

- `GET /api/auth/me`
  - returns auth mode, user identity, approval state, and admin flag
- `GET /api/auth/login`
  - starts WorkOS login flow
- `GET /api/auth/callback`
  - completes WorkOS login flow
- `POST /api/auth/logout`
  - clears local app session or AuthKit session

### Admin Endpoints

- `GET /api/admin/users`
  - list users and statuses
- `POST /api/admin/users/{id}/approve`
  - approve pending user
- `POST /api/admin/users/{id}/disable`
  - disable user
- `POST /api/admin/users/{id}/make-admin`
  - optional for v1, useful but not required initially

### Existing Session Endpoints

Current session endpoints remain the same externally, but access depends on auth mode:

- in disabled mode, use current principal behavior
- in WorkOS mode, derive `principal_id` from approved local user identity

### CLI Auth Endpoints

For hosted CLI support in v1, add app-issued CLI API tokens tied to the same local user record used by the browser.

Recommended endpoints:

- `POST /api/auth/cli/tokens`
  - create a CLI token for the current approved user
- `GET /api/auth/cli/tokens`
  - list active CLI tokens for the current user
- `DELETE /api/auth/cli/tokens/{id}`
  - revoke a CLI token

## Frontend Plan

Replace browser bootstrap behavior in auth mode.

### Current

- client automatically calls `POST /api/bootstrap`

### Target

- client first calls `GET /api/auth/me`
- if unauthenticated, redirect to login
- if authenticated but pending approval, render pending state
- if approved, proceed with normal session and dataset UI

### UI States

- loading auth state
- login required
- pending approval
- approved application
- unauthorized or disabled account

### Admin UI

Admin UI is a v1 requirement.

Recommended minimal screen:

- route such as `/admin/users`
- table of users with `pending`, `approved`, and `disabled` status
- actions:
  - `Approve`
  - `Disable`

Pending users should not see any partial product UI. They should only see a static approval-waiting screen.

## CLI Plan

### Disabled Mode

No change.

### WorkOS Mode

Hosted CLI is required in v1.

Requirements:

- CLI and browser must resolve to the same local user identity
- CLI must see the same hosted sessions as the browser
- the current self-issued `X-AutoDS-Principal` model cannot be trusted in hosted mode

Recommended minimal design:

- browser users authenticate with WorkOS
- approved users can mint app-issued CLI API tokens from the hosted app
- CLI sends that token to the backend
- backend resolves the token to the same local `user.id`
- backend uses local `user.id` as `principal_id`

This gives browser and CLI a shared session namespace without requiring a full device flow in v1.

## Security Rules

- fail closed when `AUTH_MODE=workos`
- never trust browser-provided `X-AutoDS-Principal` in hosted mode
- never trust CLI self-issued principal headers in hosted mode
- keep session cookies `HttpOnly`
- use secure cookies in production
- normalize and compare email addresses carefully
- use local app sessions so request authorization does not depend on repeated remote WorkOS round trips
- enforce the same access rules for HTTP and WebSocket endpoints
- record approval and disable actions in audit logs

## Persistence Strategy

The current session storage is file and sqlite based under the AutoDS home directory. Auth storage should use the same local persistence style initially to keep operations simple.

Recommended approach:

- keep auth and session persistence in one sqlite database
- add auth-related tables alongside the existing session persistence model
- keep auth and session modules logically separate even though they share storage

This is enough for v1, keeps operations simple, and still allows later extraction if needed.

## Refactoring Plan

### Phase 1: Isolate Principal Resolution

Goal:

- move identity resolution out of `api.py` helper functions into a dedicated auth dependency layer

Deliverables:

- shared request auth resolver
- shared WebSocket auth resolver
- no behavior change yet

### Phase 2: Add Local User Registry

Goal:

- create local auth models and persistence

Deliverables:

- `users`
- `auth_sessions`
- `cli_tokens`
- `audit_log`
- storage tests

### Phase 3: Add WorkOS Login

Goal:

- support browser login in optional mode

Deliverables:

- auth config
- login endpoint
- callback endpoint
- Next.js AuthKit integration
- `GET /api/auth/me`

### Phase 4: Enforce Approval

Goal:

- ensure only approved users can interact with the system

Deliverables:

- protected HTTP routes
- protected WebSocket routes
- pending user response handling
- disabled user handling

### Phase 5: Admin Approval Workflow

Goal:

- allow approved admins to manage user access

Deliverables:

- admin-only APIs
- audit log writes
- simple admin frontend page
- CLI token management for approved users

### Phase 6: Cleanup And Hardening

Goal:

- remove dead bootstrap paths from hosted mode and validate failure behavior

Deliverables:

- production cookie settings
- more explicit errors
- docs and env examples
- integration tests

## Testing Plan

### Unit Tests

- auth config parsing
- user upsert logic
- approval state transitions
- bootstrap admin rule
- session cookie validation
- CLI token validation
- request dependency behavior

### API Tests

- unauthenticated request rejected in WorkOS mode
- pending user cannot access session APIs
- approved user can create and use sessions
- disabled user is rejected
- admin endpoints require admin role
- hosted CLI token resolves to the same user namespace as the browser
- WebSocket access uses the same authorization rules

### Regression Tests

- disabled mode preserves current browser bootstrap behavior
- disabled mode preserves current CLI principal token behavior

## Operational Notes

### Environment Variables

Expected additions:

- `AUTH_MODE`
- `WORKOS_CLIENT_ID`
- `WORKOS_API_KEY`
- `WORKOS_REDIRECT_URI`
- `AUTH_BOOTSTRAP_ADMIN_EMAILS`
- `AUTH_COOKIE_SECURE`

### Observability

Add structured logs for:

- login success and failure
- pending-user denial
- disabled-user denial
- admin approval actions
- admin disable actions

## Recommended Next Step

Start with Phase 1 and Phase 2 only.

That gives the project:

- a clean auth boundary
- a local authorization model
- minimal risk to existing behavior

Then add WorkOS integration once the internal ownership model is already decoupled from anonymous bootstrap.
