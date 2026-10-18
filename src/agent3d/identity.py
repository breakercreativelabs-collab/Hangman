"""Product identity, read from identity.toml at the repo root (the only place the product name appears)."""
import os
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FILE = os.path.join(ROOT, "identity.toml")
_DATA = {}


def read():
    if not _DATA:
        with open(FILE, "rb") as f:
            _DATA.update(tomllib.load(f))
    return dict(_DATA)


def name():
    return read()["name"]


def slug():
    return read()["slug"]


def description():
    return read()["description"]


def version():
    return read()["version"]


def title():
    """Short text for the CLI/log/MCP banner, e.g. '<name> 0.1.0'."""
    return f"{name()} {version()}"


def public_repo():
    """'owner/repo' that receives feedback submissions (GitHub Issues); '' if not published yet."""
    return read().get("public_repo", "")
