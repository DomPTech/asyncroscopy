# base_protocol.py
from twisted.internet.protocol import Protocol, Factory
import struct, traceback

class CommandProtocol(Protocol):
    def __init__(self):
        super().__init__()
        self.commands = {}

    def register_command(self, name, func):
        """Register a callable command function."""
        self.commands[name] = func

    def dataReceived(self, data):
        try:
            msg = data.decode().strip()
            parts = msg.split()
            cmd = parts[0]

            if cmd not in self.commands:
                response = f"Unknown command: {cmd}".encode()
            else:
                # call the registered function and get the response bytes
                response_data = self.commands[cmd](parts[1:])
                if not isinstance(response_data, (bytes, bytearray)):
                    raise ValueError("Command must return bytes")
                response = response_data

            # send back length-prefixed response
            self.transport.write(struct.pack("!I", len(response)))
            self.transport.write(response)

        except Exception as e:
            err = traceback.format_exc().encode()
            self.transport.write(struct.pack("!I", len(err)))
            self.transport.write(err)

        finally:
            self.transport.loseConnection()


class CommandFactory(Factory):
    protocol = CommandProtocol