# AS_server.py
from twisted.internet import reactor
import numpy as np
import time
from base_protocol import CommandProtocol, CommandFactory

class ASProtocol(CommandProtocol):
    def __init__(self):
        super().__init__()
        # register all supported commands
        self.register_command("AS_get_image", self.get_image)
        self.register_command("AS_status", self.status)

    def get_image(self, args):
        size = int(args[0])
        print(f"[AS] Generating image of size {size}x{size}")
        time.sleep(5)
        img = (np.random.rand(size, size) * 255).astype(np.uint8)
        return img.tobytes()

    def status(self, args):
        return b"AS server online"


if __name__ == "__main__":
    factory = CommandFactory()
    factory.protocol = ASProtocol

    port = 9001
    print(f"AS server running on port {port}...")
    reactor.listenTCP(port, factory)
    reactor.run()