"""CLI command implementations, one module per verb.

This package is the refactor's beachhead. Five audits noted cli.py's
size; rather than a risky mass-migration, the rule from here forward is:
NEW commands are born in this package, and existing ones migrate out of
cli.py as they are next touched. cli.py keeps argument parsing and
dispatch; the work lives here, importable and testable without the
3,000-line module around it.
"""
