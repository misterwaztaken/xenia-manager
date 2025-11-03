import tkinter as tk
from PIL import Image, ImageTk
from tkinter import ttk, messagebox, filedialog, simpledialog, PhotoImage
import os
import json
import subprocess
import zipfile
import sys
import shutil
import requests
import pathlib

# Optional drag-and-drop support via tkinterdnd2 (recommended on Windows)
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAVE_TKDN = True
except Exception:
    HAVE_TKDN = False

# File to store labels (placed in parent folder of the "Xbox 360 Dashboards" folder)
def get_labels_path():
    dash_folder = os.path.abspath("Xbox 360 Dashboards")
    if os.path.exists(dash_folder):
        parent = os.path.dirname(dash_folder)
    else:
        parent = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(parent, "dashboard_labels.json")

def refresh_trees():
    populate_dashboards_tree()
    populate_games_tree()


def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to create directory '{path}': {e}")
        return False


def add_dashboard():
    name = simpledialog.askstring("New Dashboard", "Enter folder name for new dashboard:")
    if not name:
        return
    dash_dir = os.path.join("Xbox 360 Dashboards", name)
    if ensure_dir(dash_dir):
        messagebox.showinfo("Created", f"Created dashboard folder: {name}")
        refresh_trees()


def import_dashboard():
    paths = filedialog.askopenfilenames(title="Select .xex files to import", filetypes=[("XEX files", "*.xex" )])
    if not paths:
        return
    name = simpledialog.askstring("Import Dashboard", "Enter folder name to import into (will be created):")
    if not name:
        return
    dash_dir = os.path.join("Xbox 360 Dashboards", name)
    if not ensure_dir(dash_dir):
        return
    for p in paths:
        try:
            dest = os.path.join(dash_dir, os.path.basename(p))
            shutil.copy2(p, dest)
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to copy '{p}' to '{dash_dir}': {e}")
            return
    messagebox.showinfo("Imported", f"Imported {len(paths)} file(s) into '{name}'")
    refresh_trees()

def update_xenia(emulator, version=None):
    """
    Update Xenia to a specific version or the latest version
    :param emulator: Either 'xenia-canary' or 'xenia-stable'
    :param version: Optional specific version to install
    """
    
    # Parse emulator type
    if emulator == "xenia-canary":
        OWNER = "xenia-canary"
        REPO = "xenia-canary-releases"
    elif emulator == "xenia-stable":
        OWNER = "xenia-project"
        REPO = "release-builds-windows"
    elif emulator == "xenia-oldercanary":
        OWNER = "xenia-canary"
        REPO = "xenia-canary" # older releases were kept at the xenia-canary repo
    else:
        messagebox.showerror("Error", "Invalid emulator type specified: " + emulator)
        return
        
    # Create progress popup
    popup = tk.Toplevel()
    popup.title(f"{emulator} Update")
    popup.geometry("400x150")
    
    # Create and pack widgets
    status_var = tk.StringVar(value="Preparing update...")
    progress_var = tk.StringVar(value="")
    
    status_label = ttk.Label(popup, textvariable=status_var)
    status_label.pack(padx=20, pady=(20, 6))
    
    progress_bar = ttk.Progressbar(popup, mode='determinate')
    progress_bar.pack(fill='x', padx=20, pady=6)
    
    progress_label = ttk.Label(popup, textvariable=progress_var)
    progress_label.pack(padx=20, pady=6)

    cancel_state = {"cancelled": False}
    def cancel_update():
        cancel_state["cancelled"] = True
        popup.destroy()
    
    cancel_btn = ttk.Button(popup, text="Cancel", command=cancel_update)
    cancel_btn.pack(pady=6)

    # Ensure popup appears
    popup.update()
    orig_Toplevel = tk.Toplevel
    orig_Label = tk.Label

    # optional cancel state (can be checked later if you add cancellation support)
    cancel_state = {"cancelled": False}
    def _cancel():
        cancel_state["cancelled"] = True
        status_label.config(text="Cancelled by user.")
    tk.Button(popup, text="Cancel", command=_cancel).pack(pady=(0, 12))

    # ensure popup appears immediately
    popup.update_idletasks()
    popup.update()

    # override tk.Label so subsequent calls in this function update our existing labels
    def _label_override(*args, **kwargs):
        text = kwargs.get("text", "")
        if isinstance(text, str):
            lower = text.lower()
            # heuristics: status vs progress
            if "download" in lower or "install" in lower or "prepar" in lower:
                status_label.config(text=text)
            else:
                progress_label.config(text=text)
        # return a dummy object that supports .pack() and .config() to satisfy callers
        class _Dummy:
            def pack(self, *a, **k): return None
            def config(self, **kw):
                t = kw.get("text")
                if isinstance(t, str):
                    status_label.config(text=t)
            def __getattr__(self, name):
                return lambda *a, **k: None
        return _Dummy()

    tk.Label = _label_override

    # override tk.Toplevel so later code that creates a new popup will get the same one
    def _toplevel_override(*a, **k):
        return popup
    tk.Toplevel = _toplevel_override

    # restore original factories when the popup is destroyed
    def _restore(event=None):
        try:
            tk.Toplevel = orig_Toplevel
            tk.Label = orig_Label
        except Exception:
            pass

    popup.bind("<Destroy>", _restore)

    # Ensure popup appears
    popup.update()
    
    def update_status(text):
        status_var.set(text)
        popup.update()
        
    def update_progress(percent, text=""):
        progress_bar['value'] = percent
        progress_var.set(text)
        popup.update()
    
    def download_with_progress(url, dest_path):
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        downloaded = 0
        
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(block_size):
                if cancel_state["cancelled"]:
                    raise Exception("Update cancelled by user")
                downloaded += len(data)
                f.write(data)
                if total_size:
                    percent = int(100 * downloaded / total_size)
                    update_progress(percent, f"Downloaded: {downloaded // 1024}KB / {total_size // 1024}KB")
    
    try:
        # Get release info
        update_status("Fetching release information...")
        releases_url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases"
        if version:
            releases_url += f"/tags/{version}"
        else:
            releases_url += "/latest"
            
        response = requests.get(releases_url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch release info: {response.status_code}")
            
        release_info = response.json()
        if not version:  # Store latest version
            state.setdefault('versions', {})[emulator] = release_info['tag_name']
            save_state(state)
        
        # Find Windows zip asset
        assets = release_info.get("assets", [])
        download_url = None
        for asset in assets:
            if REPO == "xenia-canary-releases": # canary releases
                if asset["name"].endswith(".zip") and asset["name"].startswith("xenia_canary_windows"):
                    download_url = asset["browser_download_url"]
                    break
            elif REPO == "release-builds-windows": # stable releases (nice naming convention LOL)
                if asset["name"].endswith(".zip") and "xenia_master" in asset["name"].lower():
                    download_url = asset["browser_download_url"]
                    break
            elif REPO == "xenia-canary": # older canary releases
                if asset["name"].endswith(".zip") and "xenia_canary" in asset["name"].lower():
                    download_url = asset["browser_download_url"]
                    break
                
        if not download_url:
            raise Exception("No Windows release found")
            
        # Create temp directory
        update_status("Downloading update...")
        os.makedirs("temp", exist_ok=True)
        zip_path = os.path.join("temp", f"{emulator}_{version or 'latest'}.zip")
        
        # Download with progress tracking
        download_with_progress(download_url, zip_path)
        
        if cancel_state["cancelled"]:
            raise Exception("Update cancelled by user")
            
        # Extract and install
        update_status("Installing update...")
        update_progress(0, "Extracting files...")
        
        # Extract the zip
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("temp/xenia_update")
            
        # Copy files to main directory
        update_progress(50, "Copying files...")
        dest_dir = os.path.abspath(os.path.dirname(__file__))
        src_dir = os.path.join("temp", "xenia_update")
        
        for root, dirs, files in os.walk(src_dir):
            if cancel_state["cancelled"]:
                raise Exception("Update cancelled by user")
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, src_dir)
                dest_path = os.path.join(dest_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)
        
        # Record installed executable version(s)
        try:
            detected = []
            for fn in os.listdir(dest_dir):
                if fn.lower().endswith('.exe') and 'xenia' in fn.lower():
                    ap = os.path.abspath(os.path.join(dest_dir, fn))
                    # choose release tag if available
                    tag = release_info.get('tag_name') if isinstance(release_info, dict) else (version or 'Unknown')
                    state.setdefault('installed_emulators', {})[ap] = tag
                    # also ensure emulators mapping has a friendly name
                    ems = state.setdefault('emulators', {})
                    if ap not in ems:
                        ems[ap] = 'Xenia Canary' if 'canary' in fn.lower() or 'canary' in emulator else 'Xenia'
                    detected.append((ap, tag))
            # persist state if we detected anything
            if detected:
                save_state(state)
        except Exception:
            pass

        # Clean up
        update_status("Cleaning up...")
        update_progress(90, "Removing temporary files...")
        shutil.rmtree("temp/xenia_update", ignore_errors=True)
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception:
            pass

        update_status("Update complete!")
        update_progress(100, "Finished!")
        messagebox.showinfo("Success", f"{emulator} has been updated successfully!")
        popup.destroy()
        
    except Exception as e:
        error_msg = str(e)
        update_status(f"Error: {error_msg}")
        update_progress(0, "")
        messagebox.showerror("Error", f"Failed to update {emulator}: {error_msg}")
        if not popup.winfo_exists():
            return
        # Add close button since cancel button might be gone
        ttk.Button(popup, text="Close", command=popup.destroy).pack(pady=6)
    finally:
        # Clean up temp files if they exist
        try:
            shutil.rmtree("temp/xenia_update", ignore_errors=True)
            if 'zip_path' in locals():
                os.remove(zip_path)
        except Exception:
            pass
        
    try:
        response = requests.get(releases_url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch release info: {response.status_code}")
            
        release_info = response.json()
        if not version:  # Store latest version
            state.setdefault('versions', {})[emulator] = release_info['tag_name']
            save_state(state)
            
        status_label.config(text="Downloading update...")
        
        # Download and process the zip file
        assets = release_info.get("assets", [])
        download_url = None
        for asset in assets:
            if asset["name"].endswith(".zip") and "windows" in asset["name"].lower():
                download_url = asset["browser_download_url"]
                break
                
        if not download_url:
            raise Exception("No Windows release found")
            
        # Create temp directory if it doesn't exist
        os.makedirs("temp", exist_ok=True)
        zip_path = os.path.join("temp", f"{emulator}_{version or 'latest'}.zip")
        
        # Download with progress
        response = requests.get(download_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        block_size = 1024
        
        with open(zip_path, 'wb') as f:
            downloaded = 0
            for data in response.iter_content(block_size):
                downloaded += len(data)
                f.write(data)
                if total_size:
                    percent = int(100 * downloaded / total_size)
                    status_label.config(text=f"Downloading... {percent}%")
                    popup.update()
                    
        status_label.config(text="Installing update...")
        popup.update()
        
      
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("temp/xenia_update")
            
        # Copy files to main directory
        dest_dir = os.path.abspath(os.path.dirname(__file__))
        src_dir = os.path.join("temp", "xenia_update")
        
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, src_dir)
                dest_path = os.path.join(dest_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)
        
        # Clean up
        shutil.rmtree("temp/xenia_update", ignore_errors=True)
        os.remove(zip_path)
        
        status_label.config(text="Update complete!")
        messagebox.showinfo("Success", f"{emulator} has been updated successfully!")
        popup.destroy()
        
    except Exception as e:
        status_label.config(text=f"Error: {str(e)}")
        messagebox.showerror("Error", f"Failed to update {emulator}: {str(e)}")
        popup.destroy()

        os.makedirs("temp", exist_ok=True)
        releases_url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"

        response = requests.get(releases_url)

        if response.status_code != 200:
            print(f"Failed to fetch release info: {response}")
            return


        release_info = response.json()
        assets = release_info.get("assets", [])

        if not assets:
            print("No assets found for the latest release.")
            return


        for asset in assets:
            if asset["name"].endswith(".zip") and asset["name"].startswith("xenia_canary_windows"):
                asset_url = asset["browser_download_url"]
                file_name = asset["name"]
                download_path = pathlib.Path("temp") / file_name

                print(f"Downloading {file_name}...") #TODO: make this a pop-up loader
                updatelabel = tk.Label(popup, text="Downloading Xenia Canary Update, please wait...").pack(padx=20, pady=20)
                smalllabel = tk.Label(popup, text="(Downloading chunks...)").pack(padx=20, pady=10)
                asset_response = requests.get(asset_url, stream=True)

                if asset_response.status_code == 200:
                    with open(download_path, "wb") as f:
                        # get number of chunks (where each chunk is 1024) for percent
                        total_size = int(asset_response.headers.get('content-length', 0))
                        chunks_downloaded = 0
                        for chunk in asset_response.iter_content(chunk_size=1024):
                            if chunk:
                                chunks_downloaded += 1
                                updatelabel = tk.Label(text=f"Downloading Xenia Canary Update... {int((chunks_downloaded * 1024 / total_size) * 100)}%") #FIXME
                                f.write(chunk)

                    print(f"Successfully downloaded Xenia Canary update")
                else:
                    print(f"Failed to download Xenia Canary update: Internet resource responded with error code {asset_response.status_code}" )

        updatelabel = tk.Label(popup, text="Installing Xenia Canary update, please wait...").pack(padx=20, pady=20)
        smalllabel = tk.Label(popup, text="(Replacing older executable with newer update...)").pack(padx=20, pady=10)

        # Extract and replace files
        try:
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                zip_ref.extractall("temp/xenia_canary_update")

            # Copy extracted files to current directory (overwrite)
            src_dir = pathlib.Path("temp/xenia_canary_update")
            dest_dir = pathlib.Path(os.path.abspath(os.path.dirname(__file__)))

            for item in src_dir.rglob('*'):
                relative_path = item.relative_to(src_dir)
                dest_path = dest_dir / relative_path

                if item.is_dir():
                    os.makedirs(dest_path, exist_ok=True)
                else:
                    shutil.copy2(item, dest_path)

            print("Xenia Canary update installed successfully.")
            updatelabel = tk.Label(popup, text="Xenia Canary update installed successfully.").pack(padx=20, pady=20)
        except Exception as e:
            popup.close()
            # make new popup to show error
            error_popup = tk.Toplevel()
            error_popup.title("Xenia Canary Update Error")
            error_label = tk.Label(error_popup, text=f"Failed to install Xenia Canary update: {e}").pack(padx=20, pady=20)
            # add ok button to close
            ok_button = tk.Button(error_popup, text="OK", command=error_popup.destroy).pack(pady=10)

def add_game():
    name = simpledialog.askstring("New Game", "Enter folder name for new game:")
    if not name:
        return
    game_dir = os.path.join("games", name)
    if ensure_dir(game_dir):
        messagebox.showinfo("Created", f"Created game folder: {name}")
        refresh_trees()


def import_game():
    paths = filedialog.askopenfilenames(title="Select .xex files to import", filetypes=[("XEX files", "*.xex" )])
    if not paths:
        return
    name = simpledialog.askstring("Import Game", "Enter folder name to import into (will be created):")
    if not name:
        return
    game_dir = os.path.join("games", name)
    if not ensure_dir(game_dir):
        return
    for p in paths:
        try:
            dest = os.path.join(game_dir, os.path.basename(p))
            shutil.copy2(p, dest)
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to copy '{p}' to '{game_dir}': {e}")
            return
    messagebox.showinfo("Imported", f"Imported {len(paths)} file(s) into '{name}'")
    refresh_trees()


def import_dashboards_menu():
    # Ask user to pick dashboard files (xex)
    paths = filedialog.askopenfilenames(title="Select dashboard .xex files to import", filetypes=[("XEX files", "*.xex" )])
    if not paths:
        return
    # Ask whether to copy into Xbox 360 Dashboards folder
    into_local = messagebox.askyesno("Import Option", "Import into the local 'Xbox 360 Dashboards' folder? (Yes = copy files into a new/existing folder there; No = record external paths in config)")
    if into_local:
        name = simpledialog.askstring("Import Dashboard", "Enter folder name to import into (will be created):")
        if not name:
            return
        dash_dir = os.path.join("Xbox 360 Dashboards", name)
        if not ensure_dir(dash_dir):
            return
        for p in paths:
            try:
                dest = os.path.join(dash_dir, os.path.basename(p))
                shutil.copy2(p, dest)
            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to copy '{p}' to '{dash_dir}': {e}")
                return
        messagebox.showinfo("Imported", f"Imported {len(paths)} file(s) into '{name}'")
    else:
        ips = state.setdefault('imports', {}).setdefault('dashboards', [])
        for p in paths:
            ap = os.path.abspath(p)
            if ap not in ips:
                ips.append(ap)
        state['imports']['dashboards'] = ips
        save_state(state)
        messagebox.showinfo("Recorded", f"Recorded {len(paths)} external dashboard path(s) in config.")
    refresh_trees()


def import_games_menu():
    # Ask user to pick game files (iso)
    paths = filedialog.askopenfilenames(title="Select game .iso files to import", filetypes=[("ISO files", "*.iso" )])
    if not paths:
        return
    into_local = messagebox.askyesno("Import Option", "Import into the local 'games' folder? (Yes = copy files into a new/existing folder there; No = record external paths in config)")
    if into_local:
        name = simpledialog.askstring("Import Game", "Enter folder name to import into (will be created):")
        if not name:
            return
        game_dir = os.path.join("games", name)
        if not ensure_dir(game_dir):
            return
        for p in paths:
            try:
                dest = os.path.join(game_dir, os.path.basename(p))
                shutil.copy2(p, dest)
            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to copy '{p}' to '{game_dir}': {e}")
                return
        messagebox.showinfo("Imported", f"Imported {len(paths)} file(s) into '{name}'")
    else:
        ips = state.setdefault('imports', {}).setdefault('games', [])
        for p in paths:
            ap = os.path.abspath(p)
            if ap not in ips:
                ips.append(ap)
        state['imports']['games'] = ips
        save_state(state)
        messagebox.showinfo("Recorded", f"Recorded {len(paths)} external game path(s) in config.")
    refresh_trees()


def configure_emulator():
    # Let user add an emulator executable path and a display name
    path = filedialog.askopenfilename(title="Select emulator executable", filetypes=[("Executables", "*.exe" ), ("All files","*")])
    if not path:
        return
    name = simpledialog.askstring("Emulator Name", "Enter a display name for this emulator:", initialvalue=os.path.basename(path))
    if not name:
        name = os.path.basename(path)
    emus = state.setdefault('emulators', {})
    emus[path] = name
    state['emulators'] = emus
    # Record this as an installed emulator (mark version if we can infer it, otherwise 'Unknown')
    versions_map = state.setdefault('versions', {})
    inst = state.setdefault('installed_emulators', {})
    inferred = 'Unknown'
    b = os.path.basename(path).lower()
    if 'canary' in b:
        inferred = versions_map.get('xenia-canary', inferred)
    elif 'xenia' in b:
        inferred = versions_map.get('xenia-stable', inferred)
    inst[path] = inferred
    state['installed_emulators'] = inst
    save_state(state)
    messagebox.showinfo("Saved", f"Saved emulator '{name}' (version: {inferred})")


def open_manager_config():
    """Open the Manager configuration window (simple multi-tab manager).
    Allows configuring dashboard folder locations, import paths, and general settings.
    """
    top = tk.Toplevel()
    top.title("Configure Manager")
    nb = ttk.Notebook(top)
    nb.pack(fill='both', expand=True, padx=8, pady=8)

    # Dashboard Folders tab - core configuration of which folders contain dashboard files
    folders_frame = ttk.Frame(nb)
    nb.add(folders_frame, text='Dashboard Folders')

    folders_list = tk.Listbox(folders_frame, width=100, height=15)
    folders_list.pack(side='left', fill='both', expand=True, padx=(6,0), pady=6)
    scrollbar = ttk.Scrollbar(folders_frame, command=folders_list.yview)
    scrollbar.pack(side='right', fill='y', padx=(0,6), pady=6)
    folders_list.config(yscrollcommand=scrollbar.set)

    def refresh_folders():
        folders_list.delete(0, tk.END)
        # Local root dashboard folders
        folders_list.insert(tk.END, '--- Local Dashboard Folders ---')
        # Default folder is always first
        if os.path.isdir('Xbox 360 Dashboards'):
            folders_list.insert(tk.END, 'Xbox 360 Dashboards [Default]')
        # Additional configured folders from state
        for folder in state.get('settings', {}).get('dashboard_folders', []):
            if os.path.isdir(folder):
                folders_list.insert(tk.END, folder)
        # Import paths
        imports = state.get('imports', {}).get('dashboards', [])
        if imports:
            folders_list.insert(tk.END, '--- Imported Paths ---')
            for p in imports:
                if os.path.isdir(os.path.dirname(p)):  # show parent folder of .xex files
                    folders_list.insert(tk.END, os.path.dirname(p))

    refresh_folders()

    btn_frame = ttk.Frame(folders_frame)
    btn_frame.pack(fill='x', padx=8, pady=(6,0), before=folders_list)

    def add_folder():
        folder = filedialog.askdirectory(title='Select dashboard folder to add')
        if not folder:
            return
        folder = os.path.abspath(folder)
        # skip if it's the default folder
        if folder.endswith('Xbox 360 Dashboards'):
            messagebox.showinfo('Info', "'Xbox 360 Dashboards' is always included as the default folder.")
            return
        folders = state.setdefault('settings', {}).setdefault('dashboard_folders', [])
        if folder not in folders:
            folders.append(folder)
            state['settings']['dashboard_folders'] = folders
            save_state(state)
            refresh_folders()
            refresh_trees()
            messagebox.showinfo('Added', 'Dashboard folder added.')

    def remove_folder():
        sel = folders_list.curselection()
        if not sel:
            return
        val = folders_list.get(sel[0])
        if val.startswith('---') or val.endswith('[Default]'):
            messagebox.showinfo('Info', 'Select a specific folder to remove.')
            return

        # Handle absolute path removal
        if os.path.isabs(val):
            folders = state.get('settings', {}).get('dashboard_folders', [])
            if val in folders:
                folders.remove(val)
                state['settings']['dashboard_folders'] = folders
                save_state(state)
                refresh_folders()
                refresh_trees()
                messagebox.showinfo('Removed', 'Dashboard folder removed from configuration.')
                return

        # If it's an imported path parent folder, offer to remove the import
        imports = state.get('imports', {}).get('dashboards', [])
        removed = []
        for p in list(imports):  # work on copy since we modify
            if os.path.dirname(p) == val:
                imports.remove(p)
                removed.append(p)
        if removed:
            state['imports']['dashboards'] = imports
            save_state(state)
            refresh_folders()
            refresh_trees()
            messagebox.showinfo('Removed', f'Removed {len(removed)} imported dashboard(s) from this folder.')

    def open_selected():
        sel = folders_list.curselection()
        if not sel:
            return
        val = folders_list.get(sel[0])
        if val.startswith('---'):
            messagebox.showinfo('Info', 'Select a specific folder to open.')
            return
        if val.endswith('[Default]'): # FIXME
            return
        # Handle both absolute paths and default folder
        path = val if os.path.isabs(val) else os.path.abspath(val)
        if os.path.isdir(path):
            os.startfile(path)
            # Reposition the button frame to appear above the folders list
    #TODO: make buttons an icon, maybe add tooltip
    
    
    ttk.Button(btn_frame, image=plus_icon, text='Add Folder...', command=add_folder).pack(side='left', padx=6)
    ttk.Button(btn_frame, image=minus_icon, text='Remove Selected', command=remove_folder).pack(side='left', padx=6)
    ttk.Button(btn_frame, image=open_folder_icon, text='Open Folder', command=open_selected).pack(side='left', padx=6)

    # General tab for simple settings
    gen_frame = ttk.Frame(nb)
    nb.add(gen_frame, text='General')
    suppress_var = tk.BooleanVar(value=state.get('settings', {}).get('suppress_does_not_work_warning', False))
    chk = ttk.Checkbutton(gen_frame, text="Suppress 'Does Not Work' launch warning", variable=suppress_var)
    chk.pack(anchor='w', padx=8, pady=8)
    
    def save_general():
        s = state.setdefault('settings', {})
        s['suppress_does_not_work_warning'] = bool(suppress_var.get())
        state['settings'] = s
        save_state(state)
        messagebox.showinfo('Saved', 'Settings saved.')
        
    ttk.Button(gen_frame, text="Save", command=save_general).pack(side='bottom', padx=6)
    
    update_frame = ttk.Frame(nb)
    nb.add(update_frame, text='Update')

    # Create tree view for versions
    versions_tree = ttk.Treeview(update_frame)
    versions_tree.pack(fill='both', expand=True, padx=8, pady=8)
    versions_tree.heading('#0', text='Available Xenia Versions')
    
    def fetch_xenia_versions(product):
        if product == 'canary':
            owner = 'xenia-canary'
            repo = 'xenia-canary-releases'
        elif product == 'stable':
            owner = 'xenia-project'
            repo = 'release-builds-windows'
        elif product == 'oldercanary':
            owner = 'xenia-canary'
            repo = 'xenia-canary' # older releases were kept at the xenia-canary repo
        else:
            print("Unknown product for fetching versions! Falling back to stable.")
            print(product)
            owner = 'xenia-project'
            repo = 'release-builds-windows' # default to stable
            
        url = f'https://api.github.com/repos/{owner}/{repo}/releases'
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            messagebox.showerror('Error', f'Failed to fetch versions: {e}')
        return []

    def populate_versions_tree():
        versions_tree.delete(*versions_tree.get_children())
        
        # Add Xenia Canary node
        canary_node = versions_tree.insert('', 'end', text='Xenia Canary', open=True)
        canary_versions = fetch_xenia_versions('canary')
        for release in canary_versions:
            version = release.get('tag_name', '')
            date = release.get('published_at', '').split('T')[0]
            node_id = f"canary_{version}"
            versions_tree.insert(canary_node, 'end', node_id, text=f"{version} ({date})")
            
        # Add Xenia Stable node
        stable_node = versions_tree.insert('', 'end', text='Xenia Stable', open=True)
        stable_versions = fetch_xenia_versions('stable')
        for release in stable_versions:
            version = release.get('tag_name', '')
            date = release.get('published_at', '').split('T')[0]
            node_id = f"stable_{version}"
            versions_tree.insert(stable_node, 'end', node_id, text=f"{version} ({date})")
            
        # Add older Xenia Canary node
        old_canary_node = versions_tree.insert('', 'end', text='Xenia Canary (older)', open=True)
        old_canary_versions = fetch_xenia_versions('oldercanary')
        for release in old_canary_versions:
            version = release.get('tag_name', '')
            date = release.get('published_at', '').split('T')[0]
            node_id = f"oldercanary_{version}"
            versions_tree.insert(old_canary_node, 'end', node_id, text=f"{version} ({date})")

    def show_version_info(event):
        item_id = versions_tree.selection()[0]
        if not versions_tree.parent(item_id):  # Skip root nodes
            return
            
        product, version = item_id.split('_', 1) 
        releases = fetch_xenia_versions(product)
        
        for release in releases:
            if release.get('tag_name') == version:
                info_window = tk.Toplevel()
                info_window.title(f"Version Info - {version}")
                info_window.geometry("600x400")
                
                text = tk.Text(info_window, wrap=tk.WORD)
                text.pack(fill='both', expand=True, padx=8, pady=8)
                
                # Add version info
                text.insert('end', f"Version: {version}\n\n")
                text.insert('end', f"Released: {release.get('published_at', '').split('T')[0]}\n\n")
                text.insert('end', f"Changelog:\n{release.get('body', 'No changelog available.')}\n\n")
                
                text.config(state='disabled')
                
                # Add action buttons
                btn_frame = ttk.Frame(info_window)
                btn_frame.pack(fill='x', padx=8, pady=8)
                
                ttk.Button(btn_frame, text="Switch to This Version", 
                          command=lambda: update_xenia(f'xenia-{product}', version)).pack(side='left', padx=4)
                          
                ttk.Button(btn_frame, text="Close", 
                          command=info_window.destroy).pack(side='right', padx=4)
                break
    
    def version_context_menu(event):
        item_id = versions_tree.identify_row(event.y)
        if not item_id or not versions_tree.parent(item_id):  # Skip if no item or root
            return
            
        versions_tree.selection_set(item_id)
        menu = tk.Menu(root, tearoff=0)
        
        product, version = item_id.split('_', 1)
        menu.add_command(label=f"Switch to Version {version}", 
                        command=lambda: update_xenia(f'xenia-{product}', version))
        menu.add_command(label="View Changelog", 
                        command=lambda: show_version_info(None))
        
        menu.tk_popup(event.x_root, event.y_root)

    versions_tree.bind('<Double-Button-1>', show_version_info)
    versions_tree.bind('<Button-3>', version_context_menu)

    # Add refresh button and auto-update checkbox
    btn_frame = ttk.Frame(update_frame)
    btn_frame.pack(fill='x', padx=8, pady=4)

    ttk.Button(btn_frame, text="Refresh Versions", command=populate_versions_tree).pack(side='left', padx=4)
    check_updates_xm = tk.BooleanVar(value=state.get('update', {}).get('check_update_on_launch_xm', False))
    chk = ttk.Checkbutton(btn_frame, text="Check for updates on launch", variable=check_updates_xm)
    chk.pack(side='right', padx=4)

    # Initial population
    populate_versions_tree()

    emu_frame = ttk.Frame(nb)
    nb.add(emu_frame, text='Emulator')
    
    # Add fullscreen toggle with proper state management
    fullscreen = state.setdefault('emulator', {}).setdefault('fullscreen', False)
    fullscreen_var = tk.BooleanVar(value=fullscreen)
    
    def save_fullscreen():
        state['emulator']['fullscreen'] = fullscreen_var.get()
        save_state(state)
    
    chk = ttk.Checkbutton(emu_frame, text="Launch games in fullscreen", 
                         variable=fullscreen_var, command=save_fullscreen)
    chk.pack(anchor='w', padx=8, pady=8)
    # Installed Emulators list (path -> version)
    installed_label = ttk.Label(emu_frame, text="Installed Emulators:")
    installed_label.pack(anchor='w', padx=8, pady=(8,0))

    installed_frame = ttk.Frame(emu_frame)
    installed_frame.pack(fill='both', expand=False, padx=8, pady=4)

    installed_list = tk.Listbox(installed_frame, width=100, height=8)
    installed_list.pack(side='left', fill='both', expand=True)
    installed_scroll = ttk.Scrollbar(installed_frame, command=installed_list.yview)
    installed_scroll.pack(side='right', fill='y')
    installed_list.config(yscrollcommand=installed_scroll.set)

    def refresh_installed_list():
        installed_list.delete(0, tk.END)
        inst = state.get('installed_emulators', {})
        if not inst:
            installed_list.insert(tk.END, '(No installed emulators detected)')
            return
        for path, ver in sorted(inst.items()):
            name = os.path.basename(path)
            display = f"{name} — {ver} — {path}"
            installed_list.insert(tk.END, display)

    def detect_and_refresh():
        detect_installed_emulators()
        refresh_installed_list()

    def open_selected_emulator_folder():
        sel = installed_list.curselection()
        if not sel:
            return
        line = installed_list.get(sel[0])
        # last token is path
        path = line.split(' — ')[-1]
        if os.path.exists(os.path.dirname(path)):
            os.startfile(os.path.dirname(path))

    def remove_selected_emulator():
        sel = installed_list.curselection()
        if not sel:
            return
        line = installed_list.get(sel[0])
        path = line.split(' — ')[-1]
        # remove from state['installed_emulators'] and from state['emulators'] if present
        inst = state.get('installed_emulators', {})
        if path in inst:
            inst.pop(path, None)
        ems = state.get('emulators', {})
        if path in ems:
            ems.pop(path, None)
        state['installed_emulators'] = inst
        state['emulators'] = ems
        save_state(state)
        refresh_installed_list()

    btns = ttk.Frame(emu_frame)
    btns.pack(fill='x', padx=8, pady=(2,8))
    ttk.Button(btns, text='Detect Installed Emulators', command=detect_and_refresh).pack(side='left', padx=6)
    ttk.Button(btns, text='Open Folder', command=open_selected_emulator_folder).pack(side='left', padx=6)
    ttk.Button(btns, text='Remove Selected', command=remove_selected_emulator).pack(side='left', padx=6)

    # populate the list initially
    refresh_installed_list()
    

if HAVE_TKDN:
    # use TkinterDnD root if available for native file-drop support
    root = TkinterDnD.Tk()
else:
    root = tk.Tk()
root.title("Xenia Manager")

plus_icon = PhotoImage(file="./assets/icons/plus.png")
minus_icon = PhotoImage(file="./assets/icons/minus.png")
open_folder_icon = PhotoImage(file="./assets/icons/open-folder.png")

def load_state():
    path = get_labels_path()
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # backward compat: flat labels dict -> convert
                if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
                    return {'labels': data, 'emulators': {}}
                return data if isinstance(data, dict) else {'labels': {}, 'emulators': {}}
    except Exception:
        return {'labels': {}, 'emulators': {}}


def save_state(state):
    path = get_labels_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        messagebox.showerror('Save Error', f'Failed to save config: {e}')


state = load_state()
labels = state.get("labels", {})  # mapping: folder_name -> label string
emulators = state.get("emulators", {})  # mapping: emulator_path -> display name

# Detect local Xenia Canary executables next to this script and add to emulators if found
script_dir = os.path.abspath(os.path.dirname(__file__))
for candidate in ("xenia_canary.exe", "xenia_canary_netplay.exe"):
    candidate_path = os.path.join(script_dir, candidate)
    if os.path.exists(candidate_path):
        # store absolute path -> display name
        if candidate_path not in emulators:
            emulators[candidate_path] = "Xenia Canary"
            state["emulators"] = emulators
            save_state(state)
        break

# Track installed emulator versions (path -> version string)
installed_emulators = state.setdefault('installed_emulators', {})

def detect_installed_emulators(scan_dirs=None):
    """Scan for installed emulator executables and populate state['installed_emulators'].
    If installed via this manager we attempt to record the version (from state['versions']),
    otherwise store 'Unknown'."""
    scan_dirs = scan_dirs or [script_dir]
    found = {}
    for d in scan_dirs:
        try:
            for fn in os.listdir(d):
                if fn.lower().endswith('.exe') and 'xenia' in fn.lower():
                    path = os.path.abspath(os.path.join(d, fn))
                    # If we already know a version for this exact path, keep it
                    version = state.get('installed_emulators', {}).get(path)
                    if not version:
                        # try infer from known versions stored under keys like 'xenia-canary'
                        if 'canary' in fn.lower():
                            version = state.get('versions', {}).get('xenia-canary', 'Unknown')
                        else:
                            version = state.get('versions', {}).get('xenia-stable', 'Unknown')
                    found[path] = version
        except Exception:
            continue
    # Also include any emulators explicitly configured by user
    for path in list(state.get('emulators', {}).keys()):
        try:
            ap = os.path.abspath(path)
            if os.path.exists(ap) and ap not in found:
                found[ap] = state.get('installed_emulators', {}).get(ap, 'Unknown')
        except Exception:
            pass

    # Merge into state and persist
    # preserve any prior entries and update with detected ones
    prior = state.get('installed_emulators', {})
    merged = {**prior, **found}
    state['installed_emulators'] = merged
    save_state(state)
    return state['installed_emulators']

# Run detection at startup
detect_installed_emulators()

# --- Menu bar (File, Settings, Help)
menubar = tk.Menu(root)
file_menu = tk.Menu(menubar, tearoff=0)
# open xenia emulator directly using subprocess by getting default emulator, do not use open_xex, no dashboard or game
file_menu.add_command(label="Launch Xenia Emulator", command=lambda: subprocess.Popen([pick_preferred_emulator()]))
file_menu.add_separator()
file_menu.add_command(label="Import Dashboards...", command=import_dashboards_menu)
file_menu.add_command(label="Import Games...", command=import_games_menu)
file_menu.add_separator()
file_menu.add_command(label="Exit", command=root.quit)
menubar.add_cascade(label="File", menu=file_menu)

settings_menu = tk.Menu(menubar, tearoff=0)
settings_menu.add_command(label="Configure Manager...", command=open_manager_config)
settings_menu.add_command(label="Configure Emulator...", command=configure_emulator)
menubar.add_cascade(label="Settings", menu=settings_menu)

help_menu = tk.Menu(menubar, tearoff=0)
help_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", "Xenia Manager — Dashboard & Games Manager"))
menubar.add_cascade(label="Help", menu=help_menu)

root.config(menu=menubar)


def pick_preferred_emulator():
    # prefer any emulator whose filename contains both 'xenia' and 'canary'
    for path, name in emulators.items():
        b = os.path.basename(path).lower()
        if 'xenia' in b and 'canary' in b:
            return path
    # otherwise return first registered emulator
    if emulators:
        return next(iter(emulators.keys()))
    return None


def open_xex(xex_path, emulator_exec=None):
    if not xex_path:
        messagebox.showerror("Not Found", "Could not find a .xex file to launch for the selected dashboard.")
        return
    # If emulator_exec is None -> default system open
    if emulator_exec is None:
        try:
            os.startfile(os.path.abspath(xex_path)) 
        except Exception as e:
            messagebox.showerror("Launch Error", f"Failed to open '{xex_path}': {e}")
        return

    # launch using subprocess
    script_dir_local = os.path.abspath(os.path.dirname(__file__))
    # make sure that if it is stable xenia, we launch flags then the xex path
    if not 'xenia-canary' in os.path.basename(emulator_exec).lower():
        cmd = [emulator_exec]
    else:
        cmd = [emulator_exec, os.path.abspath(xex_path)]
    
    # Add fullscreen flag if enabled in settings
    if state.get('emulator', {}).get('fullscreen', False):
        cmd.append("--fullscreen")
    
    print(os.path.basename(emulator_exec).lower()) #debug purposes only
    
    # Add other standard flags
    if 'xenia-canary' in os.path.basename(emulator_exec).lower():
        cmd.extend(["--use_new_decoder=true", "--use_dedicated_xma_thread=false"]) # test to see if stable has these flags
    
    if not 'xenia-canary' in os.path.basename(emulator_exec).lower():
        cmd = cmd + [os.path.abspath(xex_path)] # different order for stable
        
    print(f"Launching emulator with command: {' '.join(cmd)}")    
    
    try:
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NEW_CONSOLE
        subprocess.Popen(cmd, cwd=script_dir_local, creationflags=creationflags) # FLAG
    except FileNotFoundError:
        messagebox.showerror("Launch Error", f"Emulator not found: {emulator_exec}")
    except Exception as e:
        messagebox.showerror("Launch Error", f"Failed to launch '{xex_path}' with '{emulator_exec}': {e}")


# Load a category index mapping category name -> list of filenames
def load_index():
    # look for dashboard_index.json in the same parent as the dashboards folder
    labels_path = get_labels_path()
    parent = os.path.dirname(labels_path)
    index_path = os.path.join(parent, "dashboard_index.json")
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # fallback default mapping
        return {
            "Dashboards": ["$flash_dash.xex", "dash.xex"],
            "Boot Animations": ["bootanim.xex", "$flash_bootanim.xex"]
        }


# (Toolbar removed — use drag-and-drop or right-click Import functions)

# Create notebook for tabs
notebook = ttk.Notebook(root)
notebook.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

# Create frames for each tab
dashboards_frame = ttk.Frame(notebook)
games_frame = ttk.Frame(notebook)

# Add the frames to notebook
notebook.add(dashboards_frame, text='Dashboards')
notebook.add(games_frame, text='Games')

# Create trees for both tabs
dash_tree = ttk.Treeview(dashboards_frame)
dash_tree.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

games_tree = ttk.Treeview(games_frame)
games_tree.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

# If tkinterdnd2 is available, register the games_tree as a drop target
if HAVE_TKDN:
    def _parse_dnd_files(data):
        # data may be a string like '{C:/path/one.iso} {C:/path/two.iso}' or space-separated
        import re
        parts = re.findall(r'\{([^}]*)\}|([^ ]+)', data)
        files = []
        for a, b in parts:
            if a:
                files.append(a)
            elif b:
                files.append(b)
        return files

    def on_games_drop(event):
        data = event.data
        files = _parse_dnd_files(data)
        if not files:
            return
        # Determine drop target folder (if dropped onto a folder node)
        try:
            y = event.y_root - games_tree.winfo_rooty()
            iid = games_tree.identify_row(y)
        except Exception:
            iid = None

        target_folder = None
        if iid and iid.startswith('game::'):
            target_folder = iid.split('::', 1)[1]

        if not target_folder:
            # ask for folder name
            target_folder = simpledialog.askstring("Import Games", "Enter target game folder name (will be created):")
            if not target_folder:
                return

        game_dir = os.path.join('games', target_folder)
        if not ensure_dir(game_dir):
            return

        imported = 0
        for p in files:
            try:
                if not os.path.isfile(p):
                    continue
                # only accept .iso files for games
                if not p.lower().endswith('.iso'):
                    continue
                dest = os.path.join(game_dir, os.path.basename(p))
                shutil.copy2(p, dest)
                imported += 1
            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to copy '{p}' to '{game_dir}': {e}")
        if imported:
            messagebox.showinfo("Imported", f"Imported {imported} file(s) into '{target_folder}'")
            refresh_trees()

    games_tree.drop_target_register(DND_FILES)
    games_tree.dnd_bind('<<Drop>>', on_games_drop)

index_map = load_index()
file_nodes = {}  # iid -> abs path
folder_nodes = []  # list of folder iids


def display_text_for(folder):
    # show folder with optional label appended
    label = labels.get(folder)
    if label:
        return f"{folder} [{label}]"
    return folder
def get_tree_for_event(event):
    # Returns the appropriate tree based on the widget that received the event
    widget = event.widget
    if widget == dash_tree:
        return dash_tree
    if widget == games_tree:
        return games_tree
    # fallback: if event.widget is a child, try to find nearest Treeview ancestor
    parent = widget
    while parent is not None:
        try:
            if isinstance(parent, ttk.Treeview):
                return parent
        except Exception:
            pass
        parent = getattr(parent, 'master', None)
    return None


def update_folder_display(folder):
    # update folder nodes in both trees (if present)
    dash_id = f"dash::{folder}"
    game_id = f"game::{folder}"
    if dash_tree.exists(dash_id):
        dash_tree.item(dash_id, text=display_text_for(folder))
    if games_tree.exists(game_id):
        games_tree.item(game_id, text=display_text_for(folder))



def populate_dashboards_tree():
    # builds the dashboards tree from the default folder and any configured folders
    dash_tree.delete(*dash_tree.get_children())
    file_nodes.clear()
    folder_nodes.clear()

    def add_folder_to_tree(folder_path, parent_node=''):
        if not os.path.isdir(folder_path):
            return
        folder = os.path.basename(folder_path)
        folder_id = f"dash::{folder}" if not parent_node else f"{parent_node}::{folder}"
        folder_nodes.append(folder_id)
        node_text = display_text_for(folder) if not parent_node else folder
        dash_tree.insert(parent_node, 'end', folder_id, text=node_text)

        for category, file_patterns in index_map.items():
            category_id = f"{folder_id}::{category}"
            has_files = False
            for pattern in file_patterns:
                file_path = os.path.join(folder_path, pattern)
                if os.path.exists(file_path):
                    if not has_files:
                        dash_tree.insert(folder_id, 'end', category_id, text=category)
                        has_files = True
                    file_id = f"{folder_id}:::{pattern}"
                    file_nodes[file_id] = file_path
                    dash_tree.insert(category_id, 'end', file_id, text=os.path.basename(pattern))

        # one-level subfolders
        for item in sorted(os.listdir(folder_path)):
            sub = os.path.join(folder_path, item)
            if os.path.isdir(sub):
                add_folder_to_tree(sub, folder_id)

    default_path = 'Xbox 360 Dashboards'
    if os.path.exists(default_path):
        add_folder_to_tree(default_path)

    for folder in state.get('settings', {}).get('dashboard_folders', []):
        if os.path.isdir(folder):
            add_folder_to_tree(folder)

    # imported dashboard files grouped by parent folder
    imports = state.get('imports', {}).get('dashboards', []) if isinstance(state.get('imports', {}), dict) else []
    if imports:
        imported_id = 'dash::Imported'
        dash_tree.insert('', 'end', imported_id, text='Imported Dashboards')
        grouped = {}
        for p in imports:
            if not os.path.exists(p):
                continue
            parent = os.path.dirname(p)
            grouped.setdefault(parent, []).append(p)
        for parent, files in sorted(grouped.items()):
            folder = os.path.basename(parent)
            folder_id = f"{imported_id}::{folder}"
            dash_tree.insert(imported_id, 'end', folder_id, text=folder)
            for p in sorted(files):
                fid = 'dash::import::' + str(abs(hash(p)))
                file_nodes[fid] = p
                dash_tree.insert(folder_id, 'end', fid, text=os.path.basename(p))


def populate_games_tree():
    games_tree.delete(*games_tree.get_children())
    games_path = 'games'
    if not os.path.exists(games_path):
        return
    detected_games = []
    excluded_folders = {'cache', 'cache0', 'cache1'}
    for folder in sorted(os.listdir(games_path)):
        if folder in excluded_folders:
            continue
        folder_path = os.path.join(games_path, folder)
        if not os.path.isdir(folder_path):
            continue
        folder_id = f"game::{folder}"
        folder_nodes.append(folder_id)
        games_tree.insert('', 'end', folder_id, text=display_text_for(folder))
        detected_games.append(folder)
        for file in sorted(os.listdir(folder_path)):
            if file.lower().endswith('.iso'):
                file_path = os.path.join(folder_path, file)
                file_id = f"{folder_id}:::{file}"
                file_nodes[file_id] = file_path
                games_tree.insert(folder_id, 'end', file_id, text=file)
    try:
        state['games'] = detected_games
        save_state(state)
    except Exception:
        pass


def refresh_trees():
    populate_dashboards_tree()
    populate_games_tree()


def ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        messagebox.showerror('Error', f"Failed to create directory '{path}': {e}")
        return False


def on_right_click(event):
    tree = get_tree_for_event(event)
    if tree is None:
        return
    iid = tree.identify_row(event.y)
    if not iid:
        return
    tree.selection_set(iid)

    menu = tk.Menu(root, tearoff=0)

    # If it's a file node, show Open / Open in...
    if iid in file_nodes:
        xex_path = file_nodes[iid]
        preferred = pick_preferred_emulator()
        menu.add_command(label="Open", command=lambda p=xex_path: open_xex(p, preferred))
        open_menu = tk.Menu(menu, tearoff=0)
        open_menu.add_command(label="Default System", command=lambda p=xex_path: open_xex(p, None))
        for emu_exec, emu_name in emulators.items():
            open_menu.add_command(label=emu_name, command=lambda e=emu_exec, p=xex_path: open_xex(p, e))
        menu.add_cascade(label="Open in...", menu=open_menu)
    else:
        # treat as folder or category node; find folder name without prefix
        if ':::' in iid:
            # shouldn't happen (file nodes handled above)
            return
        # folder nodes use prefixes like 'dash::FolderName' or 'game::FolderName',
        # categories are 'dash::FolderName::Category'
        if '::' in iid:
            parts = iid.split('::')
            # parts[0] is prefix (dash or game), parts[1] is folder
            if len(parts) >= 2:
                folder = parts[1]
            else:
                folder = iid
        else:
            folder = iid

        label_menu = tk.Menu(menu, tearoff=0)

        def set_label(value):
            if value is None:
                labels.pop(folder, None)
            else:
                labels[folder] = value
            state["labels"] = labels
            save_state(state)
            update_folder_display(folder)

        label_menu.add_command(label="Works", command=lambda: set_label("Works"))
        label_menu.add_command(label="Partially Working", command=lambda: set_label("Partially Working"))
        label_menu.add_command(label="Does Not Work", command=lambda: set_label("Does Not Work"))
        label_menu.add_separator()
        label_menu.add_command(label="Clear Label", command=lambda: set_label(None))

        menu.add_cascade(label="Label As...", menu=label_menu)

    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def on_double_click(event):
    tree = get_tree_for_event(event)
    if tree is None:
        return
    iid = tree.identify_row(event.y)
    if not iid:
        return
    # If file node, open it
    if iid in file_nodes:
        xex_path = file_nodes[iid]
        # folder part is like 'dash::FolderName' or 'game::FolderName'
        folder_pref = iid.split(':::', 1)[0]
        folder = folder_pref.split('::', 1)[1] if '::' in folder_pref else folder_pref
        label = labels.get(folder)
        suppress = state.get('settings', {}).get('suppress_does_not_work_warning', False)
        if label == "Does Not Work" and not suppress:
            proceed = messagebox.askyesno(
                "Warning",
                f"The dashboard '{folder}' is labeled as 'Does Not Work' and may not launch correctly. Continue anyway?"
            )
            if not proceed:
                return
        preferred = pick_preferred_emulator()
        open_xex(xex_path, preferred)
    else:
        # toggle expand/collapse for folder/category nodes
        children = tree.get_children(iid)
        if children:
            is_open = tree.item(iid, 'open')
            tree.item(iid, open=not is_open)





# Initialize tree views
dash_tree.heading("#0", text="Dashboards")
games_tree.heading("#0", text="Games")

# Bind events for both trees
for tree in (dash_tree, games_tree):
    tree.bind('<Button-3>', on_right_click)
    tree.bind('<Double-Button-1>', on_double_click)

# Bind F5 to refresh
root.bind('<F5>', lambda e: refresh_trees())

# Initial population
populate_dashboards_tree()
populate_games_tree()

root.mainloop()