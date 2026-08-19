# ADR-002: Model Gateway and Inference Gateway

## Context

The platform must support multiple model runtimes (commercial APIs, self-hosted
vLLM, local GGUF) and multiple models. Coupling these concerns makes fallback,
observability and cost accounting fragile.

## Decision

Separate the Model Gateway (which model) from the Inference Gateway (how to
reach a runtime). All provider-specific code lives in adapters behind a
provider-neutral `ModelProvider` protocol.

## Consequences

- Providers are interchangeable without changing callers.
- Fallback is a Model Gateway concern; timeouts and circuit breaking are an
  Inference Gateway concern.
- Adding a new runtime is one adapter and one catalog entry.
