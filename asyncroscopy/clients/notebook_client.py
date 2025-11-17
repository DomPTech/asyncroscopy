# notebook_client.py
'''Client for TEM central server.'''
import socket
import struct
import numpy as np

# still needs a lot of work
class NotebookClient:
    """Client for TEM central server."""
    def __init__(self, host="localhost", port=9000):
        self.host = host
        self.port = port

    @classmethod
    def connect(cls,  host="127.0.0.1", port=9000):
        """Try to connect briefly to verify central server is up.
        Returns TEMClient(host, port) on success, or None on failure.
        """
        print(f"Connecting to central server {host}:{port}...")
        try:
            with socket.create_connection((host, port), timeout=5) as s:
                print("Connected to central server.")
            return cls(host, port)
        except (ConnectionRefusedError, socket.timeout):
            print(f"Could not connect to central server at {host}:{port}")
            return None

    def send_command(self, destination: str, command: str,
                     args: dict | None = {},
                     timeout: float | None = None) -> bytes:
        """Send a length-prefixed command with args and receive a length-prefixed response."""
        cmd = f"{destination}_{command} " + " ".join(f"{k}={v}" for k, v in args.items())
        try:
            # Encode the command
            payload = cmd.encode()
            header = struct.pack("!I", len(payload))

            with socket.create_connection((self.host, self.port), timeout=timeout) as sock:
                # Send length-prefixed message
                sock.sendall(header + payload)

                # Read the 4-byte response header
                resp_hdr = self._recv_exact(sock, 4)
                resp_len = struct.unpack("!I", resp_hdr)[0]

                # Read full response
                data = self._recv_exact(sock, resp_len)
                end_idx = data.index(b']') + 1
                header = data[:end_idx].decode()  # header is text
                payload = data[end_idx:]          # payload is binary
                dtype, *shape = header[1:-1].split(',')
                shape = tuple(map(int, shape))

                if dtype == 'str':
                    payload = payload.decode()
                elif dtype == 'uint8':
                    payload = np.frombuffer(payload, dtype=np.uint8).reshape(shape)
                elif dtype == 'float32':
                    payload = np.frombuffer(payload, dtype=np.float32).reshape(shape)
                else:
                    try: # try string
                        payload = payload.decode()
                    except:
                        raise ValueError(f"Unknown data type in notebook client: {dtype}")
                return payload

        except (ConnectionRefusedError, socket.timeout):
            print(f"Could not connect to {self.host}:{self.port} after {timeout} seconds")
            return None

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes:
        """Receive exactly n bytes or raise ConnectionError if socket closes early."""
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Socket closed early while receiving data")
            buf += chunk
        return buf
