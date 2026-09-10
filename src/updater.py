import hashlib
import os
import subprocess
import sys
import tempfile
import urllib.request

APP_EXE_NAME = "DLSS5Manager.exe"


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": "DLSS5Manager/2.2"})
    part = destination + ".part"
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(part, "wb") as handle:
            while chunk := response.read(256 * 1024):
                handle.write(chunk)
        if not os.path.isfile(part) or os.path.getsize(part) == 0:
            raise RuntimeError("Downloaded update is empty.")
        os.replace(part, destination)
    finally:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass


def verify(path, expected_sha256):
    if not expected_sha256:
        return True
    return sha256_file(path).lower() == expected_sha256.lower()


def start_replace_helper(current_exe, new_exe):
    current_exe = os.path.abspath(current_exe)
    new_exe = os.path.abspath(new_exe)
    backup_exe = current_exe + ".old"
    script = os.path.join(tempfile.gettempdir(), "dlss5manager_updater.bat")
    current_pid = os.getpid()
    content = f'''@echo off
setlocal
set "PID={current_pid}"
set "CURRENT={current_exe}"
set "NEW={new_exe}"
set "BACKUP={backup_exe}"
:wait
 tasklist /FI "PID eq %PID%" 2>nul | findstr /R /C:" %PID% " >nul
 if not errorlevel 1 (
   timeout /t 1 /nobreak >nul
   goto wait
 )
 copy /Y "%CURRENT%" "%BACKUP%" >nul
 if errorlevel 1 exit /b 1
 move /Y "%NEW%" "%CURRENT%" >nul
 if errorlevel 1 (
   copy /Y "%BACKUP%" "%CURRENT%" >nul
   exit /b 1
 )
 start "DLSS5Manager" "%CURRENT%"
 del "%BACKUP%" >nul 2>&1
 del "%~f0" >nul 2>&1
'''
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(content)
    subprocess.Popen(["cmd.exe", "/d", "/c", script], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def apply_update(download_url, expected_sha256=None):
    current = os.path.abspath(sys.executable)
    if not current.lower().endswith(".exe"):
        raise RuntimeError("Self-update is available only for the packaged EXE.")
    new_exe = os.path.join(tempfile.gettempdir(), "DLSS5Manager.new.exe")
    download(download_url, new_exe)
    if not verify(new_exe, expected_sha256):
        try:
            os.remove(new_exe)
        except OSError:
            pass
        raise RuntimeError("Update SHA-256 verification failed.")
    start_replace_helper(current, new_exe)
