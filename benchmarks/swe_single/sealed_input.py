"""Keep user-supplied implementation assets encrypted in the public CI repo."""
import os
from pathlib import Path
import subprocess


def transform(source, destination, *, decrypt=False, passphrase=None):
    secret = passphrase or os.environ.get('OPENCLAW57_PATCH_KEY')
    if not secret:
        raise ValueError('OPENCLAW57_PATCH_KEY is required for the sealed build input')
    command = ['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-iter', '200000',
               '-pass', 'stdin', '-in', str(source), '-out', str(destination)]
    command += ['-d'] if decrypt else ['-salt']
    # No key in command arguments, filenames, artifacts or logs. Ciphertext
    # hashes are pinned in source.json before decryption is attempted.
    result = subprocess.run(command, input=(secret + '\n').encode(), capture_output=True)
    if result.returncode:
        Path(destination).unlink(missing_ok=True)
        raise ValueError('Sealed build input could not be processed')
