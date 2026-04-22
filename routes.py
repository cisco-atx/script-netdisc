"""Netdisc route module.

Provides the NetdiscScript class for handling input rendering and
execution of the network discovery process.

File path: routes.py
"""

import logging
import os

from flask import render_template_string

from .workers import run_netdisc

logger = logging.getLogger(__name__)


class NetdiscScript:
    """Script handler for network discovery operations."""

    meta = {
        "name": "Netdisc",
        "version": "1.0.0",
        "description": (
            "Performs multi-layered network discovery to identify active "
            "hosts, open ports, and services on a target network."
        ),
        "icon": "network_intel_node",
    }

    def __init__(self, ctx=None):
        """Initialize NetdiscScript with context."""
        self.ctx = ctx

    @classmethod
    def input(self):
        """Render the input HTML template."""
        input_template = os.path.join(
            os.path.dirname(__file__),
            "templates",
            "input.html",
        )

        try:
            with open(input_template, encoding="utf-8") as file:
                template_content = file.read()
            return render_template_string(template_content)
        except Exception as exc:
            logger.exception("Failed to load input template: %s", exc)
            raise

    def run(self, inputs):
        """Execute the network discovery process."""
        devices = [
            d.strip()
            for d in inputs.get("devices", "").splitlines()
            if d.strip()
        ]

        flags = {
            "interface": "interface" in inputs,
            "mac": "mac" in inputs,
            "arp": "arp" in inputs,
            "cdp_lldp": "cdp_lldp" in inputs,
            "vlans": "vlans" in inputs,
            "switchport": "switchport" in inputs,
            "ip_interface": "ip_interface" in inputs,
            "routing": "routing" in inputs,
            "inventory": "inventory" in inputs,
            "config": "config" in inputs,
        }

        connector = self.ctx.config.get("connector")

        # Validation
        if not devices:
            self.ctx.error("No devices provided")
            return

        if not connector:
            self.ctx.error("No Connector information provided")
            return

        try:
            # Execute worker logic
            run_netdisc(
                devices=devices,
                flags=flags,
                connector=connector,
                ctx=self.ctx,
            )
        except Exception as exc:
            logger.exception(
                "Error during network discovery execution: %s", exc
            )
            raise

        self.ctx.finish()
