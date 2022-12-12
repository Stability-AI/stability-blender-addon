import ensurepip
import sys
import subprocess
import os
import requests
import tarfile
import sysconfig


def install_dependencies():
    ensurepip.bootstrap()
    os.environ.pop("PIP_REQ_TRACKER", None)
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env["GRPC_PYTHON_BUILD_WITH_CYTHON"] = "1"
    for dep_name in ("sentry-sdk", "Pillow"):
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep_name], env=env
        )
        print(res.stdout)


def check_dependencies_installed(using_grpc: bool = False) -> bool:
    try:
        if using_grpc:
            import stability_sdk
        import sentry_sdk

        return True
    except ImportError:
        return False
