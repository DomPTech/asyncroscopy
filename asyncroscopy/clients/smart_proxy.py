# smart_client.py
"""Smart client that extends NotebookClient for multi-backend operations."""
from clients.notebook_client import NotebookClient
from concurrent.futures import ThreadPoolExecutor


class SmartClient(NotebookClient):
    """Client with high-level functions for multi-backend operations."""
    
    def __init__(self, host="localhost", port=9000, max_workers=8):
        super().__init__(host, port)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def take_dual_spec_image(self, image_args: dict = None, 
                            spec_args: dict = None,
                            timeout: float = None):
        """
        Acquire image and spectrum simultaneously from two backends.
        
        Args:
            image_args: Arguments for image acquisition (e.g., {'exposure': 0.1})
            spec_args: Arguments for spectrum acquisition
            timeout: Timeout for each operation
        
        Returns:
            (image, spectrum) tuple
        """
        # Submit both commands concurrently, pass callable + args, not the result
        future_image = self.executor.submit(self.send_command, "AS", "get_scanned_image", image_args)
        future_spec  = self.executor.submit(self.send_command, "Gatan", "get_spectrum", spec_args)

        # Wait for both to complete
        image = future_image.result()
        spectrum = future_spec.result()
        
        return image, spectrum
    
    def parallel_acquire(self, commands: list[tuple[str, str, dict]], 
                        timeout: float = None):
        """
        Execute multiple commands in parallel.
        
        Args:
            commands: List of (destination, command, args) tuples
            timeout: Timeout for each operation
        
        Returns:
            List of results in same order as commands
        
        Example:
            results = client.parallel_acquire([
                ("AS", "get_image", {"exposure": 0.1}),
                ("Gatan", "acquire_spectrum", {}),
                ("Ceos", "get_aberrations", {})
            ])
        """
        futures = []
        for dest, cmd, args in commands:
            future = self.executor.submit(
                self.send_command,
                dest, cmd, args, timeout
            )
            futures.append(future)
        
        # Return results in order
        return [f.result() for f in futures]
    