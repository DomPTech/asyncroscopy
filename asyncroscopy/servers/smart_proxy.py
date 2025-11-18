import traceback
from twisted.internet import reactor
from asyncroscopy.servers.protocols.central_server_old import CentralProtocol, CentralFactory, routing_table


# Factory - holds shared states
class SmartProxyFactory(CentralFactory):
    def __init__(self):
        # persistent states for all protocol instances
        self.microscope = None
        self.aberrations = {}
        self.status = "Offline"
        
    def buildProtocol(self, addr):
        """Create a new protocol instance and attach the factory (shared state)."""
        proto = SmartProxyProtocol(routing_table=routing_table)
        proto.factory = self
        return proto


# Protocol - per connection methods
class SmartProxyProtocol(CentralProtocol):
    """
    Protocol for executing registered commands.
    """

    def __init__(self):
        super().__init__()
        # Build a whitelist of allowed method names
        allowed = []
        for name, value in SmartProxyProtocol.__dict__.items():
            if callable(value) and not name.startswith("_"):
                allowed.append(name)
        self.allowed_commands = set(allowed)

    def stringReceived(self, data: bytes):
        msg = data.decode().strip()

        if msg.startswith("SmartProxy_"):
            # below mirrors the stringReceived in ExecutionProtocol
            msg = msg[len('SmartProxy_') + 1:]  # strip "SmartProxy_"
            parts = msg.split()
            cmd, *args = parts
            args_dict = dict(arg.split('=', 1) for arg in args if '=' in arg)

            try:
                method = getattr(self, cmd, None)
                result = method(args_dict)
                if not isinstance(result, (bytes, bytearray)):
                    result = str(result).encode()
                self.sendString(result)

            except Exception:
                err = traceback.format_exc()
                print(f"[Exec] Error executing '{msg}':\n{err}")
                self.sendString(err.encode())

        # Otherwise fall back on base central routing
        super().stringReceived(data)


# Start the central server
print("Central server running on port 9000...")
reactor.listenTCP(9000, SmartProxyFactory())
reactor.run()