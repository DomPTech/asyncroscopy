# AS_server.py

"""
the real thing.
"""

from twisted.internet import reactor, protocol
import numpy as np
import time
import sys

from base_protocol import CommandProtocol
sys.path.insert(0, "/Users/austin/Desktop/Projects/autoscript_tem_microscope_client")
import autoscript_tem_microscope_client as auto_script


# FACTORY — holds shared state (persistent across all connections)
# ================================================================
class ASFactory(protocol.Factory):
    def __init__(self):
        # persistent state for all protocol instances
        self.microscope = None
        self.detectors = {}

    def buildProtocol(self, addr):
        """Create a new protocol instance and attach the factory (shared state)."""
        proto = ASProtocol()
        proto.factory = self
        return proto


# PROTOCOL — handles per-connection command execution
# ================================================================
class ASProtocol(CommandProtocol):
    def __init__(self):
        super().__init__()
        # Register supported commands
        self.register_command("AS_connect_AS", self.connect_AS)
        self.register_command("AS_get_image", self.get_image)
        self.register_command("AS_get_status", self.get_status)
        self.register_command("AS_get_stage", self.get_stage)

    # ---------------------------------------------------------------
    def connect_AS(self, args):
        """Connect to the microscope via AutoScript."""
        try:
            # self.factory.microscope = auto_script.TemMicroscopeClient()
            # self.factory.microscope.connect(host=str(args[0]), port=int(args[1]))
            self.factory.microscope = "Connected!!"
            msg = "[AS] Connected to microscope."
        except Exception as e:
            msg = f"[AS] Failed to connect to microscope: {e}"
            self.factory.microscope = None
        return msg.encode()

    # ---------------------------------------------------------------
    def get_image(self, args):
        """Simulate image acquisition (placeholder for actual TEM API call)."""
        size = int(args[0])
        print(f"[AS] Generating image of size {size}x{size}")
        time.sleep(1)
        img = (np.random.rand(size, size) * 255).astype(np.uint8)
        return img.tobytes()

    # ---------------------------------------------------------------
    def get_stage(self, args):
        """Return current stage position as a NumPy byte array."""
        if self.factory.microscope is None:
            return b"Microscope not connected"
        try:
            # positions = self.factory.microscope.specimen.stage.position
            positions = [0.0, 0.0, 0.0, 0.0, 0.0]  # placeholder
            return np.array(positions, dtype=np.float32).tobytes()
        except Exception as e:
            return f"[AS] Failed to get stage position: {e}".encode()

    # ---------------------------------------------------------------
    def get_status(self, args):
        """Return whether the AutoScript microscope is connected."""
        if self.factory.microscope is None:
            return b"AS server offline"
        else:
            return b"AS server online"


# ================================================================
if __name__ == "__main__":
    port = 9001
    print(f"[AS] Server running on port {port}...")
    reactor.listenTCP(port, ASFactory())
    reactor.run()