"""HTTP layer.

Routers here are deliberately thin: validate, resolve context and permissions,
call exactly one application service, map the result. Any decision about
models, prompts, retrieval or policy living in this package is an architecture
violation - that logic belongs to the AI Orchestrator (M2).
"""
