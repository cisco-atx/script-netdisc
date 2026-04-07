import os
from flask import render_template_string
from .workers import run_netdisc


class NetdiscScript:
    meta = {
        "name": "Netdisc",
        "version": "1.0.0",
        "description": "Performs multi-layered network discovery to identify active hosts, open ports, and services on a target network.",
        "icon": "network_intel_node",
    }

    def __init__(self, ctx=None):
        self.ctx = ctx

    @classmethod
    def input(self):
        input_template = os.path.join(
            os.path.dirname(__file__),
            "templates",
            "input.html"
        )
        return render_template_string(open(input_template).read())

    def run(self, inputs):
        devices = [d.strip() for d in inputs.get("devices", "").splitlines() if d.strip()]

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

        # Execute worker logic
        run_netdisc(
            devices=devices,
            flags=flags,
            connector=connector,
            ctx=self.ctx
        )

        self.ctx.finish()