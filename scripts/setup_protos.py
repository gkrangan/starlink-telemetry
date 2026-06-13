#!/usr/bin/env python3
"""Download Starlink proto files and compile Python gRPC stubs."""

import os
import subprocess
import sys
from pathlib import Path

import requests

REPO_RAW = "https://raw.githubusercontent.com/sparky8512/starlink-grpc-tools/main/proto"

PROTO_FILES = [
    "spacex/api/device/command.proto",
    "spacex/api/device/device.proto",
    "spacex/api/device/dish.proto",
    "spacex/api/device/transceiver.proto",
    "spacex/api/device/wifi.proto",
    "spacex/api/device/wifi_config.proto",
    "spacex/api/common/status/status.proto",
]

ROOT = Path(__file__).parent.parent
PROTO_DIR = ROOT / "proto"
OUT_DIR = ROOT / "starlink_telemetry" / "proto"


def download_protos():
    print("Downloading proto files...")
    for rel_path in PROTO_FILES:
        url = f"{REPO_RAW}/{rel_path}"
        dest = PROTO_DIR / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"  {rel_path}")
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    print(f"Downloaded {len(PROTO_FILES)} proto files to {PROTO_DIR}/")


def compile_protos():
    print("\nCompiling proto stubs...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create __init__.py files for each package level
    packages = set()
    for rel_path in PROTO_FILES:
        parts = Path(rel_path).parts[:-1]
        for i in range(len(parts)):
            packages.add("/".join(parts[: i + 1]))

    for pkg in packages:
        init = OUT_DIR / pkg / "__init__.py"
        init.parent.mkdir(parents=True, exist_ok=True)
        if not init.exists():
            init.touch()
    (OUT_DIR / "__init__.py").touch()

    for rel_path in PROTO_FILES:
        proto_file = PROTO_DIR / rel_path
        print(f"  {rel_path}")
        cmd = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={PROTO_DIR}",
            f"--python_out={OUT_DIR}",
            f"--grpc_python_out={OUT_DIR}",
            str(proto_file),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR compiling {rel_path}:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)

    # Fix relative imports in generated grpc files (grpcio-tools generates absolute imports)
    for grpc_file in OUT_DIR.rglob("*_pb2_grpc.py"):
        text = grpc_file.read_text()
        # Generated files import like: from spacex.api... import ...
        # We need: from starlink_telemetry.proto.spacex.api... import ...
        text = text.replace(
            "from spacex.api",
            "from starlink_telemetry.proto.spacex.api",
        )
        text = text.replace(
            "import spacex.api",
            "import starlink_telemetry.proto.spacex.api",
        )
        grpc_file.write_text(text)

    for pb2_file in OUT_DIR.rglob("*_pb2.py"):
        text = pb2_file.read_text()
        text = text.replace(
            "from spacex.api",
            "from starlink_telemetry.proto.spacex.api",
        )
        text = text.replace(
            "\"spacex/api",
            "\"starlink_telemetry/proto/spacex/api",  # for descriptor pool file names
        )
        pb2_file.write_text(text)

    print(f"\nStubs written to {OUT_DIR}/")


if __name__ == "__main__":
    try:
        import grpc_tools  # noqa: F401
    except ImportError:
        print("grpcio-tools not found. Run: pip install -r requirements.txt")
        sys.exit(1)

    download_protos()
    compile_protos()
    print("\nSetup complete. Run `starlink --help` or `python -m starlink_telemetry.cli --help`")
