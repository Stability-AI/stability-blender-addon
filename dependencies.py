import ensurepip
import sys
import subprocess
import os
import requests
import tarfile
import sysconfig


def install_dependencies(using_grpc: bool, using_sentry: bool) -> None:
    ensurepip.bootstrap()
    os.environ.pop("PIP_REQ_TRACKER", None)
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env["GRPC_PYTHON_BUILD_WITH_CYTHON"] = "1"
    deps_to_install = ["Pillow"]
    if using_sentry:
        deps_to_install.append("sentry-sdk")
    if using_grpc:
        deps_to_install.append("stability-sdk")
    for dep_name in deps_to_install:
        res = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep_name], env=env
        )
        print(res.stdout)


def check_dependencies_installed(using_grpc: bool, using_sentry: bool) -> bool:
    try:
        if using_grpc:
            import stability_sdk
        if using_sentry:
            import sentry_sdk

        return True
    except ImportError:
        return False
