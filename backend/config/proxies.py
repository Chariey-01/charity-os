"""Which address a request came from, when a reverse proxy sits in front.

Behind a proxy, ``REMOTE_ADDR`` is the proxy. Proxies append the address
they saw to ``X-Forwarded-For``, but a client can send that header too, so
only the entries added by proxies we run can be believed:

* ``CHARITYOS_TRUSTED_PROXIES`` lists the proxies' addresses or networks
  (comma-separated). It is empty by default, which ignores forwarded
  headers entirely and uses ``REMOTE_ADDR``.
* A forwarded header is read only when ``REMOTE_ADDR`` itself is trusted
  (a connection that bypassed the proxy is not believed).
* The header is read from the right, skipping trusted proxies; the first
  other address is the client. Everything to its left was written by the
  client and is ignored. If that entry is not a plain IP address the proxy
  address is used, never a guess.

Used for django-axes lockouts (``AXES_CLIENT_IP_CALLABLE``) and for the
security log. See docs/operations/reverse-proxy.md.
"""

import ipaddress

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

HEADER = "HTTP_X_FORWARDED_FOR"


def parse_trusted_proxies(value):
    """Parse a comma-separated list of addresses or networks, strictly."""
    networks = []
    for item in (part.strip() for part in (value or "").split(",")):
        if not item:
            continue
        try:
            network = ipaddress.ip_network(item, strict=True)
        except ValueError as exc:
            raise ImproperlyConfigured(
                f"CHARITYOS_TRUSTED_PROXIES: {item!r} is not an IP address or "
                "network (host bits must be zero, e.g. 10.0.0.0/8)."
            ) from exc
        if network.prefixlen == 0:
            raise ImproperlyConfigured(
                f"CHARITYOS_TRUSTED_PROXIES: {item!r} would trust every address."
            )
        networks.append(network)
    return tuple(networks)


def _address(value):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _trusted(address, networks):
    return address is not None and any(address in network for network in networks)


def client_ip(request):
    """The client's address as a string (see the module docstring)."""
    remote = request.META.get("REMOTE_ADDR", "")
    networks = getattr(settings, "CHARITYOS_TRUSTED_PROXIES", ())
    if not networks or not _trusted(_address(remote), networks):
        return remote
    hops = [hop for hop in request.META.get(HEADER, "").split(",") if hop.strip()]
    for hop in reversed(hops):
        address = _address(hop)
        if address is None:
            return remote  # a trusted proxy wrote something unusable
        if not _trusted(address, networks):
            return str(address)
    # Every hop is one of ours: the left-most is a client inside our network.
    return str(_address(hops[0])) if hops else remote


def axes_client_ip(request):
    """``AXES_CLIENT_IP_CALLABLE``: the same address the security log uses."""
    return client_ip(request)
