# ADR-004: Managed Identity Provider

## Context

Authentication is security-critical and not a differentiator for the product.
Building password storage, recovery and cryptography in-house adds risk.

## Decision

Use a managed identity provider for the initial implementation and introduce an
`IdentityProvider` abstraction so Enterprise SSO can be added later.

## Consequences

- Faster, safer MVP.
- No credentials stored in the application.
- Internal `User` and `Organization` records map the verified identity to our
  tenant model.
