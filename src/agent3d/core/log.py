"""CLI logging. The product name comes from identity (never hard-code it)."""
from .. import identity


def banner(module, command):
    print(f"== {identity.title()} :: {module} {command}")


def info(message):
    print(message)
