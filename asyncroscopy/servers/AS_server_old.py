# AS_server.py

"""
the real thing.
"""

from twisted.internet import reactor
import numpy as np
import time
from base_protocol import CommandProtocol, CommandFactory

import sys
# sys.path.insert(0, "C:\\AE_future\\autoscript_1_14\\")
sys.path.insert(0, "/Users/austin/Desktop/Projects/autoscript_tem_microscope_client")
import autoscript_tem_microscope_client as auto_script

class ASProtocol(CommandProtocol):
    def __init__(self):
        super().__init__()
        # inits
        self.microscope = None
        self.detectors  = {}
        
        # register all supported commands
        self.register_command("AS_connect_AS", self.connect_AS)
        self.register_command("AS_get_image", self.get_image)
        self.register_command("AS_get_status", self.get_status)

    def connect_AS(self, args):
        try:
            self.microscope = 'Connected!!'
            # self.microscope = auto_script.TemMicroscopeClient()
            # self.microscope.connect(host = str(args[0]), port = int(args[1]))
            msg = "[AS] Connected to microscope."
        except Exception as e:
            msg = "[AS] Failed to connect to microscope: {e}"
            self.microscope = None
        return msg.encode()

        
    def get_image(self, args):
        size = int(args[0])
        print(f"[AS] Generating image of size {size}x{size}")
        time.sleep(1)
        img = (np.random.rand(size, size) * 255).astype(np.uint8)
        return img.tobytes()

    def get_stage(self):
        """Get the current stage position"""
        positions = self.microscope.specimen.stage.position
        return np.array(positions).tobytes()

    def get_status(self, args):
        if self.microscope is None:
            return b"AS server offline"
        else:
            return b"AS server online"


if __name__ == "__main__":
    factory = CommandFactory()
    factory.protocol = ASProtocol

    port = 9001
    print(f"AS server running on port {port}...")
    reactor.listenTCP(port, factory)
    reactor.run()