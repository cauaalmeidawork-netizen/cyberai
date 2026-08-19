"""Core kernel: configuration, errors, logging, identifiers, request context.

Nothing in this package may import a web framework, database driver or any
other module of the application. It is the only package everything else is
allowed to depend on.
"""
