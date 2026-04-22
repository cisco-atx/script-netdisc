"""Netdisc worker module.

Runs network discovery across multiple devices, collects interface,
L2/L3, routing, inventory, and configuration data, and generates
an Excel report.

Module path: workers.py
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from socket import getfqdn, gethostbyname

from netcore import GenericHandler, XLBW, get_config_section


def _normalize_iface(iface: str) -> str:
    """Normalize interface name to short format."""
    labels = ['Te', 'Gi', 'Fa', 'Eth', 'Lo', 'Vl', 'Two', 'Twe']
    for label in labels:
        if re.match(f'^{label}', iface, re.IGNORECASE):
            port = re.search(r'(\d+\S*)', iface)
            return f"{label}{port.group(1)}" if port else iface
    return iface


def _expand_iface(iface: str) -> str:
    """Expand interface name to full format."""
    mapping = {
        'Te': 'TenGigabitEthernet',
        'Gi': 'GigabitEthernet',
        'Fa': 'FastEthernet',
        'Eth': 'Ethernet',
        'Two': 'TwoGigabitEthernet',
        'Twe': 'TwentyFiveGigE',
        'Lo': 'Loopback',
        'Vl': 'Vlan',
    }
    for short, full in mapping.items():
        if re.match(f'^{short}', iface, re.IGNORECASE):
            port = re.search(r'(\d+\S*)', iface)
            return f"{full}{port.group(1)}" if port else iface
    return iface


def run_netdisc(devices, flags, connector, ctx):
    """Execute network discovery across multiple devices."""
    total_devices = len(devices)
    ctx.log(f"Starting Netdisc for {total_devices} devices")

    data = {"summary": {}, "links": {}}

    def worker(device):
        """Process a single device."""
        ctx.log(f"[{device}] Connecting")

        proxy = None
        if connector.get("jumphost_ip"):
            proxy = {
                "hostname": connector["jumphost_ip"],
                "username": connector["jumphost_username"],
                "password": connector["jumphost_password"],
            }

        try:
            handler = GenericHandler(
                hostname=device,
                username=connector["network_username"],
                password=connector["network_password"],
                proxy=proxy,
                handler="NETMIKO",
            )
        except Exception as e:
            ctx.error(f"[{device}] Connection failed: {e}")
            return

        ctx.log(f"[{device}] Connected, collecting data")

        try:
            iface_data = handler.sendCommand(
                cmd="show interface",
                autoParse=True,
                key="interface",
            )
        except Exception:
            return

        iface_status = {}
        iface_desc = {}
        if flags["interface"]:
            iface_status = handler.sendCommand(
                cmd="show interface status",
                autoParse=True,
                key="interface",
            )
            iface_desc = handler.sendCommand(
                cmd="show interface description",
                autoParse=True,
                key="interface",
            )

        swport_data = (
            handler.sendCommand(
                cmd="show interface switchport",
                autoParse=True,
                key="interface",
            )
            if flags["switchport"]
            else {}
        )

        vlan_data = (
            handler.sendCommand(
                cmd="show vlan",
                autoParse=True,
                key="vlan_id",
            )
            if flags["vlans"]
            else {}
        )

        mac_data = (
            handler.sendCommand(
                cmd="show mac address",
                autoParse=True,
                key="mac_address",
            )
            if flags["mac"]
            else {}
        )

        arp_data = (
            handler.sendCommand(
                cmd="show ip arp",
                autoParse=True,
                key="mac_address",
            )
            if flags["arp"]
            else {}
        )

        lldp_data, cdp_data = {}, {}
        if flags["cdp_lldp"]:
            lldp_data = handler.sendCommand(
                cmd="show lldp neighbors",
                autoParse=True,
                key="local_interface",
            )
            cdp_data = handler.sendCommand(
                cmd="show cdp neighbors",
                autoParse=True,
                key="local_interface",
            )

        ip_iface_data = (
            handler.sendCommand(
                cmd="show ip interface",
                autoParse=True,
                key="interface",
            )
            if flags["ip_interface"]
            else {}
        )

        bgp_data, ospf_data = {}, {}
        if flags["routing"]:
            bgp_data = handler.sendCommand(
                cmd="show ip bgp neighbors",
                autoParse=True,
                key="neighbor",
            )
            ospf_data = handler.sendCommand(
                cmd="show ip ospf interface brief",
                autoParse=True,
                key="interface",
            )

        config = (
            handler.sendCommand("show runn")
            if flags["config"]
            else ""
        )

        version = {}
        mgmt_ip = ""
        if flags["inventory"]:
            version = handler.sendCommand(
                cmd="show version",
                autoParse=True,
            )[0]
            mgmt_ip = gethostbyname(device)

        ctx.log(f"[{device}] Processing data")

        links = {}

        for iface, iface_props in iface_data.items():
            iface_n = _normalize_iface(iface)
            links[iface_n] = {}

            if flags["interface"]:
                links[iface_n].update(
                    {
                        "Status": "",
                        "Description": "",
                        "Link": "",
                        "Duplex": "",
                        "Speed": "",
                        "MediaType": "",
                    }
                )

                for k, v in iface_status.items():
                    if iface_n == _normalize_iface(k):
                        links[iface_n].update(
                            {
                                "Status": v["status"],
                                "Link": v["vlan_id"],
                                "Duplex": v["duplex"],
                                "Speed": v["speed"],
                                "MediaType": v["type"],
                            }
                        )

                for k, v in iface_desc.items():
                    if iface_n == _normalize_iface(k):
                        links[iface_n]["Description"] = v["description"]

            if flags["switchport"]:
                links[iface_n].update(
                    {
                        "Switchport": "",
                        "Access": "",
                        "Voice": "",
                        "Trunk": "",
                        "Native": "",
                    }
                )

                for k, v in swport_data.items():
                    if iface_n == _normalize_iface(k):
                        links[iface_n].update(
                            {
                                "Switchport": v["mode"],
                                "Access": v["access_vlan"],
                                "Voice": v["voice_vlan"],
                                "Trunk": v["trunking_vlans"],
                                "Native": v["native_vlan"],
                            }
                        )

            if flags["vlans"]:
                links[iface_n]["VlanName"] = ""
                for vlan in vlan_data.values():
                    if iface in vlan["interfaces"]:
                        links[iface_n]["VlanName"] = vlan["vlan_name"]

            if flags["cdp_lldp"]:
                links[iface_n].update(
                    {
                        "Neighbor": "",
                        "Platform": "",
                        "Capability": "",
                        "RemoteIface": "",
                    }
                )

                for k, v in lldp_data.items():
                    if iface_n == _normalize_iface(k):
                        links[iface_n].update(
                            {
                                "Neighbor": v["neighbor"],
                                "Capability": v["capabilities"],
                                "RemoteIface": _normalize_iface(
                                    v["remote_interface"]
                                ),
                            }
                        )

                for k, v in cdp_data.items():
                    if iface_n == _normalize_iface(k):
                        links[iface_n].update(
                            {
                                "Neighbor": v["neighbor"],
                                "Platform": v["platform"],
                                "Capability": v["capability"],
                                "RemoteIface": _normalize_iface(
                                    v["remote_interface"]
                                ),
                            }
                        )

            if flags["mac"]:
                links[iface_n]["MAC"] = []
                links[iface_n]["VLAN"] = []

                if flags["arp"]:
                    links[iface_n]["ARP"] = []
                    links[iface_n]["FQDN"] = []

                for mac, mac_props in mac_data.items():
                    if iface_n == _normalize_iface(mac_props["ports"]):
                        links[iface_n]["MAC"].append(mac)
                        links[iface_n]["VLAN"].append(
                            mac_props["vlan_id"]
                        )

                        if flags["arp"]:
                            ip = arp_data.get(mac, {}).get(
                                "ip_address", ""
                            )
                            links[iface_n]["ARP"].append(ip)
                            links[iface_n]["FQDN"].append(
                                getfqdn(ip) if ip else ""
                            )

            if flags["ip_interface"]:
                links[iface_n].update(
                    {"IP Interface": "", "VRF": ""}
                )

                for k, v in ip_iface_data.items():
                    if iface_n == _normalize_iface(k):
                        links[iface_n]["IP Interface"] = (
                            f"{v['ip_address']}/{v['mask']}"
                            if v["ip_address"]
                            else ""
                        )
                        links[iface_n]["VRF"] = v["vrf"]

            if flags["routing"]:
                links[iface_n]["Routing"] = {}

                for v in bgp_data.values():
                    if v["localhost_ip"] == iface_props.get(
                            "ip_address"
                    ):
                        links[iface_n]["Routing"]["BGP"] = {
                            "remoteAsn": v["remote_asn"],
                            "state": v["bgp_state"],
                        }

                for k, v in ospf_data.items():
                    if iface_n == _normalize_iface(k):
                        links[iface_n]["Routing"]["OSPF"] = {
                            "area": v["area"],
                            "state": v["state"],
                        }

            if flags["config"]:
                links[iface_n]["Config"] = get_config_section(
                    f"interface {_expand_iface(iface_n)}", config
                )

        data["links"][device] = links

        summary = {}
        if flags["inventory"]:
            summary.update(
                {
                    "Hostname": version.get("hostname", ""),
                    "Version": version.get("version", ""),
                    "Model": version.get("hardware", ""),
                    "SerialNo": version.get("serial", ""),
                    "Uptime": version.get("uptime", ""),
                    "IP": mgmt_ip,
                }
            )

        data["summary"][device] = summary

        handler.close()
        ctx.log(f"[{device}] Completed")

    with ThreadPoolExecutor(max_workers=8) as pool:
        pool.map(worker, devices)

    ctx.log("All devices processed, generating report")

    _generate_report(data, ctx)

    ctx.log("Netdisc execution finished")


def _generate_report(data, ctx):
    """Generate Excel report from collected data."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H.%M")
    filename = f"Netdisc_{timestamp}.xlsx"
    path = os.path.join(ctx.output_dir, filename)

    wb = XLBW(path)

    if data["summary"]:
        ws = wb.add_worksheet("Summary")
        ws.freeze_panes(1, 2)
        wb.dump(_reindex(data["summary"], "Hostname"), ws)

    if data["links"]:
        ws = wb.add_worksheet("Links")
        ws.freeze_panes(1, 3)
        wb.dump(_flatten_links(data["links"]), ws)

    wb.close()

    ctx.log(f"Report generated: {filename}")


def _reindex(data, key):
    """Reindex dictionary data with incremental integer keys."""
    return {
        i: {key: k, **v}
        for i, (k, v) in enumerate(data.items(), 1)
    }


def _flatten_links(data):
    """Flatten nested link data for report output."""
    out = {}
    idx = 0
    for device, links in data.items():
        for port, props in links.items():
            idx += 1
            out[idx] = {"Hostname": device, "Port": port, **props}
    return out
