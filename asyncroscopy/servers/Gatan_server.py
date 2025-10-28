# Gatan_server.py
from twisted.internet import reactor
import numpy as np
import time
from base_protocol import CommandProtocol, CommandFactory

class GatanProtocol(CommandProtocol):
    def __init__(self):
        super().__init__()
        # register all supported commands
        self.register_command("Gatan_get_spectrum", self.get_spectrum)
        self.register_command("Gatan_status", self.status)

    def get_spectrum(self, args):
        size = int(args[0])
        print(f"[AS] Generating spectrum of size {size}")
        time.sleep(3)

        x = np.arange(size)
        spectrum = (np.exp(-x / 200) * 1000
         + 50 * np.exp(-0.5 * ((x - 150) / 5) ** 2)
         + 30 * np.exp(-0.5 * ((x - 300) / 8) ** 2)
         + np.random.normal(0, 5, size)).astype(np.float32)

        return spectrum.tobytes()

    def status(self, args):
        return b"Gatan server online"


if __name__ == "__main__":
    factory = CommandFactory()
    factory.protocol = GatanProtocol

    port = 9002
    print(f"Gatan server running on port {port}...")
    reactor.listenTCP(port, factory)
    reactor.run()