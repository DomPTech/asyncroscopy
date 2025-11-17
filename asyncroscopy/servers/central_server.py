# central_server.py
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.protocols.basic import Int32StringReceiver
from twisted.internet.defer import Deferred

# Define backend server addresses
routing_table = {"AS": ("localhost", 9001),
                "Gatan": ("localhost", 9002),
                "Ceos": ("localhost", 9003),
                "Preacquired_AS": ("localhost", 9004)}

# routing_table = {"AS": ("10.46.217.241", 9095),
#                 "Gatan": ("localhost", 9002),
#                 "Ceos": ("localhost", 9003)}

class CentralProtocol(Int32StringReceiver):
    MAX_LENGTH = 10_000_000 # quick fix
    """Generic command protocol using 4-byte length-prefixed messages."""

    def __init__(self, routing_table=None):
        super().__init__()
        self.routing_table = routing_table
    
    def set_routing_table(self, routing_table):
        self.routing_table = routing_table

    def connectionMade(self):
        print("[Central] Connection made from", self.transport.getPeer())

    def stringReceived(self, data: bytes):
        """Handle incoming message from a client."""
        msg = data.decode().strip()
        print(f"[Central] Received command: {msg}")

        # Determine if it should be routed
        for prefix, (host, port) in self.routing_table.items():
            if msg.startswith(prefix):
                routed_cmd = msg[len(prefix) + 1:]  # strip "PREFIX_"
                print(f"[Central] Routing '{msg}' to {prefix} backend at {host}:{port}")
                self._forward_to_backend(host, port, routed_cmd)
                return

        if msg.startswith("Central"):
            parts = msg.split()
            if parts[0][8:] == "set_routing_table":
                # Reassemble "KEY=('host', port)" chunks in one pass
                cleaned, buf = [], []
                for tok in parts[1:]:
                    buf.append(tok)
                    if tok.endswith(")"):
                        cleaned.append(" ".join(buf))
                        buf = []
                routing_table = {
                    k: (v.strip()[1:-1].split(",",1)[0].strip().strip("'\""),
                        int(v.strip()[1:-1].split(",",1)[1]))
                    for k, v in (item.split("=",1) for item in cleaned)}
                self.set_routing_table(routing_table)
                payload = f"[str,23][Central] Updated routing table"
                self.sendString(payload.encode())
                return
            
            else:
                response = f"[Central] Recived unknown central command '{parts[0][8:]}'"
                header = f'[str,{len(response)}]'
                payload = header + msg
                self.sendString(payload.encode())
                return
        
        # If no match, return error
        self.sendString(f"Unknown command prefix in '{msg}'".encode())

    # Backend routing helper
    def _forward_to_backend(self, host, port, command: str):
        """Forward a command to a backend server and return its response asynchronously."""
        d = Deferred()
        endpoint = TCP4ClientEndpoint(reactor, host, port)

        def on_connect(proto):
            proto.sendCommand(command)
            return d  # Return our deferred that will fire when backend responds

        connect_d = connectProtocol(endpoint, BackendClient(d))
        connect_d.addCallback(on_connect)
        connect_d.addCallback(self._send_backend_response)
        connect_d.addErrback(self._send_backend_error)
        return connect_d

    def _send_backend_response(self, payload: bytes):
        print(f"[Central] Received backend response: {payload!r}")
        self.sendString(payload)

    def _send_backend_error(self, err):
        self.sendString(f"[Central] Error communicating with backend server: {err}".encode())


class BackendClient(Int32StringReceiver):
    """Handles communication with a backend server (AS, Gatan, CEOS, etc)."""
    MAX_LENGTH = 10_000_000 # quick fix
    def __init__(self, finished: Deferred):
        self.finished = finished

    def connectionMade(self):
        print(f"[Central] Connected to backend at {self.transport.getPeer()}")

    def stringReceived(self, data: bytes):
        self.finished.callback(data)
        self.transport.loseConnection()

    def connectionLost(self, reason):
        if not self.finished.called:
            self.finished.errback(reason)

    def sendCommand(self, cmd: str):
        print(f"[Central → Exec] Sending framed command: {cmd!r}")
        self.sendString(cmd.encode())
        print(f"[Central → Exec] Flushed command of length {len(cmd)} bytes")


class CentralFactory(Factory):
    def buildProtocol(self, addr):
        return CentralProtocol(routing_table=routing_table)

# Start the central server
print("Central server running on port 9000...")
reactor.listenTCP(9000, CentralFactory())
reactor.run()