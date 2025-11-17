# execution_protocol.py
"""
Executes locally registered commands.
Used by backend servers (AS, Gatan, CEOS, etc).
Packages responses in a standard format.
"""

from twisted.protocols.basic import Int32StringReceiver
import traceback
import logging
import numpy as np
logging.basicConfig()
log = logging.getLogger('CEOS_acquisition') # fix later
log.setLevel(logging.INFO)

class ExecutionProtocol(Int32StringReceiver):
    """
    Protocol for executing registered commands.
    """

    def __init__(self):
        super().__init__()
        # Build a whitelist of allowed method names
        allowed = []
        for name, value in ExecutionProtocol.__dict__.items():
            if callable(value) and not name.startswith("_"):
                allowed.append(name)
        self.allowed_commands = set(allowed)

        self._pendingCommands = {}


    def connectionMade(self):
        """
        Called by twisted after a connection to the server has been
        established.
        """
        # log.info('[Exec] Connection from {self.transport.getPeer()}')
        print(f"[Exec] Connection from {self.transport.getPeer()}")

    def connectionLost(self, reason):
        """
        Called by twisted after the connection to the server has been
        interrupted.
        """
        log.info('Client disconnected: %s', reason.getErrorMessage())

        for d in self._pendingCommands.values():
            d.errback(reason)
        self._pendingCommands.clear()
        
    def disconnect(self):
        """
        Disconnect from server.
        """
        self.transport.loseConnection()

    def stringReceived(self, data: bytes):
        msg = data.decode().strip()
        print(f"[Exec] Received: {msg}")
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

    def package_message(self, data):
        """
        Convert Python data into the protocol format:
        
            b"[dtype,shape...]<binary payload>"
        
        Compatible with the client's parsing logic.
        """

        # ----- Strings -----
        if isinstance(data, str):
            encoded = data.encode()
            header = f"[str,{len(encoded)}]".encode()
            return header + encoded

        # ----- Bytes -----
        if isinstance(data, (bytes, bytearray)):
            # treat raw bytes as uint8 array
            arr = np.frombuffer(data, dtype=np.uint8)
            header = f"[uint8,{arr.size}]".encode()
            return header + data

        # ----- Scalars -----
        if isinstance(data, (int, float)):
            arr = np.array([data], dtype=np.float32)
            header = f"[float32,1]".encode()
            return header + arr.tobytes()

        # ----- Lists / Tuples -----
        if isinstance(data, (list, tuple)):
            data = np.asarray(data)

        # ----- NumPy Array -----
        if isinstance(data, np.ndarray):
            dtype = data.dtype.name       # e.g. "uint8", "float32"
            shape = ",".join(str(x) for x in data.shape)
            header = f"[{dtype},{shape}]".encode()
            return header + data.tobytes()

        # ----- Unknown object → stringify -----
        text = str(data).encode()
        header = f"[str,{len(text)}]".encode()
        return header + text