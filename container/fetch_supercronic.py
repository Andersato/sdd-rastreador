"""Descarga supercronic para la arquitectura de la imagen y comprueba su SHA-256.

Solo se usa al construir la imagen (etapa `supercronic` del Dockerfile). Si la
suma no coincide, termina con error y la construcción falla.
"""

import hashlib
import os
import platform
import sys
import urllib.request

URL = "https://github.com/aptible/supercronic/releases/download/{version}/supercronic-linux-{arch}"
MACHINE_TO_ARCH = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64", "amd64": "amd64"}


def main(destination: str) -> int:
    arch = os.environ.get("TARGETARCH") or MACHINE_TO_ARCH.get(platform.machine(), "")
    expected = os.environ.get(f"SUPERCRONIC_SHA256_{arch.upper()}", "")
    if not expected:
        print(f"Error: arquitectura no soportada para supercronic: {arch!r}", file=sys.stderr)
        return 1
    url = URL.format(version=os.environ["SUPERCRONIC_VERSION"], arch=arch)
    with urllib.request.urlopen(url, timeout=120) as response:
        binary = response.read()
    actual = hashlib.sha256(binary).hexdigest()
    if actual != expected:
        print(f"Error: la suma SHA-256 de {url} no coincide: esperada {expected}, "
              f"obtenida {actual}", file=sys.stderr)
        return 1
    with open(destination, "wb") as out:
        out.write(binary)
    os.chmod(destination, 0o755)
    print(f"supercronic {os.environ['SUPERCRONIC_VERSION']} ({arch}) verificado")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
