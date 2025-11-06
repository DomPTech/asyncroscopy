# AS_server_twin.py

"""
mirrors the real thing.
"""

from twisted.internet import reactor, protocol
import numpy as np
import time
import sys

from asyncroscopy.servers.protocols.execution_protocol import ExecutionProtocol
# sys.path.insert(0, "C:\\AE_future\\autoscript_1_14\\")
sys.path.insert(0, "/Users/austin/Desktop/Projects/autoscript_tem_microscope_client")
import autoscript_tem_microscope_client as auto_script


# FACTORY — holds shared state (persistent across all connections)
class ASFactory(protocol.Factory):
    def __init__(self):
        # persistent states for all protocol instances
        self.microscope = None
        self.detectors = {}
        self.status = "Offline"

    def buildProtocol(self, addr):
        """Create a new protocol instance and attach the factory (shared state)."""
        proto = ASProtocol()
        proto.factory = self
        return proto


# PROTOCOL — handles per-connection command execution
class ASProtocol(ExecutionProtocol):
    def __init__(self):
        super().__init__()
        # Register supported commands
        self.register_command("connect_AS", self.connect_AS)
        self.register_command("get_scanned_image", self.get_scanned_image)
        self.register_command("get_stage", self.get_stage)
        self.register_command("get_status", self.get_status)

    def connect_AS(self, host, port):
        """Connect to the microscope via AutoScript"""
        self.factory.microscope = 'Debugging'
        self.factory.status = "Ready"
        msg = "[AS] Connected to Digital Twin microscope."
        return msg.encode()

    def get_scanned_image(self, scanning_detector, size, dwell_time):
        """Return a scanned image using the indicated detector"""
        size = int(size)
        dwell_time = float(dwell_time)
        if dwell_time * size * size > 600: # frame time > 10 minutes
            print(f"[AS] Error: Acquisition too long: {dwell_time*size*size} seconds")
            return None
        else:
            self.factory.status = "Busy"
            time.sleep(5)
            image = (np.random.rand(size, size) * 255).astype(np.uint8)
            self.factory.status = "Ready"
            return image.tobytes()

    def get_stage(self):
        """Return current stage position (placeholder)"""
        positions = [np.random.uniform(-10, 10) for _ in range(5)]
        return np.array(positions, dtype=np.float32).tobytes()

    def get_status(self, args=None):
        """Return the server status"""
        msg = f"Microscope is {self.factory.status}"
        return msg.encode()


if __name__ == "__main__":
    port = 9001
    print(f"[AS] Server running on port {port}...")
    reactor.listenTCP(port, ASFactory())
    reactor.run()