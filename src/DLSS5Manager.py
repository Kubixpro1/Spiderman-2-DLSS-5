import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import winreg
import zipfile
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from updater import apply_update
except ImportError:
    apply_update = None

APP_NAME = "DLSS 5 Manager"
APP_VERSION = "2.2.0"
CONFIG_BASE = "https://raw.githubusercontent.com/Kubixpro1/Spiderman-2-DLSS-5/main/config/"
COMPONENTS_URL = CONFIG_BASE + "components.json"
VERSION_URL = CONFIG_BASE + "version.json"
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_ZIP_FILES = 500
MAX_ZIP_UNCOMPRESSED = 2 * 1024 * 1024 * 1024

BG, CARD, BORDER = "#0f0f0f", "#1a1a1a", "#2a2a2a"
ACCENT, TEXT, TEXT_DIM, TEXT_MUTED = "#e8003d", "#f0f0f0", "#888888", "#555555"
GREEN, AMBER, RED = "#22c55e", "#f59e0b", "#ef4444"
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO = ("Consolas", 9)
GAME_NAME = "Marvel's Spider-Man 2"

FALLBACK_COMPONENTS = {
    "reshade": {"name": "ReShade 6.8.0 Add-on", "version": "6.8.0", "url": "https://reshade.me/downloads/ReShade_Setup_6.8.0_Addon.exe", "sha256": "", "requires_authenticode": True, "kind": "exe"},
    "dlss_streamline": {"name": "DLSS 3.10.8.0 + Streamline 2.13", "version": "3.10.8.0-streamline-2.13", "url": "https://cdn.discordapp.com/attachments/1543975158937821315/1543977625226182827/DLSS310.8.0-Streamline2.13.zip?ex=6aa403b7&is=6aa2b237&hm=e8309e81114238473664557b896bde2ef0bb9f7d8b54f6f2a66f2ea6bf6af02&", "sha256": "", "kind": "zip"},
    "nvngx_dlssnr": {"name": "Patched nvngx_dlssnr.dll", "version": "managed", "url": "https://cdn.discordapp.com/attachments/1543976771920330884/1543982044797866107/nvngx_dlssnr.dll?ex=6aa407d5&is=6aa2b655&hm=2ba08e80f7f791bbcfc0880039e278a1cebbcb00b47365e669305b9686e6bf86&", "sha256": "", "kind": "dll"},
    "renodx_dlss": {"name": "renodx-dlss.addon64", "version": "managed", "url": "https://cdn.discordapp.com/attachments/1545049227321810974/1545877902715920504/renodx-dlss.addon64?ex=6aa3ad3d&is=6aa25bbd&hm=e195687a64529ab6fb52d0eb35769a00a83579b295e3b5083b7432a5417a9485&", "sha256": "", "kind": "addon"},
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def safe_path(base, target):
    try:
        return os.path.commonpath([os.path.abspath(base), os.path.abspath(target)]) == os.path.abspath(base)
    except ValueError:
        return False


def download_file(url, destination, progress=None):
    if not url.startswith("https://"):
        raise RuntimeError("Only HTTPS downloads are allowed.")
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    part = destination + ".part"
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            if total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("Remote file exceeds the download size limit.")
            while chunk := response.read(256 * 1024):
                downloaded += len(chunk)
                if downloaded > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError("Download exceeded the size limit.")
                out.write(chunk)
                if progress and total:
                    progress(min(100, int(downloaded * 100 / total)))
        if downloaded == 0:
            raise RuntimeError("Downloaded file is empty.")
        os.replace(part, destination)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e
    finally:
        if os.path.exists(part):
            try: os.remove(part)
            except OSError: pass


def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_hash(path, expected):
    if not expected:
        return None, "SHA-256 not configured in manifest."
    actual = sha256_file(path)
    return (True, f"SHA-256 verified: {actual}") if actual.lower() == expected.lower() else (False, f"SHA-256 mismatch. Expected {expected}, got {actual}")


def verify_authenticode(path):
    env = os.environ.copy(); env["DLSS_MANAGER_FILE"] = os.path.abspath(path)
    ps = "$s=Get-AuthenticodeSignature -LiteralPath $env:DLSS_MANAGER_FILE; [string]$s.Status"
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, capture_output=True, text=True, timeout=20)
        status = result.stdout.strip()
        return status.lower() == "valid", f"Authenticode: {status or 'no status'}"
    except Exception as e:
        return False, f"Authenticode check failed: {e}"


def detect_gpu_gen():
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"], capture_output=True, text=True, timeout=5)
        n = r.stdout.lower()
        for gen, needles in (("rtx50", ("rtx 50", "5050", "5060", "5070", "5080", "5090")), ("rtx40", ("rtx 40", "4050", "4060", "4070", "4080", "4090")), ("rtx30", ("rtx 30", "3050", "3060", "3070", "3080", "3090")), ("rtx20", ("rtx 20", "2060", "2070", "2080"))):
            if any(x in n for x in needles): return gen
    except Exception: pass
    return None


def steam_path():
    for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"), (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"), (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
        try:
            with winreg.OpenKey(hive, key) as k:
                for value in ("SteamPath", "InstallPath"):
                    try:
                        p = winreg.QueryValueEx(k, value)[0]
                        if os.path.isdir(p): return os.path.normpath(p)
                    except FileNotFoundError: pass
        except OSError: pass
    return None


def find_spiderman2():
    root = steam_path()
    if not root: return None
    libraries = [root]
    vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(vdf):
        try:
            text = Path(vdf).read_text(encoding="utf-8", errors="ignore")
            libraries += re.findall(r'"path"\s*"([^"]+)"', text)
        except OSError: pass
    for lib in dict.fromkeys(libraries):
        common = os.path.join(lib.replace("\\\\", "\\"), "steamapps", "common")
        if not os.path.isdir(common): continue
        for name in ("Marvel's Spider-Man 2", "Marvels Spider-Man 2"):
            candidate = os.path.join(common, name)
            if os.path.isdir(candidate): return candidate
        for entry in os.listdir(common):
            if "spider" in entry.lower() and "man" in entry.lower() and os.path.isdir(os.path.join(common, entry)):
                return os.path.join(common, entry)
    return None


def find_game_files(game_dir):
    wanted = {x.lower() for x in ("nvngx_dlss.dll", "nvngx_dlssnr.dll", "nvngx.dll", "sl.common.dll", "sl.dlss.dll", "reshade.ini", "reshade.log", "renodx-dlss.addon64", "renodx-dlss5.addon64", "dxgi.dll", "d3d12.dll")}
    found = {}
    for root, dirs, files in os.walk(game_dir):
        dirs[:] = [d for d in dirs if d.lower() != ".dlss_manager_backups"]
        for name in files:
            if name.lower() in wanted: found.setdefault(name.lower(), os.path.join(root, name))
    return found


def safe_extract(zip_path, destination, log):
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        if len(members) > MAX_ZIP_FILES: raise RuntimeError("Archive contains too many files.")
        if sum(m.file_size for m in members) > MAX_ZIP_UNCOMPRESSED: raise RuntimeError("Archive is too large when unpacked.")
        seen = set()
        for m in members:
            name = m.filename.replace("\\", "/")
            base = os.path.basename(name)
            if not base or base in seen: raise RuntimeError(f"Unsafe or duplicate archive entry: {m.filename}")
            seen.add(base)
            target = os.path.join(destination, base)
            if not safe_path(destination, target): raise RuntimeError(f"Unsafe archive path: {m.filename}")
        for m in members:
            base = os.path.basename(m.filename.replace("\\", "/"))
            target = os.path.join(destination, base)
            with z.open(m) as src, open(target, "wb") as dst: shutil.copyfileobj(src, dst, 1024 * 1024)
            log(f"Extracted: {base}")


class DLSSManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION} — Spider-Man 2")
        self.geometry("820x760"); self.resizable(False, False); self.configure(bg=BG)
        self.gpu = detect_gpu_gen(); self.running = False
        self.game_path = tk.StringVar(value=find_spiderman2() or "")
        self.status = tk.StringVar(value="Ready."); self.progress = tk.IntVar(value=0)
        self.steps = {}; self.labels = {}
        self.components = FALLBACK_COMPONENTS.copy(); self.remote_version = None
        self.build_ui(); self.refresh_status()
        self.after(500, self.check_updates)

    def button(self, parent, text, command):
        return tk.Button(parent, text=text, font=FONT_SMALL, bg=CARD, fg=TEXT_DIM, activebackground=BORDER, activeforeground=TEXT, relief="flat", bd=0, padx=12, pady=8, command=command, cursor="hand2")

    def ui(self, fn): self.after(0, fn)
    def log(self, text): self.ui(lambda: (self.logbox.insert("end", f"[{datetime.now():%H:%M:%S}] {text}\n"), self.logbox.see("end")))
    def set_status(self, text, color=TEXT_DIM): self.ui(lambda: (self.status.set(text), self.status_label.config(fg=color)))
    def step(self, key, text, color): self.ui(lambda: self.steps[key].config(text=text, fg=color))
    def prog(self, value): self.ui(lambda: self.progress.set(max(0, min(100, int(value)))))

    def build_ui(self):
        tk.Frame(self, bg=ACCENT, height=4).pack(fill="x")
        header=tk.Frame(self,bg=CARD,pady=15); header.pack(fill="x")
        tk.Label(header,text="DLSS 5 Manager",font=FONT_TITLE,bg=CARD,fg=TEXT).pack(side="left",padx=(24,8))
        tk.Label(header,text="Spider-Man 2",font=("Segoe UI",11),bg=CARD,fg=TEXT_DIM).pack(side="left")
        badge=f"● {self.gpu.replace('rtx','RTX ').upper()} Series" if self.gpu else "● GPU unknown"
        tk.Label(header,text=badge,font=FONT_SMALL,bg=CARD,fg=GREEN if self.gpu else AMBER,padx=12).pack(side="right",padx=24)
        body=tk.Frame(self,bg=BG,padx=24,pady=14); body.pack(fill="both",expand=True)
        tk.Label(body,text="GAME DIRECTORY",font=("Segoe UI",8,"bold"),bg=BG,fg=TEXT_MUTED).pack(anchor="w")
        row=tk.Frame(body,bg=BG,pady=4); row.pack(fill="x")
        tk.Entry(row,textvariable=self.game_path,font=FONT_MONO,bg=CARD,fg=TEXT,insertbackground=TEXT,relief="flat",highlightthickness=1,highlightbackground=BORDER).pack(side="left",fill="x",expand=True,ipady=7,padx=(0,6))
        self.button(row,"Browse",self.browse).pack(side="left",padx=2); self.button(row,"Auto-detect",self.autodetect).pack(side="left",padx=2)
        self.button(row,"Check updates",self.check_updates).pack(side="left",padx=2)
        tk.Label(body,text="INSTALLATION STATUS",font=("Segoe UI",8,"bold"),bg=BG,fg=TEXT_MUTED).pack(anchor="w",pady=(12,5))
        card=tk.Frame(body,bg=CARD,highlightthickness=1,highlightbackground=BORDER); card.pack(fill="x")
        for i,(key,name) in enumerate((("reshade","ReShade"),("dlss","DLSS / Streamline"),("patch","DLSS-NR patched DLL"),("addon","RenoDX DLSS addon"),("backup","Backup"))):
            r=tk.Frame(card,bg=CARD); r.pack(fill="x",pady=4); tk.Label(r,text=name,font=FONT_BODY,bg=CARD,fg=TEXT,width=23,anchor="w").pack(side="left",padx=12)
            l=tk.Label(r,text="Checking...",font=FONT_SMALL,bg=CARD,fg=TEXT_DIM); l.pack(side="right",padx=12); self.labels[key]=l
            if i<4: tk.Frame(card,bg=BORDER,height=1).pack(fill="x")
        tk.Label(body,text="INSTALLATION STEPS",font=("Segoe UI",8,"bold"),bg=BG,fg=TEXT_MUTED).pack(anchor="w",pady=(12,5))
        steps_frame=tk.Frame(body,bg=CARD,highlightthickness=1,highlightbackground=BORDER); steps_frame.pack(fill="x")
        for i,(key,text) in enumerate((("backup","Create backup"),("reshade","Download & safely launch ReShade"),("dlss","Install DLSS + Streamline"),("patch","Install patched DLSS-NR DLL"),("addon","Install RenoDX DLSS addon"),("verify","Verify installation")),1):
            r=tk.Frame(steps_frame,bg=CARD); r.pack(fill="x"); tk.Label(r,text=str(i),font=("Segoe UI",9,"bold"),bg=ACCENT,fg="white",width=3,pady=7).pack(side="left"); tk.Label(r,text=text,font=FONT_BODY,bg=CARD,fg=TEXT,anchor="w").pack(side="left",padx=12,fill="x",expand=True)
            l=tk.Label(r,text="—",font=FONT_SMALL,bg=CARD,fg=TEXT_MUTED,padx=12); l.pack(side="right"); self.steps[key]=l
            if i<6: tk.Frame(steps_frame,bg=BORDER,height=1).pack(fill="x")
        tk.Label(body,text="PROGRESS",font=("Segoe UI",8,"bold"),bg=BG,fg=TEXT_MUTED).pack(anchor="w",pady=(12,4))
        ttk.Style(self).configure("Red.Horizontal.TProgressbar",troughcolor=CARD,background=ACCENT,lightcolor=ACCENT,darkcolor=ACCENT,thickness=8)
        ttk.Progressbar(body,variable=self.progress,maximum=100,style="Red.Horizontal.TProgressbar").pack(fill="x")
        self.status_label=tk.Label(body,textvariable=self.status,font=FONT_MONO,bg=BG,fg=TEXT_DIM,anchor="w"); self.status_label.pack(fill="x",pady=4)
        tk.Label(body,text="LOG",font=("Segoe UI",8,"bold"),bg=BG,fg=TEXT_MUTED).pack(anchor="w",pady=(4,3))
        lf=tk.Frame(body,bg=CARD,highlightthickness=1,highlightbackground=BORDER); lf.pack(fill="both",expand=True)
        self.logbox=tk.Text(lf,height=6,bg=CARD,fg=TEXT_DIM,font=FONT_MONO,relief="flat",wrap="word"); self.logbox.pack(fill="both",expand=True,padx=6,pady=6)
        bottom=tk.Frame(self,bg=CARD,pady=10,padx=24); bottom.pack(fill="x")
        self.install_btn=tk.Button(bottom,text="INSTALL / UPDATE",font=("Segoe UI",10,"bold"),bg=ACCENT,fg="white",activebackground="#c0002e",relief="flat",bd=0,padx=18,pady=9,command=self.start_install); self.install_btn.pack(side="right")
        self.button(bottom,"Restore backup",self.restore_backup).pack(side="right",padx=6); self.button(bottom,"Verify",self.verify_clicked).pack(side="right",padx=6); self.button(bottom,"Open folder",self.open_folder).pack(side="left")

    def load_components(self):
        try:
            data=fetch_json(COMPONENTS_URL); components=data.get("components",{})
            for key in FALLBACK_COMPONENTS:
                if key in components and components[key].get("url"): self.components[key]={**FALLBACK_COMPONENTS[key],**components[key]}
            self.log("Loaded remote components.json")
        except Exception as e: self.log(f"Remote component manifest unavailable; using built-in fallback: {e}")

    def check_updates(self):
        def worker():
            try:
                data=fetch_json(VERSION_URL); remote=data.get("app",{}); self.remote_version=remote.get("version")
                if self.remote_version and self.remote_version != APP_VERSION:
                    msg=f"A manager update is available: {APP_VERSION} → {self.remote_version}.\n\nUpdate now?"
                    if self.ask("Update available",msg):
                        if not apply_update: raise RuntimeError("Updater module is unavailable in this build.")
                        apply_update(remote.get("download_url",""),remote.get("sha256") or None)
                        self.log("Update downloaded. Restarting..."); self.after(500,self.destroy)
                else: self.set_status("Manager is up to date.",GREEN)
            except Exception as e: self.log(f"Update check: {e}")
        threading.Thread(target=worker,daemon=True).start()

    def ask(self,title,text):
        result={"v":False}; event=threading.Event()
        self.after(0,lambda:(result.__setitem__("v",messagebox.askyesno(title,text,parent=self)),event.set()))
        event.wait(); return result["v"]

    def browse(self):
        p=filedialog.askdirectory(title="Select Spider-Man 2 game folder")
        if p: self.game_path.set(p); self.refresh_status()
    def autodetect(self):
        p=find_spiderman2()
        if p: self.game_path.set(p); self.set_status(f"Found: {p}",GREEN); self.refresh_status()
        else: self.set_status("Spider-Man 2 was not found.",AMBER)
    def open_folder(self):
        p=self.game_path.get().strip()
        if os.path.isdir(p): os.startfile(p)
        else: messagebox.showerror("Invalid path","Set a valid game path first.")

    def refresh_status(self):
        p=self.game_path.get().strip()
        if not os.path.isdir(p):
            for l in self.labels.values(): l.config(text="Game path not set",fg=TEXT_MUTED)
            return
        f=find_game_files(p)
        checks={"reshade":("✓ Installed" if "reshade.ini" in f or "reshade.log" in f or "dxgi.dll" in f or "d3d12.dll" in f else "— Not detected"),"dlss":("✓ Detected" if any(x in f for x in ("nvngx_dlss.dll","nvngx.dll","sl.common.dll","sl.dlss.dll")) else "— Not detected"),"patch":("✓ Detected" if "nvngx_dlssnr.dll" in f else "— Not detected"),"addon":("✓ Installed" if "renodx-dlss.addon64" in f else "— Not detected"),"backup":("✓ Available" if os.path.isdir(os.path.join(p,".dlss_manager_backups")) else "— No backup")}
        for k,v in checks.items(): self.labels[k].config(text=v,fg=GREEN if v.startswith("✓") else TEXT_MUTED)

    def create_backup(self,p):
        root=os.path.join(p,".dlss_manager_backups"); stamp=datetime.now().strftime("%Y%m%d_%H%M%S"); out=os.path.join(root,stamp); os.makedirs(out,exist_ok=True)
        files=find_game_files(p); manifest={"created":datetime.now().isoformat(),"game_directory":p,"files":[]}
        for src in files.values():
            if not safe_path(p,src): continue
            rel=os.path.relpath(src,p); dst=os.path.join(out,rel); os.makedirs(os.path.dirname(dst),exist_ok=True); shutil.copy2(src,dst); manifest["files"].append(rel)
        with open(os.path.join(out,"backup.json"),"w",encoding="utf-8") as f: json.dump(manifest,f,indent=2)
        self.log(f"Backup created: {out}"); return out

    def latest_backup(self,p):
        root=os.path.join(p,".dlss_manager_backups")
        dirs=[os.path.join(root,x) for x in os.listdir(root)] if os.path.isdir(root) else []
        dirs=[x for x in dirs if os.path.isdir(x)]
        return max(dirs,key=os.path.getmtime) if dirs else None

    def restore_backup(self):
        p=self.game_path.get().strip(); b=self.latest_backup(p) if os.path.isdir(p) else None
        if not b: messagebox.showinfo("No backup","No DLSS Manager backup was found."); return
        if not messagebox.askyesno("Restore backup",f"Restore the latest backup?\n\n{b}"): return
        try:
            for root,_,files in os.walk(b):
                for name in files:
                    if name=="backup.json": continue
                    src=os.path.join(root,name); rel=os.path.relpath(src,b); dst=os.path.join(p,rel)
                    if not safe_path(p,dst): raise RuntimeError("Unsafe restore path.")
                    os.makedirs(os.path.dirname(dst),exist_ok=True); shutil.copy2(src,dst)
            self.set_status("Backup restored.",GREEN); self.refresh_status()
        except Exception as e: messagebox.showerror("Restore failed",str(e))

    def download_component(self,key,tmp,progress):
        c=self.components[key]; name={"reshade":"ReShade_Setup_6.8.0_Addon.exe","dlss_streamline":"DLSS_Streamline.zip","nvngx_dlssnr":"nvngx_dlssnr.dll","renodx_dlss":"renodx-dlss.addon64"}[key]; path=os.path.join(tmp,name)
        if not c.get("url"): raise RuntimeError(f"No URL configured for {c.get('name',key)}")
        download_file(c["url"],path,progress)
        expected=c.get("sha256") or ""; ok,msg=verify_hash(path,expected); self.log(msg)
        if ok is False: raise RuntimeError(msg)
        if c.get("requires_authenticode"):
            valid,msg=verify_authenticode(path); self.log(msg)
            if not valid: raise RuntimeError("ReShade installer did not pass Authenticode verification.")
        with open(path,"rb") as f: magic=f.read(4)
        if c.get("kind") in ("exe","dll","addon") and magic[:2] != b"MZ": raise RuntimeError(f"{name} is not a valid Windows PE file.")
        if c.get("kind")=="zip" and magic[:2] != b"PK": raise RuntimeError("DLSS archive is not a ZIP file.")
        return path

    def start_install(self):
        if self.running:return
        p=self.game_path.get().strip()
        if not os.path.isdir(p): messagebox.showerror("Invalid path","Set a valid Spider-Man 2 directory first."); return
        if not self.ask("Install / Update","A backup will be created. ReShade will only run after Authenticode verification and your confirmation. Continue?"): return
        self.running=True; self.install_btn.config(state="disabled",text="INSTALLING..."); self.progress.set(0)
        threading.Thread(target=self.install_worker,args=(p,),daemon=True).start()

    def install_worker(self,p):
        tmp=tempfile.mkdtemp(prefix="dlss5_mgr_")
        try:
            self.load_components(); self.step("backup","creating...",AMBER); self.create_backup(p); self.step("backup","✓ created",GREEN); self.prog(10)
            self.step("reshade","downloading...",AMBER); reshade=self.download_component("reshade",tmp,lambda x:self.prog(10+int(x*.15)))
            if not self.ask("Run ReShade installer?","Authenticode verification passed.\n\nReShade will open and you must select the Spider-Man 2 executable.\n\nContinue?"):
                raise RuntimeError("ReShade installer cancelled by user.")
            self.log("Launching verified ReShade installer and waiting for it to close.")
            proc=subprocess.Popen([reshade],cwd=os.path.dirname(reshade),shell=False); code=proc.wait()
            if code!=0: raise RuntimeError(f"ReShade installer exited with code {code}.")
            time.sleep(1); self.step("reshade","✓ installer finished",GREEN); self.prog(30)
            files=find_game_files(p); dest=p
            for n in ("nvngx_dlss.dll","nvngx.dll","sl.common.dll","sl.dlss.dll"):
                if n in files: dest=os.path.dirname(files[n]); break
            self.step("dlss","downloading...",AMBER); archive=self.download_component("dlss_streamline",tmp,lambda x:self.prog(30+int(x*.20))); safe_extract(archive,dest,self.log); self.step("dlss","✓ installed",GREEN); self.prog(55)
            self.step("patch","downloading...",AMBER); patch=self.download_component("nvngx_dlssnr",tmp,lambda x:self.prog(55+int(x*.15))); shutil.copy2(patch,os.path.join(dest,"nvngx_dlssnr.dll")); self.step("patch","✓ installed",GREEN); self.prog(70)
            self.step("addon","downloading...",AMBER); addon=self.download_component("renodx_dlss",tmp,lambda x:self.prog(70+int(x*.15))); files=find_game_files(p); adest=os.path.dirname(files["reshade.ini"]) if "reshade.ini" in files else p
            old=os.path.join(adest,"renodx-dlss5.addon64")
            if os.path.isfile(old): shutil.move(old,old+f".backup_{datetime.now():%Y%m%d_%H%M%S}")
            shutil.copy2(addon,os.path.join(adest,"renodx-dlss.addon64")); self.step("addon","✓ installed",GREEN); self.prog(90)
            result=self.verify_install(p); self.step("verify","✓ verified" if result["ok"] else "⚠ warnings",GREEN if result["ok"] else AMBER); self.prog(100); self.set_status("Installation complete." if result["ok"] else "Installation completed with warnings.",GREEN if result["ok"] else AMBER)
            self.log("Installation finished.")
            self.after(0,lambda: messagebox.showinfo("Complete","DLSS Manager finished. A backup was created before changes."))
        except Exception as e:
            self.log(f"INSTALLATION ERROR: {e}"); self.set_status(f"Error: {e}",RED); self.after(0,lambda:messagebox.showerror("Install failed",str(e)))
        finally:
            shutil.rmtree(tmp,ignore_errors=True); self.running=False; self.after(0,lambda:self.install_btn.config(state="normal",text="INSTALL / UPDATE")); self.after(0,self.refresh_status)

    def verify_install(self,p):
        f=find_game_files(p); missing=[]
        if not any(x in f for x in ("reshade.ini","reshade.log","dxgi.dll","d3d12.dll")): missing.append("ReShade files not detected")
        if not any(x in f for x in ("nvngx_dlss.dll","nvngx.dll","sl.common.dll","sl.dlss.dll")): missing.append("DLSS runtime not detected")
        if "nvngx_dlssnr.dll" not in f: missing.append("nvngx_dlssnr.dll not detected")
        if "renodx-dlss.addon64" not in f: missing.append("renodx-dlss.addon64 not detected")
        for x in missing:self.log("Missing: "+x)
        return {"ok":not missing,"missing":missing,"files":f}

    def verify_clicked(self):
        p=self.game_path.get().strip()
        if not os.path.isdir(p): messagebox.showerror("Invalid path","Set a valid Spider-Man 2 directory first."); return
        r=self.verify_install(p); self.refresh_status()
        if r["ok"]: messagebox.showinfo("Verification","All expected components were detected.")
        else: messagebox.showwarning("Verification","Missing:\n\n"+"\n".join("• "+x for x in r["missing"]))


if __name__ == "__main__":
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception: pass
    DLSSManager().mainloop()
