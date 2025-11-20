# AS_server.py

"""
the real thing.
"""

from twisted.internet import reactor, protocol
import numpy as np
import time
import sys

from asyncroscopy.servers.protocols.execution_protocol import ExecutionProtocol
from asyncroscopy.servers.protocols.utils import package_message, unpackage_message
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

    def connect_AS(self, args: dict):
        """Connect to the microscope via AutoScript"""
        host = args.get('host')
        port = args.get('port')
        
        print(f"[AS] Connecting to microscope at {host}:{port}...")
        try:
            self.factory.microscope = auto_script.TemMicroscopeClient()
            self.factory.microscope.connect(host=str(host), port=int(port))
            self.factory.status = "Ready"
            msg = "[AS] Connected to microscope."
        except Exception as e:
            msg = f"[AS] Failed to connect to microscope: {e}"
            self.factory.microscope = None
        self.sendString(package_message(msg))

    def get_scanned_image(self, scanning_detector, size, dwell_time):
        """Return a scanned image using the indicated detector"""
        size = int(size)
        dwell_time = float(dwell_time)
        if dwell_time * size * size > 600: # frame time > 10 minutes
            print(f"[AS] Error: Acquisition too long: {dwell_time*size*size} seconds")
            return None
        else:
            self.factory.status = "Busy"
            image = self.microscope.acquisition.acquire_stem_image(
                scanning_detector = 'HAADF', 
                size = size, 
                dwell_time = dwell_time)
            self.factory.status = "Ready"
            self.sendString(package_message(image))

    def get_stage(self):
        """Return current stage position"""
        positions = self.factory.microscope.specimen.stage.position
        positions = np.array(positions, dtype=np.float32)
        self.sendString(package_message(positions))

    def get_status(self, args: dict = None):
        """Return the server status"""
        msg = f"Microscope is {self.factory.status}"
        self.sendString(package_message(msg))


if __name__ == "__main__":
    port = 9001
    print(f"[AS] Server running on port {port}...")
    reactor.listenTCP(port, ASFactory())
    reactor.run()