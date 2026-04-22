"""Netdisc module initializer.

Exposes the NetdiscScript class as the module-level entry point
for worker execution and integration within the application.

Module path: __init__.py
"""

from .routes import NetdiscScript

SCRIPT_CLASS = NetdiscScript