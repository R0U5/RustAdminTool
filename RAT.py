import os
import json
import asyncio
import datetime
import threading
import tkinter as tk
from tkinter import messagebox, ttk, Menu
import websockets
import re
import time
import urllib.parse
import base64
import hashlib
import secrets

# Pre-compile regex patterns for performance
PLAYER_REGEX = re.compile(
    r'^(?P<num>\d+)\s+(?P<steamId>\d{17})\s+"(?P<playername>.*)"\s+(?P<ping>-?\d+)\s+(?P<connected>[\d.]+)s\s+(?P<ip>[\d.]+:\d+)\s*(?P<owner>\d{17})?\s*(?P<violation>[\d.]*)?\s*(?P<kicks>[\d.]*)?'
)
TAG_REGEX = re.compile(r"\[[^\]]+\]")

# --- Config Manager ---
class ConfigManager:
    def __init__(self, path):
        self.path = path
        self._salt = self._get_or_create_salt()

    def _get_or_create_salt(self):
        salt_path = self.path + ".salt"
        if os.path.exists(salt_path):
            with open(salt_path, 'rb') as f:
                return f.read()
        salt = os.urandom(16)
        with open(salt_path, 'wb') as f:
            f.write(salt)
        return salt

    def _simple_encrypt(self, password):
        key = hashlib.sha256(self._salt).digest()
        password_bytes = password.encode('utf-8')
        encrypted = bytes([a ^ b for a, b in zip(password_bytes, key)])
        return base64.b64encode(encrypted).decode('utf-8')

    def _simple_decrypt(self, encrypted_password):
        try:
            key = hashlib.sha256(self._salt).digest()
            encrypted_bytes = base64.b64decode(encrypted_password.encode('utf-8'))
            decrypted = bytes([a ^ b for a, b in zip(encrypted_bytes, key)])
            return decrypted.decode('utf-8')
        except Exception:
            return encrypted_password

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if "password" in config:
                        config["password"] = self._simple_decrypt(config["password"])
                    return config
            except Exception as e:
                print(f"Failed to load config: {e}")
        return {}

    def save(self, config):
        try:
            config_to_save = config.copy()
            if "password" in config_to_save:
                config_to_save["password"] = self._simple_encrypt(config_to_save["password"])
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

# --- Logger with tag coloring ---
class Logger:
    def __init__(self, widget, log_file, tag_colors, tag_whitelist):
        self.widget = widget
        self.log_file = log_file
        self.tag_colors = tag_colors
        self.tag_color_map = {}
        self.tag_whitelist = tag_whitelist
        self._setup_tags()

    def _setup_tags(self):
        """Pre-configure common tags for better performance"""
        for tag in self.tag_whitelist:
            color = self.tag_colors[len(self.tag_color_map) % len(self.tag_colors)]
            self.tag_color_map[tag] = color
            try:
                self.widget.tag_config(tag, foreground=color)
            except tk.TclError:
                pass

    def log(self, message):
        self.widget.after_idle(self._log_message, message)

    def _log_message(self, message):
        self.widget.configure(state="normal")
        tags = TAG_REGEX.findall(message)
        start_index = self.widget.index(tk.END)
        self.widget.insert(tk.END, message + "\n")
        
        # Apply tags efficiently
        for tag in set(tags):  # Use set to avoid duplicate work
            if tag not in self.tag_whitelist:
                continue
            if tag not in self.tag_color_map:
                self.tag_color_map[tag] = self.tag_colors[len(self.tag_color_map) % len(self.tag_colors)]
            for match in re.finditer(re.escape(tag), message):
                self.widget.tag_add(tag, f"{start_index}+{match.start()}c", f"{start_index}+{match.end()}c")
        
        self.widget.see(tk.END)
        self.widget.configure(state="disabled")
        
        # Async file write to avoid blocking UI
        threading.Thread(target=self._write_log, args=(message,), daemon=True).start()

    def _write_log(self, message):
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}")

# --- Item Database ---
class ItemDatabase:
    def __init__(self, path):
        self.path = path
        self.items = []
        self.categories = set()
        self._search_cache = {}
        self.load()

    def load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                self.items = json.load(f)
                self.categories = set(item.get("Category", "Other") for item in self.items)
        except Exception as e:
            print(f"Failed to load items: {e}")

    def search(self, query):
        query = query.lower()
        if query in self._search_cache:
            return self._search_cache[query]
        results = [item for item in self.items if query in item.get("Name", "").lower() or query in item.get("Shortname", "").lower()]
        self._search_cache[query] = results
        # Limit cache size
        if len(self._search_cache) > 100:
            self._search_cache.clear()
        return results

    def get_categories(self):
        return sorted(self.categories)

# --- Player Manager ---
class PlayerManager:
    def __init__(self, treeview, app):
        self.tree = treeview
        self.app = app
        self._cached_players = {}

    def update(self, message):
        lines = message.splitlines()
        self.tree.delete(*self.tree.get_children())
        self._cached_players.clear()
        
        for line in lines:
            match = PLAYER_REGEX.match(line.strip())
            if match:
                try:
                    name = match.group("playername")
                    ping = match.group("ping")
                    steamid = match.group("steamId")
                    connected = match.group("connected")
                    item_id = self.tree.insert("", "end", values=(name, ping, steamid, connected))
                    self._cached_players[steamid] = item_id
                except Exception:
                    continue

    def filter(self, query):
        q = query.lower()
        for item in self.tree.get_children():
            values = self.tree.item(item)["values"]
            if any(q in str(v).lower() for v in values):
                try:
                    self.tree.reattach(item, '', 'end')
                except tk.TclError:
                    pass
            else:
                try:
                    self.tree.detach(item)
                except tk.TclError:
                    pass

    def sort(self, col, reverse):
        data = []
        for k in self.tree.get_children(''):
            value = self.tree.set(k, col)
            try:
                if col in ("SteamID",):
                    value = (value, k)
                elif col == "Ping":
                    value = (int(value) if value.lstrip('-').isdigit() else 9999, k)
                elif '.' in value and value.replace('.', '').isdigit():
                    value = (float(value), k)
                else:
                    try:
                        value = (int(value), k)
                    except ValueError:
                        value = (value.lower(), k)
            except (ValueError, TypeError):
                value = (value, k)
            data.append(value)
        data.sort(reverse=reverse)
        for index, (_, k) in enumerate(data):
            self.tree.move(k, '', index)

    def get_selected(self):
        selection = self.tree.selection()
        if selection:
            return self.tree.item(selection[0])["values"]
        return None

# --- Main GUI + WebSocket ---
class WebRCONApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rust Admin Tool (R.A.T.)")
        self.geometry("1100x750")
        self.minsize(400, 400)

        # Setup style for better look
        self.style = ttk.Style()
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        
        self.CONFIG_PATH = os.path.join(os.path.expanduser("~"), "Documents", "RAT_config.JSON")
        self.LOG_PATH = os.path.join(os.path.expanduser("~"), "Documents", "RAT_log.txt")
        self.ITEMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.json")

        self.DEFAULT_IP = "SET_YOUR_SERVER_IP_HERE"
        self.DEFAULT_PORT = 28015
        self.DEFAULT_PASSWORD = "ADMIN_PASSWORD_HERE"
        self.TAG_COLORS = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9"]
        self.TAG_WHITELIST = {"[OK]", "[ERROR]", "[WARN]", "[INFO]", "[Chat]", "[Server]", "[Command]", "[Players]", "[Hostname]", "[Version]", "[Map]", "[Ban]"}

        self.config_mgr = ConfigManager(self.CONFIG_PATH)
        self.item_db = ItemDatabase(self.ITEMS_PATH)
        self.loop = asyncio.new_event_loop()
        self.websocket = None
        self.connected = False
        self._connecting = False
        self._receiver_running = False
        self.identifier_counter = 1
        self.last_status_time = 0
        self.status_interval = 15

        self._lock = threading.Lock()
        self._receiver_task = None
        self._status_polling = False
        self._identifier_lock = threading.Lock()

        threading.Thread(target=self._run_loop, daemon=True).start()
        self._init_ui()

    def _init_ui(self):
        config = self.config_mgr.load()
        ip = config.get("ip", self.DEFAULT_IP)
        port = config.get("port", self.DEFAULT_PORT)
        password = config.get("password", self.DEFAULT_PASSWORD)

        # Configure colors
        bg_color = "#2B2B2B"
        fg_color = "#E0E0E0"
        entry_bg = "#3C3C3C"
        
        self.configure(bg=bg_color)

        # Menu bar
        menubar = tk.Menu(self, bg=bg_color, fg=fg_color, activebackground="#404040", activeforeground=fg_color)
        server_menu = tk.Menu(menubar, tearoff=0, bg=bg_color, fg=fg_color, activebackground="#404040", activeforeground=fg_color)
        server_menu.add_command(label="Connect", command=self._connect)
        server_menu.add_command(label="Disconnect", command=self._disconnect)
        server_menu.add_separator()
        server_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="Server", menu=server_menu)

        tools_menu = tk.Menu(menubar, tearoff=0, bg=bg_color, fg=fg_color, activebackground="#404040", activeforeground=fg_color)
        tools_menu.add_command(label="Ban List", command=self._show_banlist)
        tools_menu.add_command(label="Player List", command=lambda: asyncio.run_coroutine_threadsafe(self._send_json_command("players"), self.loop))
        menubar.add_cascade(label="Tools", menu=tools_menu)

        self.config(menu=menubar)

        # Connection frame with better styling
        top = tk.Frame(self, bg=bg_color, relief=tk.RAISED, bd=1)
        top.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(top, text="IP:", bg=bg_color, fg=fg_color).pack(side=tk.LEFT, padx=(5, 2))
        self.ip_entry = tk.Entry(top, width=15, bg=entry_bg, fg=fg_color, insertbackground=fg_color, relief=tk.SOLID, bd=1)
        self.ip_entry.insert(0, ip)
        self.ip_entry.pack(side=tk.LEFT, padx=2)
        
        tk.Label(top, text="Port:", bg=bg_color, fg=fg_color).pack(side=tk.LEFT, padx=(10, 2))
        self.port_entry = tk.Entry(top, width=6, bg=entry_bg, fg=fg_color, insertbackground=fg_color, relief=tk.SOLID, bd=1)
        self.port_entry.insert(0, str(port))
        self.port_entry.pack(side=tk.LEFT, padx=2)
        
        tk.Label(top, text="Password:", bg=bg_color, fg=fg_color).pack(side=tk.LEFT, padx=(10, 2))
        self.password_entry = tk.Entry(top, show="*", width=12, bg=entry_bg, fg=fg_color, insertbackground=fg_color, relief=tk.SOLID, bd=1)
        self.password_entry.insert(0, password)
        self.password_entry.pack(side=tk.LEFT, padx=2)
        
        self.connect_btn = tk.Button(top, text="Connect", command=self._connect, bg="#4CAF50", fg="white", activebackground="#45a049", relief=tk.FLAT, padx=10)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_btn = tk.Button(top, text="Disconnect", command=self._disconnect, bg="#f44336", fg="white", activebackground="#da190b", relief=tk.FLAT, padx=10)
        self.disconnect_btn.pack(side=tk.LEFT)

        # Status label
        self.status_label = tk.Label(top, text="● Disconnected", fg="#f44336", bg=bg_color, font=("Arial", 9, "bold"))
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # Main content with tabs
        mid = tk.Frame(self, bg=bg_color)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        style = ttk.Style()
        style.configure("TNotebook", background=bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", background="#3C3C3C", foreground=fg_color, padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", "#4CAF50")], foreground=[("selected", "white")])
        
        self.tabs = ttk.Notebook(mid)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        # Console tab
        console_frame = tk.Frame(self.tabs, bg=bg_color)
        self.console_tab = tk.Text(console_frame, wrap=tk.WORD, state="disabled", bg="#1E1E1E", fg="#D4D4D4", insertbackground="#D4D4D4", relief=tk.FLAT, bd=0)
        self.console_tab.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tabs.add(console_frame, text="Console")

        # Players tab
        player_tab = tk.Frame(self.tabs, bg=bg_color)
        player_tab.pack(fill=tk.BOTH, expand=True)

        # Player search
        search_frame = tk.Frame(player_tab, bg=bg_color)
        search_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(search_frame, text="Search:", bg=bg_color, fg=fg_color).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.players.filter(self.search_var.get()))
        search_entry = tk.Entry(search_frame, textvariable=self.search_var, bg=entry_bg, fg=fg_color, insertbackground=fg_color, relief=tk.SOLID, bd=1)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Player action buttons with colors
        action_frame = tk.Frame(player_tab, bg=bg_color)
        action_frame.pack(fill=tk.X, padx=5, pady=2)
        
        btn_config = {"relief": tk.FLAT, "padx": 8, "pady": 3, "font": ("Arial", 9)}
        tk.Button(action_frame, text="Kick", command=self._kick_selected, bg="#FF9800", fg="white", activebackground="#e68900", **btn_config).pack(side=tk.LEFT, padx=2)
        tk.Button(action_frame, text="Ban", command=self._ban_selected, bg="#f44336", fg="white", activebackground="#da190b", **btn_config).pack(side=tk.LEFT, padx=2)
        tk.Button(action_frame, text="Mute", command=self._mute_selected, bg="#9C27B0", fg="white", activebackground="#7b1fa2", **btn_config).pack(side=tk.LEFT, padx=2)
        tk.Button(action_frame, text="Teleport", command=self._teleport_to_selected, bg="#2196F3", fg="white", activebackground="#0b7dda", **btn_config).pack(side=tk.LEFT, padx=2)
        tk.Button(action_frame, text="Give Item", command=self._give_item_dialog, bg="#4CAF50", fg="white", activebackground="#45a049", **btn_config).pack(side=tk.LEFT, padx=2)
        tk.Button(action_frame, text="Kill", command=self._kill_selected, bg="#607D8B", fg="white", activebackground="#455a64", **btn_config).pack(side=tk.LEFT, padx=2)

        # Player treeview with styling
        tree_frame = tk.Frame(player_tab, bg=bg_color)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        style.configure("Treeview", background="#2B2B2B", foreground=fg_color, fieldbackground="#2B2B2B", rowheight=25)
        style.configure("Treeview.Heading", background="#3C3C3C", foreground=fg_color, font=("Arial", 10, "bold"))
        style.map("Treeview", background=[("selected", "#4CAF50")])
        
        self.tree = ttk.Treeview(tree_frame, columns=("Name", "Ping", "SteamID", "Connected"), show="headings", selectmode="browse")
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col, command=lambda c=col: self.players.sort(c, False))
            self.tree.column(col, anchor="center", width=100)
        self.tree.column("Name", width=200, anchor="w")
        
        # Scrollbar for treeview
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tabs.add(player_tab, text="Players")

        # Ban list tab
        ban_frame = tk.Frame(self.tabs, bg=bg_color)
        self.ban_tab = tk.Text(ban_frame, wrap=tk.WORD, state="disabled", bg="#1E1E1E", fg="#D4D4D4", relief=tk.FLAT, bd=0)
        self.ban_tab.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tabs.add(ban_frame, text="Bans")

        self.players = PlayerManager(self.tree, self)

        # Right-click context menu for players
        self.player_menu = Menu(self, tearoff=0, bg=bg_color, fg=fg_color, activebackground="#404040", activeforeground=fg_color)
        self.player_menu.add_command(label="Kick", command=self._kick_selected)
        self.player_menu.add_command(label="Ban", command=self._ban_selected)
        self.player_menu.add_command(label="Mute", command=self._mute_selected)
        self.player_menu.add_command(label="Teleport to Player", command=self._teleport_to_selected)
        self.player_menu.add_command(label="Give Item...", command=self._give_item_dialog)
        self.player_menu.add_separator()
        self.player_menu.add_command(label="Kill Player", command=self._kill_selected)
        self.tree.bind("<Button-3>", self._show_player_menu)

        # Command entry with better styling
        bot = tk.Frame(self, bg=bg_color)
        bot.pack(fill=tk.X, padx=10, pady=(5, 0))
        tk.Label(bot, text="Command:", bg=bg_color, fg=fg_color).pack(side=tk.LEFT)
        self.command_entry = tk.Entry(bot, bg=entry_bg, fg=fg_color, insertbackground=fg_color, relief=tk.SOLID, bd=1)
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.command_entry.bind("<Return>", self._send_command)
        tk.Button(bot, text="Send", command=self._send_command, bg="#2196F3", fg="white", activebackground="#0b7dda", relief=tk.FLAT, padx=15).pack(side=tk.LEFT)

        # Quick commands
        quick_frame = tk.Frame(self, bg=bg_color)
        quick_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(quick_frame, text="Quick:", bg=bg_color, fg=fg_color, font=("Arial", 9)).pack(side=tk.LEFT)
        for cmd in ["status", "players", "banlistex", "serverinfo"]:
            tk.Button(quick_frame, text=cmd, command=lambda c=cmd: self._quick_command(c), bg="#3C3C3C", fg=fg_color, activebackground="#555555", relief=tk.FLAT, padx=8, pady=2, font=("Arial", 8)).pack(side=tk.LEFT, padx=2)

        # Status bar
        self.status_bar = tk.Label(self, text="Ready", bg="#1E1E1E", fg="#808080", anchor=tk.W, font=("Arial", 8), padx=10)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.logger = Logger(self.console_tab, self.LOG_PATH, self.TAG_COLORS, self.TAG_WHITELIST)
        self._update_status_bar("Ready")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _update_status_bar(self, message):
        self.status_bar.configure(text=message)

    def _update_connection_status(self, connected):
        if connected:
            self.status_label.configure(text="● Connected", fg="#4CAF50")
            self._update_status_bar(f"Connected to {self.ip_entry.get()}:{self.port_entry.get()}")
        else:
            self.status_label.configure(text="● Disconnected", fg="#f44336")
            self._update_status_bar("Disconnected")

    def _show_player_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.player_menu.post(event.x_root, event.y_root)

    def _quick_command(self, cmd):
        if self.connected:
            asyncio.run_coroutine_threadsafe(self._send_json_command(cmd), self.loop)
            self.logger.log(f"[Command] {cmd}")

    def _kick_selected(self):
        player = self.players.get_selected()
        if player:
            name = player[0]
            if messagebox.askyesno("Kick Player", f"Kick {name}?"):
                asyncio.run_coroutine_threadsafe(self._send_json_command(f'kick "{name}"'), self.loop)
                self.logger.log(f'[Command] kick "{name}"')

    def _ban_selected(self):
        player = self.players.get_selected()
        if player:
            name = player[0]
            if messagebox.askyesno("Ban Player", f"Ban {name}?"):
                asyncio.run_coroutine_threadsafe(self._send_json_command(f'banid "{name}"'), self.loop)
                self.logger.log(f'[Command] banid "{name}"')

    def _mute_selected(self):
        player = self.players.get_selected()
        if player:
            name = player[0]
            asyncio.run_coroutine_threadsafe(self._send_json_command(f'mute "{name}"'), self.loop)
            self.logger.log(f'[Command] mute "{name}"')

    def _teleport_to_selected(self):
        player = self.players.get_selected()
        if player:
            name = player[0]
            asyncio.run_coroutine_threadsafe(self._send_json_command(f'teleport.toplayer "{name}"'), self.loop)
            self.logger.log(f'[Command] teleport.toplayer "{name}"')

    def _kill_selected(self):
        player = self.players.get_selected()
        if player:
            name = player[0]
            if messagebox.askyesno("Kill Player", f"Kill {name}?"):
                asyncio.run_coroutine_threadsafe(self._send_json_command(f'killplayer "{name}"'), self.loop)
                self.logger.log(f'[Command] killplayer "{name}"')

    def _give_item_dialog(self):
        player = self.players.get_selected()
        if not player:
            messagebox.showwarning("No Player", "Please select a player first.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Give Item")
        dialog.geometry("450x350")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg="#2B2B2B")

        tk.Label(dialog, text=f"Give item to {player[0]}", bg="#2B2B2B", fg="#E0E0E0").pack(pady=10)

        tk.Label(dialog, text="Search Item:", bg="#2B2B2B", fg="#E0E0E0").pack()
        search_var = tk.StringVar()
        search_entry = tk.Entry(dialog, textvariable=search_var, bg="#3C3C3C", fg="#E0E0E0", insertbackground="#E0E0E0", relief=tk.SOLID, bd=1)
        search_entry.pack(fill=tk.X, padx=20, pady=5)

        listbox_frame = tk.Frame(dialog, bg="#2B2B2B")
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        listbox = tk.Listbox(listbox_frame, bg="#3C3C3C", fg="#E0E0E0", selectbackground="#4CAF50", relief=tk.FLAT, bd=0)
        listbox.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def update_list(*args):
            listbox.delete(0, tk.END)
            query = search_var.get()
            if query:
                results = self.item_db.search(query)
                for item in results[:50]:
                    listbox.insert(tk.END, f"{item['Name']} ({item['Shortname']})")

        search_var.trace_add("write", update_list)

        def give_item():
            selection = listbox.curselection()
            if selection:
                item_text = listbox.get(selection[0])
                shortname = item_text.split("(")[-1].rstrip(")")
                asyncio.run_coroutine_threadsafe(
                    self._send_json_command(f'inv.giveplayer "{player[0]}" {shortname} 1'),
                    self.loop
                )
                self.logger.log(f'[Command] inv.giveplayer "{player[0]}" {shortname} 1')
                dialog.destroy()

        tk.Button(dialog, text="Give", command=give_item, bg="#4CAF50", fg="white", activebackground="#45a049", relief=tk.FLAT, padx=20, pady=5).pack(pady=10)

    def _show_banlist(self):
        if self.connected:
            asyncio.run_coroutine_threadsafe(self._send_json_command("global.banlistex"), self.loop)
            self.tabs.select(self.ban_tab)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _connect(self):
        with self._lock:
            if self.connected or self._connecting:
                self.logger.log("[WARN] Already connected or connecting.")
                return
            self._connecting = True

        try:
            ip = self.ip_entry.get().strip()
            port_str = self.port_entry.get().strip()
            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    self.logger.log("[ERROR] Port must be between 1 and 65535.")
                    with self._lock:
                        self._connecting = False
                    return
            except ValueError:
                self.logger.log("[ERROR] Invalid port number.")
                with self._lock:
                    self._connecting = False
                return

            password = self.password_entry.get()
            if not password:
                self.logger.log("[ERROR] Password cannot be empty.")
                with self._lock:
                    self._connecting = False
                return

            self.config_mgr.save({"ip": ip, "port": port, "password": password})
        except Exception as e:
            self.logger.log(f"[ERROR] {e}")
            with self._lock:
                self._connecting = False
            return

        def run():
            async def do_connect():
                try:
                    encoded_password = urllib.parse.quote(password, safe='')
                    uri = f"ws://{ip}:{port}/?password={encoded_password}"
                    self.logger.log(f"[INFO] Connecting to {ip}:{port}...")
                    self.websocket = await websockets.connect(uri, ping_interval=None, timeout=10)
                    with self._lock:
                        self.connected = True
                    self.logger.log(f"[OK] Connected to {ip}:{port}")
                    self._update_connection_status(True)
                    self._start_receiver()
                    self._start_status_polling()
                    await self._send_json_command("status")
                    await self._send_json_command("players")
                except websockets.exceptions.InvalidURI:
                    self.logger.log("[ERROR] Invalid server URI. Check IP and port.")
                except ConnectionRefusedError:
                    self.logger.log("[ERROR] Connection refused. Server may be offline.")
                except asyncio.TimeoutError:
                    self.logger.log("[ERROR] Connection timeout.")
                except Exception as e:
                    self.logger.log(f"[ERROR] Connection failed: {e}")
                finally:
                    with self._lock:
                        self._connecting = False
            asyncio.run_coroutine_threadsafe(do_connect(), self.loop)

        threading.Thread(target=run, daemon=True).start()

    def _disconnect(self):
        with self._lock:
            self.connected = False
            self._receiver_running = False
            self._status_polling = False

        if self._receiver_task:
            future = self._receiver_task
            asyncio.run_coroutine_threadsafe(future.cancel(), self.loop)
            self._receiver_task = None

        if self.websocket:
            ws = self.websocket
            asyncio.run_coroutine_threadsafe(ws.close(), self.loop)
            self.websocket = None

        self.logger.log("[WARN] Disconnected.")
        self._update_connection_status(False)

    def _send_command(self, event=None):
        with self._lock:
            is_connected = self.connected
        if is_connected and self.command_entry.get().strip():
            command = self.command_entry.get().strip().strip('"')
            self.logger.log(f"[Command] {command}")
            asyncio.run_coroutine_threadsafe(self._send_json_command(command), self.loop)
            self.command_entry.delete(0, tk.END)

    def _start_receiver(self):
        async def receive():
            self.logger.log("[INFO] Listening for server messages...")
            self._receiver_running = True
            try:
                while self._receiver_running:
                    try:
                        if self.websocket is None:
                            break
                        data = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                        self._handle_message(data)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        if self._receiver_running:
                            self.logger.log("[ERROR] Connection closed by server.")
                        break
                    except Exception as e:
                        if self._receiver_running:
                            self.logger.log(f"[ERROR] Receiver error: {e}")
                        break
            finally:
                self._receiver_running = False
                if self.connected:
                    self.after(0, self._disconnect)
        self._receiver_task = asyncio.run_coroutine_threadsafe(receive(), self.loop)

    def _start_status_polling(self):
        async def poll():
            self._status_polling = True
            while self._status_polling:
                with self._lock:
                    if not self.connected:
                        break
                now = time.time()
                if now - self.last_status_time >= self.status_interval:
                    await self._send_json_command("status")
                    self.last_status_time = now
                await asyncio.sleep(1)
        asyncio.run_coroutine_threadsafe(poll(), self.loop)

    def _handle_message(self, raw):
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
        try:
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8', errors='ignore')

            if isinstance(raw, str):
                msg = json.loads(raw)
                mtype = msg.get("Type", "")
                body = msg.get("Message", "")
                if body is None:
                    body = ""

                if mtype == "Chat":
                    try:
                        chat = json.loads(body)
                        user = chat.get("Username", "Unknown")
                        text = chat.get("Message", "")
                        self.logger.log(f"{timestamp}[Chat][{user}] {text}")
                    except (json.JSONDecodeError, TypeError):
                        self.logger.log(f"{timestamp}[Chat] {body}")
                elif mtype == "Generic":
                    cleaned = body.replace("\r", "").strip()
                    self.logger.log(f"{timestamp}[Server] {cleaned}")
                    if "players" in cleaned.lower() or re.search(r'\d{17}', cleaned):
                        self.players.update(cleaned)
                    elif "ban" in cleaned.lower():
                        self._update_ban_tab(f"{timestamp}[Ban] {cleaned}")
                elif mtype == "Error":
                    self.logger.log(f"{timestamp}[ERROR] {body}")
                else:
                    self.logger.log(f"{timestamp}[{mtype}] {body}")
            else:
                self.logger.log(f"{timestamp}[ERROR] Unexpected data type: {type(raw)}")
        except json.JSONDecodeError:
            if isinstance(raw, (str, bytes)):
                text = raw if isinstance(raw, str) else raw.decode('utf-8', errors='ignore')
                cleaned = text.strip()
                self.logger.log(f"{timestamp}[Server] {cleaned}")
                if "ban" in cleaned.lower() or "steamid" in cleaned.lower():
                    self._update_ban_tab(f"{timestamp}[Ban] {cleaned}")
        except Exception as e:
            self.logger.log(f"[ERROR] Failed to parse message: {e}")

    def _update_ban_tab(self, message):
        self.ban_tab.configure(state="normal")
        self.ban_tab.insert(tk.END, message + "\n")
        self.ban_tab.see(tk.END)
        self.ban_tab.configure(state="disabled")

    async def _send_json_command(self, command):
        with self._identifier_lock:
            identifier = self.identifier_counter
            self.identifier_counter += 1
        msg = {
            "Identifier": identifier,
            "Message": command,
            "Name": "WebRcon",
            "Type": 2
        }
        if self.websocket is None:
            self.logger.log("[ERROR] Not connected to server.")
            return
        try:
            await self.websocket.send(json.dumps(msg))
        except Exception as e:
            self.logger.log(f"[ERROR] Failed to send command: {e}")
            self._disconnect()

    def _on_close(self):
        self._disconnect()
        self.update()
        self.after(100, self._final_close)

    def _final_close(self):
        if self.websocket is not None:
            self.after(100, self._final_close)
            return
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.destroy()

if __name__ == "__main__":
    app = WebRCONApp()
    app.mainloop()
