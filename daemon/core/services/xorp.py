"""
xorp.py: defines routing services provided by the XORP routing suite.
"""

import logging

import netaddr

from core.services.coreservices import CoreService


class XorpRtrmgr(CoreService):
    """
    XORP router manager service builds a config.boot file based on other
    enabled XORP services, and launches necessary daemons upon startup.
    """

    name = "xorp_rtrmgr"
    executables = ("xorp_rtrmgr",)
    group = "XORP"
    dirs = ("/etc/xorp",)
    configs = ("/etc/xorp/config.boot",)
    startup = (
        "xorp_rtrmgr -d -b %s -l /var/log/%s.log -P /var/run/%s.pid"
        % (configs[0], name, name),
    )
    shutdown = ("killall xorp_rtrmgr",)
    validate = ("pidof xorp_rtrmgr",)

    @classmethod
    def generate_config(cls, node, filename):
        """
        Returns config.boot configuration file text. Other services that
        depend on this will have generatexorpconfig() hooks that are
        invoked here. Filename currently ignored.
        """
        cfg = "interfaces {\n"
        for iface in node.get_ifaces():
            cfg += "    interface %s {\n" % iface.name
            cfg += "\tvif %s {\n" % iface.name
            cfg += "".join(map(cls.addrstr, iface.addrlist))
            cfg += cls.lladdrstr(iface)
            cfg += "\t}\n"
            cfg += "    }\n"
        cfg += "}\n\n"

        for s in node.services:
            try:
                s.dependencies.index(cls.name)
                cfg += s.generatexorpconfig(node)
            except ValueError:
                logging.exception("error getting value from service: %s", cls.name)

        return cfg

    @staticmethod
    def addrstr(x):
        """
        helper for mapping IP addresses to XORP config statements
        """
        addr, plen = x.split("/")
        cfg = "\t    address %s {\n" % addr
        cfg += "\t\tprefix-length: %s\n" % plen
        cfg += "\t    }\n"
        return cfg

    @staticmethod
    def lladdrstr(iface):
        """
        helper for adding link-local address entries (required by OSPFv3)
        """
        cfg = "\t    address %s {\n" % iface.mac.tolinklocal()
        cfg += "\t\tprefix-length: 64\n"
        cfg += "\t    }\n"
        return cfg


class XorpService(CoreService):
    """
    Parent class for XORP services. Defines properties and methods
    common to XORP's routing daemons.
    """

    name = None
    executables = ("xorp_rtrmgr",)
    group = "XORP"
    dependencies = ("xorp_rtrmgr",)
    dirs = ()
    configs = ()
    startup = ()
    shutdown = ()
    meta = "The config file for this service can be found in the xorp_rtrmgr service."

    @staticmethod
    def fea(forwarding):
        """
        Helper to add a forwarding engine entry to the config file.
        """
        cfg = "fea {\n"
        cfg += "    %s {\n" % forwarding
        cfg += "\tdisable:false\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg

    @staticmethod
    def mfea(forwarding, ifaces):
        """
        Helper to add a multicast forwarding engine entry to the config file.
        """
        names = []
        for iface in ifaces:
            if hasattr(iface, "control") and iface.control is True:
                continue
            names.append(iface.name)
        names.append("register_vif")

        cfg = "plumbing {\n"
        cfg += "    %s {\n" % forwarding
        for name in names:
            cfg += "\tinterface %s {\n" % name
            cfg += "\t    vif %s {\n" % name
            cfg += "\t\tdisable: false\n"
            cfg += "\t    }\n"
            cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg

    @staticmethod
    def policyexportconnected():
        """
        Helper to add a policy statement for exporting connected routes.
        """
        cfg = "policy {\n"
        cfg += "    policy-statement export-connected {\n"
        cfg += "\tterm 100 {\n"
        cfg += "\t    from {\n"
        cfg += '\t\tprotocol: "connected"\n'
        cfg += "\t    }\n"
        cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg

    @staticmethod
    def routerid(node):
        """
        Helper to return the first IPv4 address of a node as its router ID.
        """
        for iface in node.get_ifaces(control=False):
            for a in iface.addrlist:
                a = a.split("/")[0]
                if netaddr.valid_ipv4(a):
                    return a
        # raise ValueError,  "no IPv4 address found for router ID"
        return "0.0.0.0"

    @classmethod
    def generate_config(cls, node, filename):
        return ""

    @classmethod
    def generatexorpconfig(cls, node):
        return ""


class XorpOspfv2(XorpService):
    """
    The OSPFv2 service provides IPv4 routing for wired networks. It does
    not build its own configuration file but has hooks for adding to the
    unified XORP configuration file.
    """

    name = "XORP_OSPFv2"

    @classmethod
    def generatexorpconfig(cls, node):
        cfg = cls.fea("unicast-forwarding4")
        rtrid = cls.routerid(node)
        cfg += "\nprotocols {\n"
        cfg += "    ospf4 {\n"
        cfg += "\trouter-id: %s\n" % rtrid
        cfg += "\tarea 0.0.0.0 {\n"
        for iface in node.get_ifaces(control=False):
            cfg += "\t    interface %s {\n" % iface.name
            cfg += "\t\tvif %s {\n" % iface.name
            for a in iface.addrlist:
                addr = a.split("/")[0]
                if not netaddr.valid_ipv4(addr):
                    continue
                cfg += "\t\t    address %s {\n" % addr
                cfg += "\t\t    }\n"
            cfg += "\t\t}\n"
            cfg += "\t    }\n"
        cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg


class XorpOspfv3(XorpService):
    """
    The OSPFv3 service provides IPv6 routing. It does
    not build its own configuration file but has hooks for adding to the
    unified XORP configuration file.
    """

    name = "XORP_OSPFv3"

    @classmethod
    def generatexorpconfig(cls, node):
        cfg = cls.fea("unicast-forwarding6")
        rtrid = cls.routerid(node)
        cfg += "\nprotocols {\n"
        cfg += "    ospf6 0 { /* Instance ID 0 */\n"
        cfg += "\trouter-id: %s\n" % rtrid
        cfg += "\tarea 0.0.0.0 {\n"
        for iface in node.get_ifaces(control=False):
            cfg += "\t    interface %s {\n" % iface.name
            cfg += "\t\tvif %s {\n" % iface.name
            cfg += "\t\t}\n"
            cfg += "\t    }\n"
        cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg


class XorpBgp(XorpService):
    """
    IPv4 inter-domain routing. AS numbers and peers must be customized.
    """

    name = "XORP_BGP"
    custom_needed = True

    @classmethod
    def generatexorpconfig(cls, node):
        cfg = "/* This is a sample config that should be customized with\n"
        cfg += " appropriate AS numbers and peers */\n"
        cfg += cls.fea("unicast-forwarding4")
        cfg += cls.policyexportconnected()
        rtrid = cls.routerid(node)
        cfg += "\nprotocols {\n"
        cfg += "    bgp {\n"
        cfg += "\tbgp-id: %s\n" % rtrid
        cfg += "\tlocal-as: 65001 /* change this */\n"
        cfg += '\texport: "export-connected"\n'
        cfg += "\tpeer 10.0.1.1 { /* change this */\n"
        cfg += "\t    local-ip: 10.0.1.1\n"
        cfg += "\t    as: 65002\n"
        cfg += "\t    next-hop: 10.0.0.2\n"
        cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg


class XorpRip(XorpService):
    """
    RIP IPv4 unicast routing.
    """

    name = "XORP_RIP"

    @classmethod
    def generatexorpconfig(cls, node):
        cfg = cls.fea("unicast-forwarding4")
        cfg += cls.policyexportconnected()
        cfg += "\nprotocols {\n"
        cfg += "    rip {\n"
        cfg += '\texport: "export-connected"\n'
        for iface in node.get_ifaces(control=False):
            cfg += "\tinterface %s {\n" % iface.name
            cfg += "\t    vif %s {\n" % iface.name
            for a in iface.addrlist:
                addr = a.split("/")[0]
                if not netaddr.valid_ipv4(addr):
                    continue
                cfg += "\t\taddress %s {\n" % addr
                cfg += "\t\t    disable: false\n"
                cfg += "\t\t}\n"
            cfg += "\t    }\n"
            cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg


class XorpRipng(XorpService):
    """
    RIP NG IPv6 unicast routing.
    """

    name = "XORP_RIPNG"

    @classmethod
    def generatexorpconfig(cls, node):
        cfg = cls.fea("unicast-forwarding6")
        cfg += cls.policyexportconnected()
        cfg += "\nprotocols {\n"
        cfg += "    ripng {\n"
        cfg += '\texport: "export-connected"\n'
        for iface in node.get_ifaces(control=False):
            cfg += "\tinterface %s {\n" % iface.name
            cfg += "\t    vif %s {\n" % iface.name
            cfg += "\t\taddress %s {\n" % iface.mac.tolinklocal()
            cfg += "\t\t    disable: false\n"
            cfg += "\t\t}\n"
            cfg += "\t    }\n"
            cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg


class XorpPimSm4(XorpService):
    """
    PIM Sparse Mode IPv4 multicast routing.
    """

    name = "XORP_PIMSM4"

    @classmethod
    def generatexorpconfig(cls, node):
        cfg = cls.mfea("mfea4", node.get_ifaces())

        cfg += "\nprotocols {\n"
        cfg += "    igmp {\n"
        names = []
        for iface in node.get_ifaces(control=False):
            names.append(iface.name)
            cfg += "\tinterface %s {\n" % iface.name
            cfg += "\t    vif %s {\n" % iface.name
            cfg += "\t\tdisable: false\n"
            cfg += "\t    }\n"
            cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"

        cfg += "\nprotocols {\n"
        cfg += "    pimsm4 {\n"

        names.append("register_vif")
        for name in names:
            cfg += "\tinterface %s {\n" % name
            cfg += "\t    vif %s {\n" % name
            cfg += "\t\tdr-priority: 1\n"
            cfg += "\t    }\n"
            cfg += "\t}\n"
        cfg += "\tbootstrap {\n"
        cfg += "\t    cand-bsr {\n"
        cfg += "\t\tscope-zone 224.0.0.0/4 {\n"
        cfg += '\t\t    cand-bsr-by-vif-name: "%s"\n' % names[0]
        cfg += "\t\t}\n"
        cfg += "\t    }\n"
        cfg += "\t    cand-rp {\n"
        cfg += "\t\tgroup-prefix 224.0.0.0/4 {\n"
        cfg += '\t\t    cand-rp-by-vif-name: "%s"\n' % names[0]
        cfg += "\t\t}\n"
        cfg += "\t    }\n"
        cfg += "\t}\n"

        cfg += "    }\n"
        cfg += "}\n"

        cfg += "\nprotocols {\n"
        cfg += "    fib2mrib {\n"
        cfg += "\tdisable: false\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg


class XorpPimSm6(XorpService):
    """
    PIM Sparse Mode IPv6 multicast routing.
    """

    name = "XORP_PIMSM6"

    @classmethod
    def generatexorpconfig(cls, node):
        cfg = cls.mfea("mfea6", node.get_ifaces())

        cfg += "\nprotocols {\n"
        cfg += "    mld {\n"
        names = []
        for iface in node.get_ifaces(control=False):
            names.append(iface.name)
            cfg += "\tinterface %s {\n" % iface.name
            cfg += "\t    vif %s {\n" % iface.name
            cfg += "\t\tdisable: false\n"
            cfg += "\t    }\n"
            cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"

        cfg += "\nprotocols {\n"
        cfg += "    pimsm6 {\n"

        names.append("register_vif")
        for name in names:
            cfg += "\tinterface %s {\n" % name
            cfg += "\t    vif %s {\n" % name
            cfg += "\t\tdr-priority: 1\n"
            cfg += "\t    }\n"
            cfg += "\t}\n"
        cfg += "\tbootstrap {\n"
        cfg += "\t    cand-bsr {\n"
        cfg += "\t\tscope-zone ff00::/8 {\n"
        cfg += '\t\t    cand-bsr-by-vif-name: "%s"\n' % names[0]
        cfg += "\t\t}\n"
        cfg += "\t    }\n"
        cfg += "\t    cand-rp {\n"
        cfg += "\t\tgroup-prefix ff00::/8 {\n"
        cfg += '\t\t    cand-rp-by-vif-name: "%s"\n' % names[0]
        cfg += "\t\t}\n"
        cfg += "\t    }\n"
        cfg += "\t}\n"

        cfg += "    }\n"
        cfg += "}\n"

        cfg += "\nprotocols {\n"
        cfg += "    fib2mrib {\n"
        cfg += "\tdisable: false\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg


class XorpOlsr(XorpService):
    """
    OLSR IPv4 unicast MANET routing.
    """

    name = "XORP_OLSR"

    @classmethod
    def generatexorpconfig(cls, node):
        cfg = cls.fea("unicast-forwarding4")
        rtrid = cls.routerid(node)
        cfg += "\nprotocols {\n"
        cfg += "    olsr4 {\n"
        cfg += "\tmain-address: %s\n" % rtrid
        for iface in node.get_ifaces(control=False):
            cfg += "\tinterface %s {\n" % iface.name
            cfg += "\t    vif %s {\n" % iface.name
            for a in iface.addrlist:
                addr = a.split("/")[0]
                if not netaddr.valid_ipv4(addr):
                    continue
                cfg += "\t\taddress %s {\n" % addr
                cfg += "\t\t}\n"
            cfg += "\t    }\n"
        cfg += "\t}\n"
        cfg += "    }\n"
        cfg += "}\n"
        return cfg
