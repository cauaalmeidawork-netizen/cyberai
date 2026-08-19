"""Domain modules (bounded contexts) of the modular monolith.

A module may import ``cyberai.core`` and ``cyberai.platform`` freely, but may
only reach another module through its public interface. The contracts in
``.importlinter`` fail the build when that rule is broken, which is what keeps
extraction into separate services possible later.
"""
