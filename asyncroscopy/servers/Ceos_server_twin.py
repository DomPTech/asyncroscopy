# Ceos_server.py

"""
digital twin

"""

import logging
import json
from typing import Tuple, List, Optional, Union, Sequence
import traceback
import socket
from twisted.internet import reactor,defer, protocol
from asyncroscopy.servers.protocols.execution_protocol import ExecutionProtocol

logging.basicConfig()
log = logging.getLogger('CEOS_acquisition')
log.setLevel(logging.INFO)

# FACTORY — holds shared state (persistent across all connections)
class CeosFactory(protocol.Factory):
    def __init__(self):
        # persistent states for all protocol instances
        self.microscope = None
        self.aberrations = {}
        self.status = "Offline"

    def buildProtocol(self, addr):
        """Create a new protocol instance and attach the factory (shared state)."""
        proto = CeosProtocol()
        proto.factory = self
        return proto


# PROTOCOL — handles per-connection command execution
class CeosProtocol(ExecutionProtocol):
    def __init__(self):
        super().__init__()

    def getInfo(self, args_dict=None):
        """Get microscope info."""
        msg = f"CEOS Digital Twin Server"
        self.sendString(self.package_message(msg))
    
    def uploadAberrations(self, args_dict):
        """Upload aberration data."""
        # args = aberration dictionary from pyTEMlib probe tools
        # but the values are strings
        for key in args_dict:
            args_dict[key] = float(args_dict[key])

        self.factory.aberrations.update(args_dict)
        print("args_dict:", args_dict)
        msg = 'Aberrations Loaded'
        self.sendString(self.package_message(msg))
    
    def runTableau(self, args_dict):
        """Run a tableau acquisition."""
        # args = {"tabType": 'Fast', "angle": 18}
        # args don't matter on this one:

    def correctAberration(self, args_dict):
        """Correct an aberration."""
        # args = {"name": name, "value": [...], "target": [...], "select": ...}
    
    def measure_c1a1(self):
        """Measure C1 and A1 aberrations."""
        # no args
        pass


if __name__ == "__main__":
    port = 9003
    print(f"[Ceos] Server running on port {port}...")
    reactor.listenTCP(port, CeosFactory())
    reactor.run()