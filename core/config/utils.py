"""Shared utilities for scan configuration."""
import unicodedata


def slugify(name):
    """Normalize a name to ASCII lowercase with underscores."""
    return (
        unicodedata.normalize('NFKD', name)
        .encode('ascii', 'ignore').decode('ascii')
        .replace(' ', '_')
        .replace("'", "")
        .lower()
    )
