# Gatan_server_twin.py

"""
mirrors the real thing.
"""

from twisted.internet import reactor, protocol
import numpy as np
import time
import sys

from asyncroscopy.servers.protocols.execution_protocol import ExecutionProtocol


# FACTORY — holds shared state (persistent across all connections)
class GatanFactory(protocol.Factory):
    def __init__(self):
        # persistent states for all protocol instances
        self.detectors = {}
        self.status = "Offline"

    def buildProtocol(self, addr):
        """Create a new protocol instance and attach the factory (shared state)."""
        proto = GatanProtocol()
        proto.factory = self
        return proto


# PROTOCOL — handles per-connection command execution
class GatanProtocol(ExecutionProtocol):
    def __init__(self):
        super().__init__()
        # register supported commands
        self.register_command("connect_Gatan", self.connect_Gatan)
        self.register_command("get_spectrum", self.get_spectrum)
        self.register_command("get_status", self.get_status)

    def connect_Gatan(self, host, port):
        """Connect to the Gatan camera via AutoScript"""
        self.factory.status = "Ready"
        msg = "[Gatan] Connected to Gatan camera."
        return msg.encode()

    def get_spectrum(self, size):
        size = int(size)
        time.sleep(3)

        x = np.arange(size)
        spectrum = (np.exp(-x / 200) * 1000
         + 50 * np.exp(-0.5 * ((x - 150) / 5) ** 2)
         + 30 * np.exp(-0.5 * ((x - 300) / 8) ** 2)
         + np.random.normal(0, 5, size)).astype(np.float32)

        return spectrum.tobytes()

    def get_status(self, args=None):
        """Return the status"""
        msg = f"Gatan server is {self.factory.status}"
        return msg.encode()


if __name__ == "__main__":
    port = 9002
    print(f"[Gatan] Server running on port {port}...")
    reactor.listenTCP(port, GatanFactory())
    reactor.run()