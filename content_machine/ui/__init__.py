"""
UI & Dashboard package for Content Machine.
"""

def generate_html_dashboard(*args, **kwargs):
    from .dashboard import generate_html_dashboard as _gen
    return _gen(*args, **kwargs)

__all__ = ["generate_html_dashboard"]
