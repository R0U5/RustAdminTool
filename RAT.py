import os
import json
import asyncio
import datetime
import threading
try:
    import tkinter as tk
    import customtkinter as ctk
    from tkinter import messagebox, ttk, Menu
    import websockets
except ImportError as e:
    print(f"Missing required module: {e}")
    print("Please install required dependencies:")
    print("  pip install customtkinter websockets")
    print("Or see requirements.txt for full list.")
    exit(1)

import re
import urllib.parse
import base64
import hashlib
import secrets

# Set CustomTkinter appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Pre-compile regex patterns for performance
PLAYER_REGEX = re.compile(
    r'^(?P<num>\d+)\s+(?P<steamId>\d{17})\s+"(?P<playername>.*)"\s+(?P<ping>-?\d+)\s+(?P<connected>[\d.]+)s\s+(?P<ip>[\d.]+:\d+)\s*(?P<owner>\d{17})?\s*(?P<violation>[\d.]*)?\s*(?P<kicks>[\d.]*)?'
)
TAG_REGEX = re.compile(r"\[[^\]]+\]")

# Color palette - Dark theme (section 2.2) - Valid 7-char hex for tkinter
COLORS = {
    'bg_base': '#0A0A0F',
    'bg_elevated': '#12121A',
    'bg_surface': '#1A1A24',
    'bg_hover': '#22222E',
    'bg_active': '#2A2A38',
    'border_subtle': '#1E1E2A',
    'border_default': '#2A2A3A',
    'border_focus': '#4A6CF7',
    'text_primary': '#E8E8ED',
    'text_secondary': '#8888A0',
    'text_tertiary': '#55556A',
    'accent': '#4A6CF7',
    'accent_hover': '#5B7BFF',
    'accent_light': '#E8EDFD',  # Light version for subtle backgrounds
    'success': '#34D399',
    'success_subtle': '#E8FDF5',
    'warning': '#FBBF24',
    'warning_subtle': '#FEF9C3',
    'danger': '#F87171',
    'danger_subtle': '#FEE2E2',
    'info': '#60A5FA',
    'info_subtle': '#DBEAFE',
}

# Font configuration with fallbacks (section 3.1)
FONTS = {
    'display': ('Segoe UI', 'SF Pro Display', 'DM Sans', 'Verdana', 'sans-serif'),
    'mono': ('Consolas', 'SF Mono', 'Courier New', 'monospace'),
}

def _font(family, size, weight='normal'):
    """Create font tuple with fallback"""
    base = FONTS[family]
    return (base[0], size, weight)  # tkinter uses first available from system

# Spacing scale (section 4.1)
SPACE = {
    '1': 4,   # 0.25rem
    '2': 8,   # 0.5rem
    '3': 12,  # 0.75rem
    '4': 16,  # 1rem
    '5': 20,  # 1.25rem
    '6': 24,  # 1.5rem
    '8': 32,  # 2rem
}

# Border radius scale (section 6.1)
RADIUS = {
    'sm': 4,
    'md': 8,
    'lg': 12,
    'xl': 16,
}

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


class Logger:
    def __init__(self, widget, log_file, tag_colors, tag_whitelist):
        self.widget = widget
        self.log_file = log_file
        self.tag_colors = tag_colors
        self.tag_color_map = {}
        self.tag_whitelist = tag_whitelist
        self._setup_tags()

    def _setup_tags(self):
        for tag in self.tag_whitelist:
            color = self.tag_colors.get(tag, COLORS['text_secondary'])
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

        for tag in set(tags):
            if tag not in self.tag_whitelist:
                continue
            if tag not in self.tag_color_map:
                self.tag_color_map[tag] = self.tag_colors.get(tag, COLORS['text_secondary'])
            for match in re.finditer(re.escape(tag), message):
                self.widget.tag_add(tag, f"{start_index}+{match.start()}c", f"{start_index}+{match.end()}c")

        self.widget.see(tk.END)
        self.widget.configure(state="disabled")

        threading.Thread(target=self._write_log, args=(message,), daemon=True).start()

    def _write_log(self, message):
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}")


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
        if len(self._search_cache) > 100:
            self._search_cache.clear()
        return results

    def get_categories(self):
        return sorted(self.categories)


class PlayerManager:
    def __init__(self, treeview, app):
        self.tree = treeview
        self.app = app
        self._cached_players = {}
        self._sort_reverse = {}

    def update(self, message):
        lines = message.splitlines()
        players_data = []
        for line in lines:
            match = PLAYER_REGEX.match(line.strip())
            if match:
                try:
                    name = match.group("playername")
                    ping = match.group("ping")
                    steamid = match.group("steamId")
                    connected = match.group("connected")
                    players_data.append((name, ping, steamid, connected))
                except Exception:
                    continue
        self.app.after(0, self._update_tree, players_data)

    def _update_tree(self, players_data):
        self.tree.delete(*self.tree.get_children())
        self._cached_players.clear()
        for name, ping, steamid, connected in players_data:
            item_id = self.tree.insert("", "end", values=(name, ping, steamid, connected))
            self._cached_players[steamid] = item_id

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

    def sort(self, col):
        reverse = not self._sort_reverse.get(col, False)
        self._sort_reverse[col] = reverse
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


class WebRCONApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Rust Admin Tool")
        self.geometry("1200x800")
        self.minsize(800, 600)

        self.configure(bg=COLORS['bg_base'])

        self.CONFIG_PATH = os.path.join(os.path.expanduser("~"), "Documents", "RAT_config.JSON")
        self.LOG_PATH = os.path.join(os.path.expanduser("~"), "Documents", "RAT_log.txt")
        self.ITEMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "items.json")

        self.DEFAULT_IP = "SET_YOUR_SERVER_IP_HERE"
        self.DEFAULT_PORT = 28015
        self.DEFAULT_PASSWORD = "ADMIN_PASSWORD_HERE"
        self.TAG_COLORS = {
            "[OK]": COLORS['success'],
            "[ERROR]": COLORS['danger'],
            "[WARN]": COLORS['warning'],
            "[INFO]": COLORS['info'],
            "[Chat]": COLORS['accent'],
            "[Server]": COLORS['text_secondary'],
            "[Command]": COLORS['text_primary'],
            "[Players]": COLORS['success'],
            "[Hostname]": COLORS['text_primary'],
            "[Version]": COLORS['text_secondary'],
            "[Map]": COLORS['text_secondary'],
            "[Ban]": COLORS['danger'],
        }
        self.TAG_WHITELIST = set(self.TAG_COLORS.keys())

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

    def _create_button(self, parent, text, command, style='secondary', **kwargs):
        """Create button with proper hierarchy (section 5.1)"""
        config = {
            'fg_color': COLORS['bg_elevated'],
            'text_color': COLORS['text_primary'],
            'font': _font('display', 12, 'normal'),
            'hover_color': COLORS['bg_hover'],
            'corner_radius': RADIUS['md'],
        }

        if style == 'primary':
            config['fg_color'] = COLORS['accent']
            config['text_color'] = COLORS['bg_base']
            config['hover_color'] = COLORS['accent_hover']
        elif style == 'destructive':
            config['fg_color'] = COLORS['danger_subtle']
            config['text_color'] = COLORS['danger']
            config['hover_color'] = COLORS['danger']
        elif style == 'ghost':
            config['fg_color'] = 'transparent'
            config['text_color'] = COLORS['accent']
            config['hover_color'] = COLORS['bg_hover']

        config.update(kwargs)
        btn = ctk.CTkButton(parent, text=text, command=command, **config)
        return btn

    def _create_entry(self, parent, **kwargs):
        """Create input with modern styling (section 5.4)"""
        config = {
            'fg_color': COLORS['bg_surface'],
            'text_color': COLORS['text_primary'],
            'font': _font('display', 12),
            'corner_radius': RADIUS['md'],
            'border_color': COLORS['border_default'],
            'border_width': 1,
        }
        config.update(kwargs)
        return ctk.CTkEntry(parent, **config)

    def _init_ui(self):
        config = self.config_mgr.load()
        ip = config.get("ip", self.DEFAULT_IP)
        port = config.get("port", self.DEFAULT_PORT)
        password = config.get("password", self.DEFAULT_PASSWORD)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=COLORS['bg_base'], borderwidth=0)
        style.configure('TNotebook.Tab',
                       background=COLORS['bg_elevated'],
                       foreground=COLORS['text_secondary'],
                       padding=(SPACE['4'], SPACE['2']),
                       font=_font('display', 11, 'normal'),
                       borderwidth=0)
        style.map('TNotebook.Tab',
                 background=[('selected', COLORS['bg_elevated'])],
                 foreground=[('selected', COLORS['accent'])])
        style.configure('Treeview',
                       background=COLORS['bg_surface'],
                       foreground=COLORS['text_primary'],
                       fieldbackground=COLORS['bg_surface'],
                       rowheight=40,
                       font=_font('mono', 11),
                       borderwidth=0)
        style.configure('Treeview.Heading',
                       background=COLORS['bg_elevated'],
                       foreground=COLORS['text_secondary'],
                       font=_font('display', 10, 'normal'),
                       borderwidth=0,
                       padding=(SPACE['3'], SPACE['2']))
        style.map('Treeview.Heading',
                 background=[('active', COLORS['bg_hover'])])
        style.map('Treeview',
                  background=[('selected', COLORS['accent_light'])])

        # Menu bar - tk.Menu is kept as CTk doesn't have Menu
        menubar = tk.Menu(self, bg=COLORS['bg_elevated'], fg=COLORS['text_primary'],
                           activebackground=COLORS['bg_hover'], activeforeground=COLORS['text_primary'],
                           bd=0, relief='flat')
        server_menu = tk.Menu(menubar, tearoff=0, bg=COLORS['bg_elevated'], fg=COLORS['text_primary'],
                               activebackground=COLORS['bg_hover'], activeforeground=COLORS['text_primary'])
        server_menu.add_command(label="Connect", command=self._connect)
        server_menu.add_command(label="Disconnect", command=self._disconnect)
        server_menu.add_separator()
        server_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="Server", menu=server_menu)

        tools_menu = tk.Menu(menubar, tearoff=0, bg=COLORS['bg_elevated'], fg=COLORS['text_primary'],
                               activebackground=COLORS['bg_hover'], activeforeground=COLORS['text_primary'])
        tools_menu.add_command(label="Ban List", command=self._show_banlist)
        tools_menu.add_command(label="Player List", command=lambda: asyncio.run_coroutine_threadsafe(self._send_json_command("players"), self.loop))
        menubar.add_cascade(label="Tools", menu=tools_menu)

        self.config(menu=menubar)

        # Top bar - Connection frame
        top = ctk.CTkFrame(self, fg_color=COLORS['bg_base'], height=56)
        top.pack(fill=tk.X, padx=SPACE['4'], pady=(SPACE['3'], 0))
        top.pack_propagate(False)

        # Left side - Logo/Title
        title_label = ctk.CTkLabel(top, text="R.A.T.", text_color=COLORS['accent'],
                                     font=_font('display', 14, 'bold'))
        title_label.pack(side=tk.LEFT, padx=(SPACE['2'], SPACE['4']))

        # Connection inputs
        ctk.CTkLabel(top, text="IP", text_color=COLORS['text_secondary'],
                       font=_font('display', 10)).pack(side=tk.LEFT, padx=(SPACE['2'], 2))
        self.ip_entry = self._create_entry(top, width=150)
        self.ip_entry.insert(0, ip)
        self.ip_entry.pack(side=tk.LEFT, padx=(0, 2), pady=SPACE['2'])

        ctk.CTkLabel(top, text="Port", text_color=COLORS['text_secondary'],
                       font=_font('display', 10)).pack(side=tk.LEFT, padx=(SPACE['3'], 2))
        self.port_entry = self._create_entry(top, width=60)
        self.port_entry.insert(0, str(port))
        self.port_entry.pack(side=tk.LEFT, padx=2, pady=SPACE['2'])

        ctk.CTkLabel(top, text="Password", text_color=COLORS['text_secondary'],
                       font=_font('display', 10)).pack(side=tk.LEFT, padx=(SPACE['3'], 2))
        self.password_entry = self._create_entry(top, show="*", width=300)
        self.password_entry.insert(0, password)
        self.password_entry.pack(side=tk.LEFT, padx=2, pady=SPACE['2'])

        # Connect/Disconnect buttons
        self.connect_btn = self._create_button(top, "Connect", self._connect, style='primary')
        self.connect_btn.pack(side=tk.LEFT, padx=(SPACE['3'], 2))

        self.disconnect_btn = self._create_button(top, "Disconnect", self._disconnect, style='destructive')
        self.disconnect_btn.pack(side=tk.LEFT)

        # Right side - Status indicator (section 5.6)
        self.status_frame = ctk.CTkFrame(top, fg_color=COLORS['bg_base'])
        self.status_frame.pack(side=tk.RIGHT)

        self.status_dot = tk.Canvas(self.status_frame, width=8, height=8, bg=COLORS['bg_base'],
                                      highlightthickness=0)
        self.status_dot.create_oval(0, 0, 8, 8, fill=COLORS['danger'], outline='')
        self.status_dot.pack(side=tk.LEFT, padx=(0, SPACE['1']))

        self.status_label = ctk.CTkLabel(self.status_frame, text="Disconnected",
                                          text_color=COLORS['text_secondary'],
                                          font=_font('display', 10, 'normal'))
        self.status_label.pack(side=tk.LEFT, padx=(0, SPACE['4']))

        # Main content area
        mid = ctk.CTkFrame(self, fg_color=COLORS['bg_base'])
        mid.pack(fill=tk.BOTH, expand=True, padx=SPACE['4'], pady=SPACE['3'])

        self.tabs = ttk.Notebook(mid)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        # Console tab
        console_frame = ctk.CTkFrame(self.tabs, fg_color=COLORS['bg_elevated'])
        console_frame.pack(fill=tk.BOTH, expand=True, padx=SPACE['2'], pady=SPACE['2'])

        self.console_tab = tk.Text(console_frame, wrap=tk.WORD, state="disabled",
                                    bg=COLORS['bg_base'], fg=COLORS['text_primary'],
                                    insertbackground=COLORS['text_primary'],
                                    relief='flat', bd=0,
                                    font=_font('mono', 11))
        self.console_tab.pack(fill=tk.BOTH, expand=True, padx=SPACE['2'], pady=SPACE['2'])
        self.tabs.add(console_frame, text="Console")

        # Players tab
        player_tab = ctk.CTkFrame(self.tabs, fg_color=COLORS['bg_elevated'])
        player_tab.pack(fill=tk.BOTH, expand=True)

        # Search bar
        search_frame = ctk.CTkFrame(player_tab, fg_color=COLORS['bg_elevated'])
        search_frame.pack(fill=tk.X, padx=SPACE['4'], pady=SPACE['3'])

        ctk.CTkLabel(search_frame, text="Search", text_color=COLORS['text_secondary'],
                       font=_font('display', 10, 'normal')).pack(side=tk.LEFT, padx=(0, SPACE['2']))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.players.filter(self.search_var.get()))
        search_entry = self._create_entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=SPACE['2'])

        # Action buttons - Grouped by function (section 4.2, 5.1)
        action_frame = ctk.CTkFrame(player_tab, fg_color=COLORS['bg_elevated'])
        action_frame.pack(fill=tk.X, padx=SPACE['4'], pady=(0, SPACE['2']))

        # Neutral actions group
        neutral_frame = ctk.CTkFrame(action_frame, fg_color=COLORS['bg_elevated'])
        neutral_frame.pack(side=tk.LEFT)
        btn = self._create_button(neutral_frame, "Teleport", self._teleport_to_selected, style='secondary')
        btn.configure(border_width=1, border_color=COLORS['border_default'])
        btn.pack(side=tk.LEFT, padx=(0, SPACE['2']))
        btn = self._create_button(neutral_frame, "Give Item", self._give_item_dialog, style='secondary')
        btn.configure(border_width=1, border_color=COLORS['border_default'])
        btn.pack(side=tk.LEFT)

        # Destructive actions group - visually separated
        destructive_frame = ctk.CTkFrame(action_frame, fg_color=COLORS['bg_elevated'])
        destructive_frame.pack(side=tk.LEFT, padx=(SPACE['6'], 0))
        btn = self._create_button(destructive_frame, "Kick", self._kick_selected, style='destructive')
        btn.configure(text_color='#0A0A0F', hover_color=COLORS['danger_subtle'], fg_color=COLORS['danger_subtle'])
        btn.pack(side=tk.LEFT, padx=(0, SPACE['2']))
        btn = self._create_button(destructive_frame, "Ban", self._ban_selected, style='destructive')
        btn.configure(text_color='#0A0A0F', hover_color=COLORS['danger_subtle'], fg_color=COLORS['danger_subtle'])
        btn.pack(side=tk.LEFT, padx=(0, SPACE['2']))
        btn = self._create_button(destructive_frame, "Mute", self._mute_selected, style='destructive')
        btn.configure(text_color='#0A0A0F', hover_color=COLORS['danger_subtle'], fg_color=COLORS['danger_subtle'])
        btn.pack(side=tk.LEFT, padx=(0, SPACE['2']))
        btn = self._create_button(destructive_frame, "Kill", self._kill_selected, style='destructive')
        btn.configure(text_color='#0A0A0F', hover_color=COLORS['danger_subtle'], fg_color=COLORS['danger_subtle'])
        btn.pack(side=tk.LEFT)

        # Player treeview
        tree_frame = ctk.CTkFrame(player_tab, fg_color=COLORS['bg_elevated'])
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=SPACE['4'], pady=(0, SPACE['3']))

        self.tree = ttk.Treeview(tree_frame, columns=("Name", "Ping", "SteamID", "Connected"),
                                   show="headings", selectmode="browse")
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col, command=lambda c=col: self.players.sort(c))
            anchor = 'e' if col in ("Ping",) else ('center' if col in ("Connected",) else 'w')
            width = 200 if col == "Name" else (100 if col == "SteamID" else 80)
            self.tree.column(col, anchor=anchor, width=width)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tabs.add(player_tab, text="Players")

        # Ban list tab
        ban_frame = ctk.CTkFrame(self.tabs, fg_color=COLORS['bg_elevated'])
        ban_frame.pack(fill=tk.BOTH, expand=True, padx=SPACE['2'], pady=SPACE['2'])

        self.ban_tab = tk.Text(ban_frame, wrap=tk.WORD, state="disabled",
                                bg=COLORS['bg_base'], fg=COLORS['text_primary'],
                                insertbackground=COLORS['text_primary'],
                                relief='flat', bd=0,
                                font=_font('mono', 11))
        self.ban_tab.pack(fill=tk.BOTH, expand=True, padx=SPACE['2'], pady=SPACE['2'])
        self.tabs.add(ban_frame, text="Bans")

        self.players = PlayerManager(self.tree, self)

        # Right-click context menu
        self.player_menu = Menu(self, tearoff=0, bg=COLORS['bg_elevated'], fg=COLORS['text_primary'],
                                 activebackground=COLORS['bg_hover'], activeforeground=COLORS['text_primary'])
        self.player_menu.add_command(label="Teleport to Player", command=self._teleport_to_selected)
        self.player_menu.add_command(label="Give Item...", command=self._give_item_dialog)
        self.player_menu.add_separator()
        self.player_menu.add_command(label="Kick", command=self._kick_selected)
        self.player_menu.add_command(label="Ban", command=self._ban_selected)
        self.player_menu.add_command(label="Mute", command=self._mute_selected)
        self.player_menu.add_separator()
        self.player_menu.add_command(label="Kill Player", command=self._kill_selected)
        self.tree.bind("<Button-3>", self._show_player_menu)

        # Command bar
        bot = ctk.CTkFrame(self, fg_color=COLORS['bg_base'])
        bot.pack(fill=tk.X, padx=SPACE['4'], pady=(0, SPACE['3']))

        ctk.CTkLabel(bot, text="Command", text_color=COLORS['text_secondary'],
                       font=_font('display', 10, 'normal')).pack(side=tk.LEFT, padx=(SPACE['2'], SPACE['2']))

        self.command_entry = self._create_entry(bot)
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=SPACE['2'])
        self.command_entry.bind("<Return>", self._send_command)

        send_btn = self._create_button(bot, "Send", self._send_command, style='primary')
        send_btn.pack(side=tk.LEFT, padx=(SPACE['2'], 0))

        # Quick commands
        quick_frame = ctk.CTkFrame(self, fg_color=COLORS['bg_base'])
        quick_frame.pack(fill=tk.X, padx=SPACE['4'], pady=(0, SPACE['3']))

        ctk.CTkLabel(quick_frame, text="Quick", text_color=COLORS['text_tertiary'],
                       font=_font('display', 9, 'normal')).pack(side=tk.LEFT, padx=(SPACE['2'], SPACE['2']))

        for cmd in ["status", "players", "banlistex", "serverinfo"]:
            btn = self._create_button(quick_frame, cmd, lambda c=cmd: self._quick_command(c), style='secondary')
            btn.configure(font=_font('mono', 9))
            btn.pack(side=tk.LEFT, padx=SPACE['1'], pady=SPACE['1'])

        # Status bar
        self.status_bar = ctk.CTkLabel(self, text="Ready", text_color=COLORS['text_tertiary'],
                                        anchor=tk.W, font=_font('display', 9), padx=SPACE['4'], pady=SPACE['1'])
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.logger = Logger(self.console_tab, self.LOG_PATH, self.TAG_COLORS, self.TAG_WHITELIST)
        self._update_status_bar("Ready")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _update_status_bar(self, message):
        self.status_bar.configure(text=message)

    def _update_connection_status(self, connected):
        self.after(0, self._do_update_connection_status, connected)

    def _do_update_connection_status(self, connected):
        if connected:
            self.status_dot.delete("all")
            self.status_dot.create_oval(0, 0, 8, 8, fill=COLORS['success'], outline='')
            self.status_label.configure(text="Connected", fg=COLORS['success'])
            self._update_status_bar(f"Connected to {self.ip_entry.get()}:{self.port_entry.get()}")
        else:
            self.status_dot.delete("all")
            self.status_dot.create_oval(0, 0, 8, 8, fill=COLORS['danger'], outline='')
            self.status_label.configure(text="Disconnected", fg=COLORS['text_secondary'])
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
            if messagebox.askyesno("Kick Player", f"Are you sure you want to kick {name}?"):
                asyncio.run_coroutine_threadsafe(self._send_json_command(f'kick "{name}"'), self.loop)
                self.logger.log(f'[Command] kick "{name}"')

    def _ban_selected(self):
        player = self.players.get_selected()
        if player:
            name = player[0]
            if messagebox.askyesno("Ban Player", f"Are you sure you want to ban {name}?"):
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
            if messagebox.askyesno("Kill Player", f"Are you sure you want to kill {name}?"):
                asyncio.run_coroutine_threadsafe(self._send_json_command(f'killplayer "{name}"'), self.loop)
                self.logger.log(f'[Command] killplayer "{name}"')

    def _give_item_dialog(self):
        player = self.players.get_selected()
        if not player:
            messagebox.showwarning("No Player", "Please select a player first.")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Give Item")
        dialog.geometry("500x400")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=COLORS['bg_elevated'])
        dialog.resizable(True, True)

        ctk.CTkLabel(dialog, text=f"Give item to {player[0]}",
                       text_color=COLORS['text_primary'],
                       font=_font('display', 14, 'normal')).pack(pady=SPACE['4'])

        ctk.CTkLabel(dialog, text="Search Item",
                       text_color=COLORS['text_secondary'],
                       font=_font('display', 10, 'normal')).pack(anchor=tk.W, padx=SPACE['6'], pady=(0, SPACE['2']))

        search_var = tk.StringVar()
        search_entry = self._create_entry(dialog, textvariable=search_var)
        search_entry.pack(fill=tk.X, padx=SPACE['6'], pady=(0, SPACE['3']))

        listbox_frame = ctk.CTkFrame(dialog, fg_color=COLORS['bg_elevated'])
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=SPACE['6'], pady=SPACE['3'])

        listbox = tk.Listbox(listbox_frame, bg=COLORS['bg_surface'], fg=COLORS['text_primary'],
                               selectbackground=COLORS['accent_light'],
                               selectforeground=COLORS['text_primary'],
                               relief='flat', bd=0,
                               font=_font('display', 11))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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

        give_btn = self._create_button(dialog, "Give Item", give_item, style='primary')
        give_btn.pack(pady=SPACE['4'])

    def _show_banlist(self):
        if self.connected:
            asyncio.run_coroutine_threadsafe(self._send_json_command("global.banlistex"), self.loop)
            self.tabs.select(2)

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
        self.after(0, self._do_update_ban_tab, message)

    def _do_update_ban_tab(self, message):
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
