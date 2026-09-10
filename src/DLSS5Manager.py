# Spider-Man 2 DLSS 5 Manager
# See repository README.md for project information.

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import zipfile
import shutil
import urllib.request
import urllib.error
import subprocess
import winreg
import ctypes
import tempfile
import hashlib
import json
import time
import re
from datetime import datetime

APP_NAME = "DLSS 5 Manager"
APP_VERSION = "2.1"

URL_RESHADE = "https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe"
URL_DLSS_ZIP = ("https://cdn.discordapp.com/attachments/1543975158937821315/1543977625226182827/"
               "DLSS310.8.0-Streamline2.13.zip?ex=6aa403b7&is=6aa2b237&hm="
               "e8309e81114238473664557b896bde2ef0bb9f7d8b54f6f2a66f2ea6bf6af02&")
URL_DLSS_PATCH = ("https://cdn.discordapp.com/attachments/1543976771920330884/1543982044797866107/"
                  "nvngx_dlssnr.dll?ex=6aa407d5&is=6aa2b655&hm="
                  "2ba08e80f7f791bbcfc0880039e278a1cebbcb00b47365e669305b9686e6bf86&")
URL_ADDON = ("https://cdn.discordapp.com/attachments/1545049227321810974/1545877902715920504/"
             "renodx-dlss.addon64?ex=6aa3ad3d&is=6aa25bbd&hm="
             "e195687a64529ab6fb52d0eb35769a00a83579b295e3b5083b7432a5417a9485&")

EXPECTED_HASHES = {
    "ReShade_Setup_6.8.0_Addon.exe": None,
    "DLSS_Streamline.zip": None,
    "nvngx_dlssnr.dll": None,
    "renodx-dlss.addon64": None,
}

BG = "#0f0f0f"
CARD = "#1a1a1a"
BORDER = "#2a2a2a"
ACCENT = "#e8003d"
TEXT = "#f0f0f0"
TEXT_DIM = "#888888"
TEXT_MUTED = "#555555"
GREEN = "#22c55e"
AMBER = "#f59e0b"
RED = "#ef4444"
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO = ("Consolas", 9)
GAME_NAME = "Marvel's Spider-Man 2"


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_hash(path, expected_hash):
    if not expected_hash:
        return None, "SHA-256 not configured."
    actual = sha256_file(path)
    if actual.lower() == expected_hash.lower():
        return True, f"SHA-256 verified: {actual}"
    return False, f"SHA-256 mismatch.\nExpected: {expected_hash}\nActual:   {actual}"


def is_within_directory(base_dir, target_path):
    base = os.path.abspath(base_dir)
    target = os.path.abspath(target_path)
    try:
        return os.path.commonpath([base, target]) == base
    except ValueError:
        return False


def unique_backup_name(path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{path}.backup_{timestamp}"


def detect_gpu_gen():
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=5)
        name = result.stdout.lower()
        if any(x in name for x in ["rtx 50", "rtx50", "5050", "5060", "5070", "5080", "5090"]):
            return "rtx50"
        if any(x in name for x in ["rtx 40", "rtx40", "4050", "4060", "4070", "4080", "4090"]):
            return "rtx40"
        if any(x in name for x in ["rtx 30", "rtx30", "3050", "3060", "3070", "3080", "3090"]):
            return "rtx30"
        if any(x in name for x in ["rtx 20", "rtx20", "2060", "2070", "2080"]):
            return "rtx20"
    except Exception:
        pass
    return None


def get_steam_path():
    locations = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
    ]
    for hive, key_path in locations:
        try:
            key = winreg.OpenKey(hive, key_path)
            for value_name in ("SteamPath", "InstallPath"):
                try:
                    value = winreg.QueryValueEx(key, value_name)[0]
                    if value and os.path.isdir(value):
                        winreg.CloseKey(key)
                        return os.path.normpath(value)
                except FileNotFoundError:
                    continue
            winreg.CloseKey(key)
        except Exception:
            continue
    return None


def parse_steam_library_vdf(steam_path):
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.isfile(vdf_path):
        return []
    try:
        with open(vdf_path, "r", encoding="utf-8", errors="ignore") as file:
            content = file.read()
        paths = re.findall(r'"path"\s*"([^"]+)"', content, flags=re.IGNORECASE)
        result = []
        for path in paths:
            path = path.replace("\\\\", "\\")
            if os.path.isdir(path):
                result.append(os.path.normpath(path))
        return result
    except Exception:
        return []


def find_spiderman2():
    steam_path = get_steam_path()
    if not steam_path:
        return None
    libraries = list(dict.fromkeys([steam_path, *parse_steam_library_vdf(steam_path)]))
    possible_names = ["Marvel's Spider-Man 2", "Marvels Spider-Man 2"]
    for library in libraries:
        common = os.path.join(library, "steamapps", "common")
        for name in possible_names:
            candidate = os.path.join(common, name)
            if os.path.isdir(candidate):
                return candidate
    for library in libraries:
        common = os.path.join(library, "steamapps", "common")
        if not os.path.isdir(common):
            continue
        try:
            for entry in os.listdir(common):
                if "spider" in entry.lower() and "man" in entry.lower():
                    candidate = os.path.join(common, entry)
                    if os.path.isdir(candidate):
                        return candidate
        except Exception:
            continue
    return None


def download_file(url, destination, progress_callback=None):
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
    })
    part = destination + ".part"
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            with open(part, "wb") as file:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    file.write(chunk)
                    downloaded += len(chunk)
                    if total and progress_callback:
                        progress_callback(int(downloaded / total * 100))
        if not os.path.isfile(part) or os.path.getsize(part) == 0:
            raise RuntimeError("Downloaded file is empty or missing.")
        os.replace(part, destination)
    except urllib.error.HTTPError as error:
        if os.path.exists(part): os.remove(part)
        raise RuntimeError(f"HTTP {error.code}: {error.reason}")
    except urllib.error.URLError as error:
        if os.path.exists(part): os.remove(part)
        raise RuntimeError(f"Network error: {error.reason}")
    except Exception as error:
        if os.path.exists(part): os.remove(part)
        raise RuntimeError(f"Download failed: {error}")


def verify_windows_signature(path):
    if not os.path.isfile(path):
        return False, "File does not exist."
    env = os.environ.copy()
    env["DLSS_MANAGER_FILE"] = path
    command = (
        "$s = Get-AuthenticodeSignature -LiteralPath $env:DLSS_MANAGER_FILE; "
        "Write-Output $s.Status"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            env=env, capture_output=True, text=True, timeout=15
        )
        status = result.stdout.strip().lower()
        if status == "valid":
            return True, "Authenticode signature: Valid"
        if status:
            return False, f"Authenticode signature: {status}"
        return None, "Authenticode verification returned no status."
    except Exception as error:
        return None, f"Authenticode verification unavailable: {error}"


def find_game_files(game_dir):
    wanted = {x.lower() for x in {
        "nvngx_dlss.dll", "nvngx_dlssnr.dll", "nvngx.dll", "sl.common.dll", "sl.dlss.dll",
        "reshade.ini", "reshade.log", "renodx-dlss.addon64", "renodx-dlss5.addon64"
    }}
    found = {}
    for root, dirs, files in os.walk(game_dir):
        dirs[:] = [d for d in dirs if d.lower() != ".dlss_manager_backups"]
        for filename in files:
            if filename.lower() in wanted:
                found.setdefault(filename.lower(), os.path.join(root, filename))
    return found


class DLSSManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION} — Spider-Man 2")
        self.geometry("820x760")
        self.minsize(820, 760)
        self.resizable(False, False)
        self.configure(bg=BG)
        self.gpu_gen = detect_gpu_gen()
        self.game_path = tk.StringVar(value=find_spiderman2() or "")
        self.status_var = tk.StringVar(value="Ready.")
        self.progress = tk.IntVar(value=0)
        self.install_running = False
        self._step_labels = []
        self.status_labels = {}
        self._configure_style()
        self._build_ui()
        self._refresh_gpu_badge()
        self._refresh_installation_status()

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Red.Horizontal.TProgressbar", troughcolor=CARD, bordercolor=BORDER,
                        background=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)

    def _build_ui(self):
        tk.Frame(self, bg=ACCENT, height=4).pack(fill="x")
        header = tk.Frame(self, bg=CARD, pady=15)
        header.pack(fill="x")
        tk.Label(header, text="DLSS 5 Manager", font=FONT_TITLE, bg=CARD, fg=TEXT).pack(side="left", padx=(24, 8))
        tk.Label(header, text="Spider-Man 2", font=("Segoe UI", 11), bg=CARD, fg=TEXT_DIM).pack(side="left", pady=6)
        self.gpu_badge = tk.Label(header, text="", font=FONT_SMALL, bg=CARD, fg=GREEN, padx=12)
        self.gpu_badge.pack(side="right", padx=24)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        body = tk.Frame(self, bg=BG, padx=24, pady=14)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="GAME DIRECTORY", font=("Segoe UI", 8, "bold"), bg=BG, fg=TEXT_MUTED).pack(anchor="w")
        path_row = tk.Frame(body, bg=BG, pady=4)
        path_row.pack(fill="x")
        self.path_entry = tk.Entry(path_row, textvariable=self.game_path, font=FONT_MONO, bg=CARD, fg=TEXT,
                                   insertbackground=TEXT, relief="flat", bd=0, highlightthickness=1,
                                   highlightbackground=BORDER, highlightcolor=ACCENT)
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 6))
        self._button(path_row, "Browse", self._browse).pack(side="left", padx=2)
        self._button(path_row, "Auto-detect", self._autodetect).pack(side="left", padx=2)

        tk.Label(body, text="INSTALLATION STATUS", font=("Segoe UI", 8, "bold"), bg=BG, fg=TEXT_MUTED).pack(anchor="w", pady=(12, 5))
        status_card = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        status_card.pack(fill="x")
        status_items = [("reshade", "ReShade"), ("dlss", "DLSS / Streamline"), ("patch", "DLSS-NR patched DLL"),
                        ("addon", "RenoDX DLSS addon"), ("backup", "Backup")]
        for index, (key, name) in enumerate(status_items):
            row = tk.Frame(status_card, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=name, font=FONT_BODY, bg=CARD, fg=TEXT, width=23, anchor="w").pack(side="left", padx=12)
            status = tk.Label(row, text="Checking...", font=FONT_SMALL, bg=CARD, fg=TEXT_DIM, anchor="e")
            status.pack(side="right", padx=12)
            self.status_labels[key] = status
            if index < len(status_items) - 1:
                tk.Frame(status_card, bg=BORDER, height=1).pack(fill="x")

        tk.Label(body, text="INSTALLATION STEPS", font=("Segoe UI", 8, "bold"), bg=BG, fg=TEXT_MUTED).pack(anchor="w", pady=(12, 5))
        steps_frame = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        steps_frame.pack(fill="x")
        steps = [("1", "Create backup", "backup"), ("2", "Download & safely launch ReShade", "reshade"),
                 ("3", "Install DLSS + Streamline", "dlss"), ("4", "Install patched DLSS-NR DLL", "patch"),
                 ("5", "Install RenoDX DLSS addon", "addon"), ("6", "Verify installation", "verify")]
        for index, (number, text, key) in enumerate(steps):
            row = tk.Frame(steps_frame, bg=CARD)
            row.pack(fill="x")
            tk.Label(row, text=number, font=("Segoe UI", 9, "bold"), bg=ACCENT, fg="white", width=3, pady=7).pack(side="left")
            tk.Label(row, text=text, font=FONT_BODY, bg=CARD, fg=TEXT, anchor="w").pack(side="left", padx=12, fill="x", expand=True)
            status = tk.Label(row, text="—", font=FONT_SMALL, bg=CARD, fg=TEXT_MUTED, padx=12)
            status.pack(side="right")
            self._step_labels.append((key, status))
            if index < len(steps) - 1:
                tk.Frame(steps_frame, bg=BORDER, height=1).pack(fill="x")

        tk.Label(body, text="PROGRESS", font=("Segoe UI", 8, "bold"), bg=BG, fg=TEXT_MUTED).pack(anchor="w", pady=(12, 4))
        self.pbar = ttk.Progressbar(body, variable=self.progress, maximum=100, style="Red.Horizontal.TProgressbar")
        self.pbar.pack(fill="x")
        self.status_lbl = tk.Label(body, textvariable=self.status_var, font=FONT_MONO, bg=BG, fg=TEXT_DIM, anchor="w")
        self.status_lbl.pack(fill="x", pady=(4, 2))

        tk.Label(body, text="LOG", font=("Segoe UI", 8, "bold"), bg=BG, fg=TEXT_MUTED).pack(anchor="w", pady=(5, 3))
        log_frame = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=6, bg=CARD, fg=TEXT_DIM, insertbackground=TEXT, font=FONT_MONO,
                                relief="flat", bd=0, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        bottom = tk.Frame(self, bg=CARD, pady=10, padx=24)
        bottom.pack(fill="x")
        self.install_btn = tk.Button(bottom, text="INSTALL / UPDATE", font=("Segoe UI", 10, "bold"), bg=ACCENT,
                                     fg="white", activebackground="#c0002e", activeforeground="white", relief="flat",
                                     bd=0, padx=18, pady=9, cursor="hand2", command=self._start_install)
        self.install_btn.pack(side="right")
        self.restore_btn = self._button(bottom, "Restore backup", self._restore_backup)
        self.restore_btn.pack(side="right", padx=(0, 6))
        self.verify_btn = self._button(bottom, "Verify", self._verify_clicked)
        self.verify_btn.pack(side="right", padx=(0, 6))
        self._button(bottom, "Open folder", self._open_folder).pack(side="left")

    def _button(self, parent, text, command):
        return tk.Button(parent, text=text, font=FONT_SMALL, bg=CARD, fg=TEXT_DIM, activebackground=BORDER,
                          activeforeground=TEXT, relief="flat", bd=0, padx=12, pady=8, cursor="hand2", command=command)

    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.after(0, lambda: self._append_log(line))

    def _append_log(self, line):
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")

    def _set_status(self, message, color=TEXT_DIM):
        self.after(0, lambda: (self.status_var.set(message), self.status_lbl.config(fg=color)))

    def _set_step(self, key, text, color):
        def update():
            for step_key, label in self._step_labels:
                if step_key == key:
                    label.config(text=text, fg=color)
        self.after(0, update)

    def _set_progress(self, value):
        self.after(0, lambda: self.progress.set(max(0, min(100, int(value)))))

    def _refresh_gpu_badge(self):
        if self.gpu_gen:
            generation = self.gpu_gen.replace("rtx", "RTX ").upper()
            self.gpu_badge.config(text=f"● {generation} Series", fg=GREEN)
        else:
            self.gpu_badge.config(text="● GPU unknown", fg=AMBER)

    def _browse(self):
        path = filedialog.askdirectory(title="Select Spider-Man 2 game folder")
        if path:
            self.game_path.set(path)
            self._refresh_installation_status()

    def _autodetect(self):
        found = find_spiderman2()
        if found:
            self.game_path.set(found)
            self._set_status(f"Found: {found}", GREEN)
            self._log(f"Game detected: {found}")
            self._refresh_installation_status()
        else:
            self._set_status("Spider-Man 2 was not found.", AMBER)
            self._log("Spider-Man 2 was not found.")

    def _open_folder(self):
        path = self.game_path.get().strip()
        if path and os.path.isdir(path):
            os.startfile(path)
        else:
            self._set_status("Set a valid game path first.", RED)

    def _refresh_installation_status(self):
        game_dir = self.game_path.get().strip()
        if not game_dir or not os.path.isdir(game_dir):
            for label in self.status_labels.values():
                label.config(text="Game path not set", fg=TEXT_MUTED)
            return
        files = find_game_files(game_dir)
        reshade = "reshade.ini" in files or "reshade.log" in files
        dlss = any(item in files for item in ["nvngx_dlss.dll", "nvngx.dll", "sl.common.dll", "sl.dlss.dll"])
        patch = "nvngx_dlssnr.dll" in files
        addon = "renodx-dlss.addon64" in files
        backup_dir = os.path.join(game_dir, ".dlss_manager_backups")
        backup = os.path.isdir(backup_dir)
        self._set_status_item("reshade", reshade, "Installed", "Not detected")
        self._set_status_item("dlss", dlss, "Detected", "Not detected")
        self._set_status_item("patch", patch, "Detected", "Not detected")
        self._set_status_item("addon", addon, "Installed", "Not detected")
        self._set_status_item("backup", backup, "Available", "No backup")

    def _set_status_item(self, key, condition, true_text, false_text):
        label = self.status_labels[key]
        label.config(text=f"✓ {true_text}" if condition else f"— {false_text}", fg=GREEN if condition else TEXT_MUTED)

    def _create_backup(self, game_dir):
        backup_root = os.path.join(game_dir, ".dlss_manager_backups")
        os.makedirs(backup_root, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(backup_root, timestamp)
        os.makedirs(backup_dir, exist_ok=True)
        files = find_game_files(game_dir)
        backed_up = []
        for path in files.values():
            if backup_root.lower() in path.lower():
                continue
            relative = os.path.relpath(path, game_dir)
            destination = os.path.join(backup_dir, relative)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(path, destination)
            backed_up.append(relative)
            self._log(f"Backup: {relative}")
        metadata = {"created": datetime.now().isoformat(), "game_directory": game_dir,
                    "files": backed_up, "gpu": self.gpu_gen, "manager_version": APP_VERSION}
        with open(os.path.join(backup_dir, "backup.json"), "w", encoding="utf-8") as file:
            json.dump(metadata, file, indent=2)
        self._log(f"Backup created: {backup_dir}")
        return backup_dir

    def _find_latest_backup(self, game_dir):
        root = os.path.join(game_dir, ".dlss_manager_backups")
        if not os.path.isdir(root):
            return None
        directories = [os.path.join(root, name) for name in os.listdir(root)
                       if os.path.isdir(os.path.join(root, name))]
        return max(directories, key=os.path.getmtime) if directories else None

    def _restore_backup(self):
        if self.install_running:
            return
        game_dir = self.game_path.get().strip()
        if not game_dir or not os.path.isdir(game_dir):
            messagebox.showerror("Invalid path", "Set a valid Spider-Man 2 directory first.")
            return
        backup = self._find_latest_backup(game_dir)
        if not backup:
            messagebox.showinfo("No backup", "No DLSS Manager backup was found.")
            return
        if not messagebox.askyesno("Restore backup", f"Restore the latest backup?\n\n{backup}\n\nCurrent modified files may be replaced."):
            return
        try:
            for root, dirs, files in os.walk(backup):
                for filename in files:
                    if filename == "backup.json":
                        continue
                    source = os.path.join(root, filename)
                    relative = os.path.relpath(source, backup)
                    destination = os.path.join(game_dir, relative)
                    if not is_within_directory(game_dir, destination):
                        raise RuntimeError(f"Unsafe restore path: {relative}")
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    shutil.copy2(source, destination)
                    self._log(f"Restored: {relative}")
            self._set_status("Backup restored successfully.", GREEN)
            self._refresh_installation_status()
            messagebox.showinfo("Restore complete", "The latest backup has been restored.")
        except Exception as error:
            self._log(f"Restore error: {error}")
            messagebox.showerror("Restore failed", str(error))

    def _download_and_verify(self, url, destination, expected_hash, progress_callback):
        filename = os.path.basename(destination)
        self._log(f"Downloading {filename}")
        download_file(url, destination, progress_callback)
        hash_result, hash_message = verify_hash(destination, expected_hash)
        self._log(hash_message)
        if hash_result is False:
            raise RuntimeError(f"SHA-256 verification failed for {filename}.")
        return hash_result

    def _install_reshade_safely(self, game_dir, reshade_exe):
        self._set_step("reshade", "checking signature...", AMBER)
        self._set_status("Checking ReShade installer signature...")
        signature_valid, signature_message = verify_windows_signature(reshade_exe)
        self._log(signature_message)
        if signature_valid is not True:
            raise RuntimeError("ReShade installer signature could not be confirmed as valid.\n\n"
                               f"{signature_message}\n\nFor safety, the installer was NOT executed.")
        confirmed = self._ask_main_thread("Run ReShade installer?",
            "The ReShade installer passed Windows Authenticode verification.\n\n"
            "The installer will now open and you must select the Spider-Man 2 executable.\n\n"
            "The manager will wait until ReShade closes.\n\nContinue?")
        if not confirmed:
            raise RuntimeError("User cancelled the ReShade installer.")
        self._set_step("reshade", "waiting...", AMBER)
        self._set_status("ReShade installer running...")
        self._log("Launching verified ReShade installer.")
        process = subprocess.Popen([reshade_exe], cwd=os.path.dirname(reshade_exe), shell=False)
        return_code = process.wait()
        self._log(f"ReShade installer exited with code {return_code}.")
        if return_code != 0:
            raise RuntimeError(f"ReShade installer exited with an error.\nExit code: {return_code}")
        time.sleep(1)
        files = find_game_files(game_dir)
        self._set_step("reshade", "✓ installed" if ("reshade.ini" in files or "reshade.log" in files) else "✓ installer finished", GREEN)
        self._set_progress(30)

    def _ask_main_thread(self, title, message):
        result = {"value": False}
        event = threading.Event()
        def ask():
            result["value"] = messagebox.askyesno(title, message, parent=self)
            event.set()
        self.after(0, ask)
        event.wait()
        return result["value"]

    def _extract_zip(self, zip_path, destination):
        self._log(f"Extracting {os.path.basename(zip_path)}")
        with zipfile.ZipFile(zip_path, "r") as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            if len(members) > 200:
                raise RuntimeError("Archive contains too many files.")
            total_size = sum(m.file_size for m in members)
            if total_size > 512 * 1024 * 1024:
                raise RuntimeError("Archive uncompressed size is too large.")
            seen = set()
            for member in members:
                normalized = member.filename.replace("\\", "/")
                filename = os.path.basename(normalized)
                if not filename or filename in {".", ".."} or "\x00" in filename:
                    continue
                if filename.lower() in seen:
                    raise RuntimeError(f"Duplicate archive filename: {filename}")
                seen.add(filename.lower())
                target = os.path.join(destination, filename)
                if not is_within_directory(destination, target):
                    raise RuntimeError(f"Unsafe archive path: {member.filename}")
                with archive.open(member) as source, open(target, "wb") as dest:
                    shutil.copyfileobj(source, dest)
                self._log(f"Extracted: {filename}")

    def _start_install(self):
        if self.install_running:
            return
        game_dir = self.game_path.get().strip()
        if not game_dir:
            messagebox.showerror("No path", "Set the Spider-Man 2 game directory first.")
            return
        if not os.path.isdir(game_dir):
            messagebox.showerror("Invalid path", f"Directory not found:\n{game_dir}")
            return
        if not messagebox.askyesno("Install / Update",
            "A backup will be created before any game files are changed.\n\n"
            "The ReShade installer will require your confirmation before it is executed.\n\nContinue?"):
            return
        self.install_running = True
        self.install_btn.config(state="disabled", text="INSTALLING...")
        self.restore_btn.config(state="disabled")
        self.verify_btn.config(state="disabled")
        self.progress.set(0)
        threading.Thread(target=self._install_thread, args=(game_dir,), daemon=True).start()

    def _install_thread(self, game_dir):
        temporary_dir = tempfile.mkdtemp(prefix="dlss5_mgr_")
        try:
            self._run_install(game_dir, temporary_dir)
        except Exception as error:
            self._log(f"INSTALLATION ERROR: {error}")
            self._set_status(f"Error: {error}", RED)
            self.after(0, lambda: messagebox.showerror("Install failed", str(error)))
        finally:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            self.install_running = False
            self.after(0, self._installation_finished)

    def _installation_finished(self):
        self.install_btn.config(state="normal", text="INSTALL / UPDATE")
        self.restore_btn.config(state="normal")
        self.verify_btn.config(state="normal")
        self._refresh_installation_status()

    def _run_install(self, game_dir, temporary_dir):
        self._set_step("backup", "creating...", AMBER)
        self._set_status("Creating backup...")
        self._set_progress(5)
        backup_dir = self._create_backup(game_dir)
        if not backup_dir:
            raise RuntimeError("Backup could not be created.")
        self._set_step("backup", "✓ created", GREEN)
        self._set_progress(10)

        self._set_step("reshade", "downloading...", AMBER)
        self._set_status("Downloading ReShade...")
        reshade_path = os.path.join(temporary_dir, "ReShade_Setup_6.8.0_Addon.exe")
        self._download_and_verify(URL_RESHADE, reshade_path, EXPECTED_HASHES["ReShade_Setup_6.8.0_Addon.exe"],
                                  lambda p: self._set_progress(10 + int(p * 0.15)))
        self._install_reshade_safely(game_dir, reshade_path)

        self._set_step("dlss", "downloading...", AMBER)
        self._set_status("Downloading DLSS + Streamline...")
        zip_path = os.path.join(temporary_dir, "DLSS_Streamline.zip")
        self._download_and_verify(URL_DLSS_ZIP, zip_path, EXPECTED_HASHES["DLSS_Streamline.zip"],
                                  lambda p: self._set_progress(30 + int(p * 0.20)))
        files = find_game_files(game_dir)
        dlss_destination = game_dir
        for filename in ["nvngx_dlss.dll", "nvngx.dll", "sl.common.dll", "sl.dlss.dll"]:
            if filename in files:
                dlss_destination = os.path.dirname(files[filename])
                break
        self._log(f"DLSS destination: {dlss_destination}")
        self._extract_zip(zip_path, dlss_destination)
        self._set_step("dlss", "✓ installed", GREEN)
        self._set_progress(55)

        self._set_step("patch", "downloading...", AMBER)
        self._set_status("Downloading patched DLSS-NR DLL...")
        patch_path = os.path.join(temporary_dir, "nvngx_dlssnr.dll")
        self._download_and_verify(URL_DLSS_PATCH, patch_path, EXPECTED_HASHES["nvngx_dlssnr.dll"],
                                  lambda p: self._set_progress(55 + int(p * 0.15)))
        patch_destination = os.path.join(dlss_destination, "nvngx_dlssnr.dll")
        shutil.copy2(patch_path, patch_destination)
        self._log(f"Installed: {patch_destination}")
        self._set_step("patch", "✓ installed", GREEN)
        self._set_progress(70)

        self._set_step("addon", "downloading...", AMBER)
        self._set_status("Downloading RenoDX DLSS addon...")
        addon_path = os.path.join(temporary_dir, "renodx-dlss.addon64")
        self._download_and_verify(URL_ADDON, addon_path, EXPECTED_HASHES["renodx-dlss.addon64"],
                                  lambda p: self._set_progress(70 + int(p * 0.15)))
        files = find_game_files(game_dir)
        reshade_destination = os.path.dirname(files["reshade.ini"]) if "reshade.ini" in files else game_dir
        if "reshade.ini" not in files:
            self._log("ReShade.ini not found; using game directory.")
        conflict = os.path.join(reshade_destination, "renodx-dlss5.addon64")
        if os.path.isfile(conflict):
            conflict_backup = unique_backup_name(conflict)
            shutil.move(conflict, conflict_backup)
            self._log(f"Moved conflicting addon to: {conflict_backup}")
        addon_destination = os.path.join(reshade_destination, "renodx-dlss.addon64")
        shutil.copy2(addon_path, addon_destination)
        self._log(f"Installed: {addon_destination}")
        self._set_step("addon", "✓ installed", GREEN)
        self._set_progress(90)

        self._set_step("verify", "checking...", AMBER)
        self._set_status("Verifying installation...")
        verification = self._verify_installation(game_dir)
        if not verification["ok"]:
            self._set_step("verify", "⚠ warnings", AMBER)
            self._set_progress(95)
            details = "\n".join("• " + item for item in verification["missing"])
            self._set_status("Installation completed with warnings.", AMBER)
            self._log("Verification warnings:")
            for item in verification["missing"]:
                self._log(f"Missing: {item}")
            self.after(0, lambda: messagebox.showwarning("Installation completed with warnings",
                f"Some components were not detected:\n\n{details}\n\nYou may need to finish configuring ReShade manually."))
        else:
            self._set_step("verify", "✓ verified", GREEN)
            self._set_progress(100)
            self._set_status("Installation complete and verified.", GREEN)
            self._log("Installation successfully verified.")
            self.after(0, self._show_done)

    def _verify_installation(self, game_dir):
        files = find_game_files(game_dir)
        missing = []
        if "reshade.ini" not in files and "reshade.log" not in files:
            missing.append("ReShade configuration/log not detected")
        if not any(item in files for item in ["nvngx_dlss.dll", "nvngx.dll"]):
            missing.append("DLSS runtime not detected")
        if "nvngx_dlssnr.dll" not in files:
            missing.append("nvngx_dlssnr.dll not detected")
        if "renodx-dlss.addon64" not in files:
            missing.append("renodx-dlss.addon64 not detected")
        return {"ok": not missing, "missing": missing, "files": files}

    def _verify_clicked(self):
        game_dir = self.game_path.get().strip()
        if not game_dir or not os.path.isdir(game_dir):
            messagebox.showerror("Invalid path", "Set a valid Spider-Man 2 directory first.")
            return
        result = self._verify_installation(game_dir)
        if result["ok"]:
            self._set_status("Installation verified successfully.", GREEN)
            messagebox.showinfo("Verification successful", "All expected components were detected.")
        else:
            missing = "\n".join("• " + item for item in result["missing"])
            self._set_status("Verification found missing components.", AMBER)
            messagebox.showwarning("Verification", "Some components were not detected:\n\n" + missing)
        self._refresh_installation_status()

    def _show_done(self):
        messagebox.showinfo("Installation complete",
            "DLSS Manager finished successfully.\n\nRecommended next steps:\n\n"
            "1. Launch Spider-Man 2.\n2. Press INS to open ReShade.\n"
            "3. Configure the RenoDX DLSS addon.\n\nA backup was created before installation.\n"
            "Use 'Restore backup' if you need to revert.")


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = DLSSManager()
    app.mainloop()
