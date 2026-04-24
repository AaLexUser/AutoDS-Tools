# WorkOS Auth Research

## Goal

Collect proven references for implementing optional WorkOS-backed auth with minimal custom code in AutoDS.

## Topics

- official WorkOS integration patterns
- GitHub repositories using WorkOS well
- design decisions for local approval gates
- design decisions for optional auth mode
- app-local authorization after external authentication

## Recommended Choices

### Core Architecture

- Use `AUTH_MODE=disabled | workos` as a single top-level switch.
- In `disabled`, keep current local bootstrap and CLI behavior.
- In `workos`, require authenticated browser access for all interactive usage.
- Keep WorkOS responsible for authentication.
- Keep AutoDS responsible for authorization and approval.

### Preferred Integration Shape

- Let Next.js own the browser-facing WorkOS AuthKit session flow.
- Let FastAPI act as a protected resource server.
- Use a small local `users` table with:
  - `id`
  - `workos_user_id`
  - `email`
  - `status = pending | approved | disabled`
  - `is_admin`
- Map WorkOS `user.id` to local `users.id` immediately after login.
- Use local `users.id` as the only downstream `principal_id`.

### Approval Model

- Allowlisted emails in `AUTH_BOOTSTRAP_ADMIN_EMAILS` should always become admins.
- Every other authenticated user starts as `pending`.
- Only `approved` users can create sessions, run jobs, upload files, or use WebSockets.
- Keep approval state in AutoDS, not only in WorkOS metadata.
- Pending users should see only a static approval screen.

### Hosted CLI Model

- Hosted CLI must share the same user namespace as the browser.
- The minimal viable design is app-issued CLI API tokens tied to the same local `user.id`.
- Do not trust self-issued CLI principal headers in hosted mode.
- This is smaller and safer for v1 than implementing a full device-code style login flow.

### Reuse Order

1. Copy the minimal auth/session flow from `workos/next-authkit-example` or `workos/python-authkit-example`.
2. Copy access-control and post-login user-mapping ideas from `workos/next-b2b-starter-kit`.
3. Use `splenwilz/fastapi_auth_starter` only as FastAPI wiring inspiration, not as the architecture source of truth.

## Official References

### WorkOS AuthKit For Next.js

- Docs: [AuthKit Next.js](https://workos.com/docs/authkit/nextjs)
- Repo: [workos/authkit-nextjs](https://github.com/workos/authkit-nextjs)
- Why it matters:
  - lowest-code browser auth flow
  - official middleware and callback shape
  - supported pattern for retrieving access tokens server-side

Useful snippets to study:

- [login route example](https://github.com/workos/authkit-nextjs/blob/main/examples/next/src/app/login/route.ts)
- [callback route example](https://github.com/workos/authkit-nextjs/blob/main/examples/next/src/app/callback/route.ts)
- [account page example](https://github.com/workos/authkit-nextjs/blob/main/examples/next/src/app/account/page.tsx)

### WorkOS Python AuthKit Example

- Docs: [AuthKit Python](https://workos.com/docs/authkit/vanilla/python)
- Repo: [workos/python-authkit-example](https://github.com/workos/python-authkit-example)
- App example: [app.py](https://github.com/workos/python-authkit-example/blob/main/app.py)
- Why it matters:
  - minimal Python-owned callback and sealed-session flow
  - useful reference if we keep more auth logic server-side

### WorkOS FastAPI Guidance

- Guide: [Securing a FastAPI server with WorkOS AuthKit](https://workos.com/blog/securing-a-fastapi-server-with-workos-authkit)
- Why it matters:
  - shows the resource-server model
  - gives a small bearer-token validation shape for FastAPI dependencies

### WorkOS Session And Authorization Docs

- [AuthKit sessions](https://workos.com/docs/authkit/sessions)
- [Roles and permissions](https://workos.com/docs/authkit/roles-and-permissions)
- [Metadata](https://workos.com/docs/authkit/metadata)
- [Users and Organizations](https://workos.com/docs/user-management/users-organizations)
- [Invite-only sign-up](https://workos.com/docs/user-management/invite-only-sign-up)
- [Events data syncing](https://workos.com/docs/events/data-syncing)

What to copy from these docs:

- session helpers, not custom cookie crypto
- one middleware/auth edge
- local business authorization after authentication
- Events API preference if identity sync becomes necessary later

## GitHub Examples

### `workos/next-authkit-example`

- Repo: [workos/next-authkit-example](https://github.com/workos/next-authkit-example)
- Worth copying:
  - minimal Next.js AuthKit shape
  - login/logout flow without extra abstraction
  - protected routes with very little code
- Useful file:
  - [sign-out action](https://github.com/workos/next-authkit-example/blob/main/src/app/actions/signOut.ts)

### `workos/next-b2b-starter-kit`

- Repo: [workos/next-b2b-starter-kit](https://github.com/workos/next-b2b-starter-kit)
- Worth copying:
  - clean separation between authentication and product access decisions
  - org-aware and admin-aware routing ideas
  - local user mapping and sync patterns
- Useful files:
  - [middleware](https://github.com/workos/next-b2b-starter-kit/blob/main/src/middleware.ts)
  - [router/auth entrypoint](https://github.com/workos/next-b2b-starter-kit/blob/main/src/app/router/route.ts)
  - [webhook sync](https://github.com/workos/next-b2b-starter-kit/blob/main/convex/http.ts)
  - [local user mapping](https://github.com/workos/next-b2b-starter-kit/blob/main/convex/users.ts)

### `splenwilz/fastapi_auth_starter`

- Repo: [splenwilz/fastapi_auth_starter](https://github.com/splenwilz/fastapi_auth_starter)
- Worth copying:
  - FastAPI dependency boundary ideas
  - backend route protection shape
- Use carefully:
  - it is a good wiring reference
  - it is not the best source for product-level design decisions
- Useful files:
  - [dependencies.py](https://github.com/splenwilz/fastapi_auth_starter/blob/main/app/core/dependencies.py)
  - [user route](https://github.com/splenwilz/fastapi_auth_starter/blob/main/app/api/v1/routes/user.py)

### `hackerai-tech/hackerai`

- Repo: [hackerai-tech/hackerai](https://github.com/hackerai-tech/hackerai)
- Worth copying:
  - small auth helpers instead of scattered session parsing
  - good example of keeping auth concerns contained
- Useful files:
  - [login route](https://github.com/hackerai-tech/hackerai/blob/main/app/login/route.ts)
  - [get-user-id helper](https://github.com/hackerai-tech/hackerai/blob/main/lib/auth/get-user-id.ts)

### `tambo-ai/thestandupapp`

- Repo: [tambo-ai/thestandupapp](https://github.com/tambo-ai/thestandupapp)
- Worth copying:
  - smaller app middleware pattern
  - explicit auth actions
- Useful files:
  - [middleware](https://github.com/tambo-ai/thestandupapp/blob/main/src/middleware.ts)
  - [auth actions](https://github.com/tambo-ai/thestandupapp/blob/main/src/lib/auth-actions.ts)

### `jcodog/Signalry`

- Repo: [jcodog/Signalry](https://github.com/jcodog/Signalry)
- Worth copying:
  - explicit post-auth gating helper
  - closest public example to our “authenticated but not yet approved” requirement
- Useful file:
  - [org-gating helper](https://github.com/jcodog/Signalry/blob/main/apps/web/src/lib/server/org-gating.ts)

## Decisions To Copy

### Copy

- one auth mode switch at the system boundary
- one official WorkOS session pattern, not custom auth plumbing
- one local `users` table for approval and admin state
- one shared sqlite database for auth and session persistence
- one mapping from external `workos_user_id` to internal `user.id`
- one `approved user required` dependency for FastAPI
- one post-login hook that upserts the local user record
- one deterministic bootstrap rule for the first admin
- one app-issued CLI token model for hosted CLI parity

### Copy Carefully

- WorkOS middleware and callback helpers as-is
- access-token forwarding from Next.js to FastAPI if frontend needs a separate backend
- admin-only route splits from the starter kit
- webhook or Events API sync only if we later need durable identity reconciliation

## Decisions To Avoid

### Avoid

- building a separate auth microservice in v1
- encoding product approval only in WorkOS metadata or roles
- trusting browser-supplied `X-AutoDS-Principal` in hosted auth mode
- trusting CLI self-issued principal headers in hosted auth mode
- using raw WorkOS IDs as long-term business principals everywhere
- mixing anonymous and authenticated logic per route in a way that can drift over time
- scattering auth checks across handlers instead of resolving identity once at the edge

## Notes For AutoDS

### Best Minimal Design For This Repo

- Keep the current architecture simple.
- Add a narrow auth subsystem instead of a separate service.
- Use WorkOS for sign-in.
- Keep user approval in AutoDS.
- Preserve the current `principal_id` ownership model, but back it with local approved users in WorkOS mode.

### Likely Implementation Direction

Frontend:

- replace unconditional browser bootstrap with `GET /api/auth/me`
- redirect unauthenticated users to WorkOS login
- show a pending-approval screen for `pending` users

Backend:

- add an auth dependency layer
- in `disabled` mode, preserve existing principal behavior
- in `workos` mode, resolve current user from WorkOS-backed session or bearer token
- map approved local user to `principal_id`
- reject all session and WebSocket access for non-approved users
- add app-issued CLI tokens mapped to the same local user for hosted CLI access

### Strongest Research Conclusion

The strongest public WorkOS references are in Next.js, not FastAPI.

That means the lowest-risk path is:

- copy the official WorkOS flow for browser auth
- keep FastAPI authorization thin
- build only the minimum local approval layer ourselves
