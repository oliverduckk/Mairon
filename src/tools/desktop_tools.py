import subprocess


ALLOWED_APPLICATIONS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe"
}


def launch_application(app_name):
    app_name = app_name.lower()

    if app_name not in ALLOWED_APPLICATIONS:
        return {
            "success": False,
            "message": f"Application '{app_name}' is not approved."
        }

    subprocess.Popen([ALLOWED_APPLICATIONS[app_name]])

    return {
        "success": True,
        "message": f"Launched {app_name}."
    }

