"""Strict local Tailscale startup conditions; not proof of client reachability/grants."""

import argparse
import ipaddress

TAILNET_V4 = ipaddress.IPv4Network("100.64.0.0/10")


def tailscale_ipv4(value):
    if not isinstance(value, str):
        raise ValueError("Tailscale address must be one IPv4 string")
    address = ipaddress.IPv4Address(value)
    if address not in TAILNET_V4 or str(address) != value:
        raise ValueError("Expected one canonical IPv4 in 100.64.0.0/10")
    return str(address)


def single_ipv4(values):
    if not isinstance(values, list) or not values:
        raise ValueError("Missing Tailscale IP list")
    addresses = [
        ipaddress.ip_address(value) for value in values if isinstance(value, str)
    ]
    if len(addresses) != len(values):
        raise ValueError("Invalid Tailscale IP list")
    ipv4 = [str(value) for value in addresses if value.version == 4]
    if len(ipv4) != 1:
        raise ValueError("Expected exactly one Tailscale IPv4")
    return tailscale_ipv4(ipv4[0])


def startup_state(status, expected_node_id):
    blocked = {
        "address": None,
        "network": "unverified",
        "reason_code": "TAILSCALE_NOT_READY",
    }
    if (
        not isinstance(status, dict)
        or not isinstance(expected_node_id, str)
        or not expected_node_id
    ):
        return blocked
    peer = status.get("Self")
    if not isinstance(peer, dict):
        return blocked
    tun, online, expired = (
        status.get("TUN"),
        peer.get("Online"),
        peer.get("Expired", False),
    )
    if status.get("BackendState") != "Running" or not isinstance(tun, bool) or not tun:
        return blocked
    if not isinstance(online, bool) or not online:
        return blocked
    if peer.get("ID") != expected_node_id or not isinstance(expired, bool) or expired:
        return {**blocked, "reason_code": "TAILSCALE_IDENTITY_OR_EXPIRY"}
    try:
        address = single_ipv4(status.get("TailscaleIPs"))
        if address != single_ipv4(peer.get("TailscaleIPs")):
            return blocked
    except ValueError:
        return {**blocked, "reason_code": "TAILSCALE_INVALID_ADDRESS"}
    return {
        "address": address,
        "network": "authenticated-local",
        "reason_code": "ORCA_READINESS_UNVERIFIED",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", required=True)
    args = parser.parse_args()
    try:
        print(tailscale_ipv4(args.address))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
