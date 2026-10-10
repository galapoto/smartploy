# SmartPloy identity and tenancy

SmartPloy keeps the canonical job corpus global while user-private data is scoped
to a SmartPloy profile resolved from a trusted authenticated principal.

## Identity model

A SmartPloy user is not the same thing as an identity-provider subject.

```text
smartploy_users
    |
    +-- smartploy_user_identities
    |      Cloudflare Access issuer + subject   (temporary)
    |      Obum Identity issuer + subject       (target)
    |      future enterprise identity aliases
    |
    '-- smartploy_user_profiles
           |
           +-- profile facts
           +-- preparations
           +-- applications/events
           '-- future private artifacts/preferences
```

Authorization uses the verified `(issuer, subject)` tuple. Email is only an
attribute and is never sufficient to merge accounts automatically.

## Shared versus private data

Shared:
- normalized jobs;
- source observations;
- source health;
- continuous source polling.

Private:
- profile evidence;
- profile-specific scores/rankings;
- application preparation packages;
- CRM applications and events;
- ObumAI preparation-job projections;
- future CV/cover-letter artifacts and user preferences.

A browser request cannot supply `profile_id` to select another user's private
state. The server resolves the authenticated principal to its profile.

## Cloudflare-to-Obum-Identity migration

Cloudflare Access is a temporary authentication source. It must not define the
long-term SmartPloy account identity.

When Obum Identity is live:

1. Record the existing SmartPloy `user_id` from the authenticated session.
2. Obtain the verified Obum Identity issuer/subject through the new OIDC login.
3. Explicitly link that identity alias to the existing SmartPloy user.
4. Verify both identity paths resolve to the same `user_id` and `profile_id`.
5. Only then remove the customer-facing Cloudflare Access application.

Never auto-link by email.

### Identity link command

Provide the new trusted identity through environment variables:

```bash
export SMARTPLOY_DATABASE_URL='postgresql://...'
export SMARTPLOY_IDENTITY_ISSUER='https://auth.obumai.com'
export SMARTPLOY_IDENTITY_SUBJECT='verified-provider-subject'
export SMARTPLOY_IDENTITY_EMAIL='user@example.com'
export SMARTPLOY_IDENTITY_AUTH_SOURCE='oidc'

python scripts/manage_identity.py link --user-id 'usr-...'
```

The command does not print the provider subject, email, DSN, or tokens.

## Legacy default profile

Existing single-owner data remains under profile `default`. It is not assigned
to the first person who logs in.

After the intended owner's future Obum Identity principal is verified, claim it
explicitly:

```bash
python scripts/manage_identity.py claim-legacy --profile-id default
```

The claim fails if another SmartPloy user already owns the legacy profile. It
also fails rather than replacing a newly generated profile that already contains
private facts, preparations, or applications.

## Future Obum Identity integration

The target authentication source is OIDC Authorization Code + PKCE through
`auth.obumai.com`.

SmartPloy should receive a verified server-side principal and establish its own
host-only session. The tenancy layer does not depend on Cloudflare-specific
claims, so replacing the authentication middleware does not change user/profile
authorization rules.

Global logout should invalidate the central Obum Identity session and each
application session through the supported OIDC logout mechanisms.


## SmartPloy OIDC application session

SmartPloy supports four authentication modes:

- `disabled`: local development only;
- `cloudflare`: current temporary customer gate;
- `hybrid`: Obum Identity session first, Cloudflare Access fallback second;
- `oidc`: Obum Identity session only.

Obum Identity uses:

- issuer: `https://auth.obumai.com`;
- Authorization Code flow;
- PKCE S256;
- scopes: `openid profile email`;
- exact callback: `https://smartploy.obumai.com/auth/callback`.

Authlib performs OIDC discovery, state/nonce handling, PKCE and ID-token validation. Temporary
state/nonce/code-verifier data is stored in PostgreSQL through the Authlib cache interface.

After callback, SmartPloy creates its own opaque application session. The browser receives only
`__Host-smartploy_session`; PostgreSQL stores its SHA256 hash. Provider access, refresh and ID tokens
are not stored in the SmartPloy application-session table.

## Cutover sequence

1. Keep committed production mode `cloudflare`.
2. Deploy `auth.obumai.com` and create the SmartPloy OIDC client.
3. Link the existing owner's Obum Identity principal to the existing SmartPloy user/profile.
4. Change production policy to `hybrid`.
5. Verify login, callback, tenant identity, logout, and existing Cloudflare fallback.
6. Verify silent SSO from ObumAI to SmartPloy.
7. Change production policy to `oidc`.
8. Run live acceptance while Cloudflare Access still exists as an emergency reversible control.
9. Remove the customer-facing SmartPloy Cloudflare Access application only after OIDC production
   acceptance and release evidence pass.

Cloudflare Tunnel, DNS, TLS, WAF, DDoS/rate limiting and edge protections remain.
