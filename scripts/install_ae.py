"""
ae-mcp Installer for Adobe After Effects
Installs the ScriptUI Panel and Startup script into After Effects.
"""

import os
import sys
import shutil
import glob
from pathlib import Path

def install():
    repo_root = Path(__file__).resolve().parent.parent
    panel_src = repo_root / "extendscript" / "ae_panel.jsx"
    startup_src = repo_root / "extendscript" / "ae_startup.jsx"

    if not panel_src.exists():
        print(f"Error: Panel source not found at {panel_src}")
        return False
    if not startup_src.exists():
        print(f"Error: Startup source not found at {startup_src}")
        return False

    installed_locations = []

    # 1. Target Program Files After Effects installations
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    ae_install_dirs = glob.glob(os.path.join(program_files, "Adobe", "Adobe After Effects *", "Support Files", "Scripts"))

    for scripts_dir in ae_install_dirs:
        panel_dir = Path(scripts_dir) / "ScriptUI Panels"
        startup_dir = Path(scripts_dir) / "Startup"

        try:
            panel_dir.mkdir(parents=True, exist_ok=True)
            panel_dst = panel_dir / "ae-mcp.jsx"
            shutil.copy2(panel_src, panel_dst)
            installed_locations.append(str(panel_dst))
        except PermissionError:
            print(f"Notice: Administrator permission required for {panel_dir}. Trying user roaming directory...")

        try:
            startup_dir.mkdir(parents=True, exist_ok=True)
            startup_dst = startup_dir / "ae-mcp-startup.jsx"
            shutil.copy2(startup_src, startup_dst)
            installed_locations.append(str(startup_dst))
        except PermissionError:
            pass

    # 2. Target User Roaming After Effects configurations
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        roaming_ae = Path(appdata) / "Adobe" / "After Effects"
        if roaming_ae.exists():
            for ver_dir in roaming_ae.iterdir():
                if ver_dir.is_dir() and ver_dir.name not in ("Logs",):
                    scripts_dir = ver_dir / "Scripts"
                    panel_dir = scripts_dir / "ScriptUI Panels"
                    startup_dir = scripts_dir / "Startup"

                    try:
                        panel_dir.mkdir(parents=True, exist_ok=True)
                        panel_dst = panel_dir / "ae-mcp.jsx"
                        shutil.copy2(panel_src, panel_dst)
                        installed_locations.append(str(panel_dst))
                    except Exception as e:
                        print(f"Error installing to {panel_dir}: {e}")

                    try:
                        startup_dir.mkdir(parents=True, exist_ok=True)
                        startup_dst = startup_dir / "ae-mcp-startup.jsx"
                        shutil.copy2(startup_src, startup_dst)
                        installed_locations.append(str(startup_dst))
                    except Exception as e:
                        print(f"Error installing to {startup_dir}: {e}")

    # 3. Initialize %TEMP%\ae_mcp_ipc directory
    temp_ipc = Path(os.environ.get("TEMP", r"C:\Temp")) / "ae_mcp_ipc"
    temp_ipc.mkdir(parents=True, exist_ok=True)

    print("========================================")
    print("ae-mcp After Effects Extension Installed")
    print("========================================")
    for loc in installed_locations:
        print(f" Installed: {loc}")
    print(f" IPC Channel: {temp_ipc}")
    print("Restart or open After Effects, then check:")
    print(" - Window > ae-mcp.jsx (for the dockable bridge panel)")
    print("========================================")
    return True

if __name__ == "__main__":
    install()
