import platform
import socket


def get_system_info():
    return {
        "operating_system": platform.system(),
        "os_version": platform.release(),
        "computer_name": socket.gethostname(),
        "architecture": platform.machine()
    }
