import os
import json
import asyncio
import datetime
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import websockets
import re
import time
import urllib.parse
import base64
import hashlib
import secrets

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
        # Simple XOR-based obfuscation (not cryptographically secure, but better than base64)
        # For real security, use keyring or cryptography library
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

    def log(self, message):
        self.widget.after(0, self._log_message, message)

    def _log_message(self, message):
        self.widget.configure(state="normal")
        tags = re.findall(r"\[[^\]]+\]", message)
        for tag in tags:
            if tag not in self.tag_whitelist:
                continue
            if tag not in self.tag_color_map:
                self.tag_color_map[tag] = self.tag_colors[len(self.tag_color_map) % len(self.tag_colors)]
            try:
                if not self.widget.tag_cget(tag, "foreground"):
                    self.widget.tag_config(tag, foreground=self.tag_color_map[tag])
            except tk.TclError:
                self.widget.tag_config(tag, foreground=self.tag_color_map[tag])
        start_index = self.widget.index(tk.END)
        self.widget.insert(tk.END, message + "\n")
        for tag in tags:
            if tag not in self.tag_whitelist:
                continue
            for match in re.finditer(re.escape(tag), message):
                tag_start = match.start()
                tag_end = match.end()
                self.widget.tag_add(tag, f"{start_index}+{tag_start}c", f"{start_index}+{tag_end}c")
        self.widget.see(tk.END)
        self.widget.configure(state="disabled")
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(message + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}")

# --- Player Manager ---
class PlayerManager:
    def __init__(self, treeview):
        self.tree = treeview

    def update(self, message):
        lines = message.splitlines()
        # More robust player line detection - look for lines with SteamID pattern
        player_lines = [line for line in lines if re.search(r'\d{17}', line)]  # SteamID is 17 digits
        self.tree.delete(*self.tree.get_children())
        for line in player_lines:
            # Try multiple parsing strategies
            parts = re.split(r"\s{2,}|\t", line.strip())
            if len(parts) >= 4:
                try:
                    # Try to extract name, ping, steamid, connected time
                    # Format is typically: #  Name  Ping  SteamID  Connected
                    name = ""
                    ping = ""
                    steamid = ""
                    connected = ""
                    
                    # Find SteamID (17 digit number)
                    for i, part in enumerate(parts):
                        if re.match(r'\d{17}', part):
                            steamid = part
                            # Name is typically everything before SteamID
                            name = " ".join(parts[1:i]) if i > 1 else parts[1] if len(parts) > 1 else ""
                            # Ping is typically before SteamID
                            if i > 2 and parts[i-1].isdigit():
                                ping = parts[i-1]
                            # Connected time is after SteamID
                            if i + 1 < len(parts):
                                connected = " ".join(parts[i+1:])
                            break
                    
                    if steamid:
                        self.tree.insert("", "end", values=(name, ping, steamid, connected))
                except Exception:
                    continue

    def filter(self, query):
        q = query.lower()
        all_items = self.tree.get_children()
        for item in all_items:
            values = self.tree.item(item)["values"]
            if any(q in str(v).lower() for v in values):
                if not self.tree.winfo_ismapped() or self.tree.get_children():
                    # Reattach if detached
                    try:
                        self.tree.reattach(item, '', 'end')
                    except tk.TclError:
                        pass  # Already attached
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
                # Handle SteamID and other large numbers as strings
                if col in ("SteamID",):
                    value = (value, k)
                elif '.' in value:
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

# --- Main GUI + WebSocket ---
class WebRCONApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rust Admin Tool (R.A.T.)")
        self.geometry("900x600")
        self.minsize(200, 200)

        self.CONFIG_PATH = os.path.join(os.path.expanduser("~"), "Documents", "RAT_config.JSON")
        self.LOG_PATH = os.path.join(os.path.expanduser("~"), "Documents", "RAT_log.txt")

        self.DEFAULT_IP = "SET_YOUR_SERVER_IP_HERE"
        self.DEFAULT_PORT = 28015
        self.DEFAULT_PASSWORD = "ADMIN_PASSWORD_HERE"
        self.TAG_COLORS = ["red", "blue", "green", "orange", "purple", "brown", "cyan", "magenta"]
        self.TAG_WHITELIST = {"[OK]", "[ERROR]", "[WARN]", "[INFO]", "[Chat]", "[Server]", "[Command]", "[Players]", "[Hostname]", "[Version]", "[Map]"}

        self.config_mgr = ConfigManager(self.CONFIG_PATH)
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

        menubar = tk.Menu(self)
        server_menu = tk.Menu(menubar, tearoff=0)
        server_menu.add_command(label="Connect", command=self._connect)
        server_menu.add_command(label="Disconnect", command=self._disconnect)
        menubar.add_cascade(label="Server", menu=server_menu)
        self.config(menu=menubar)

        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(top, text="IP:").pack(side=tk.LEFT)
        self.ip_entry = tk.Entry(top, width=15)
        self.ip_entry.insert(0, ip)
        self.ip_entry.pack(side=tk.LEFT, padx=2)
        tk.Label(top, text="Port:").pack(side=tk.LEFT)
        self.port_entry = tk.Entry(top, width=6)
        self.port_entry.insert(0, str(port))
        self.port_entry.pack(side=tk.LEFT, padx=2)
        tk.Label(top, text="Password:").pack(side=tk.LEFT)
        self.password_entry = tk.Entry(top, show="*", width=12)
        self.password_entry.insert(0, password)
        self.password_entry.pack(side=tk.LEFT, padx=2)

        mid = tk.Frame(self)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tabs = ttk.Notebook(mid)
        self.console_tab = tk.Text(self.tabs, wrap=tk.WORD, state="disabled")
        self.tabs.add(self.console_tab, text="Console")
        player_tab = tk.Frame(self.tabs)
        search_frame = tk.Frame(player_tab)
        search_frame.pack(fill=tk.X, padx=5, pady=2)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.players.filter(self.search_var.get()))
        tk.Entry(search_frame, textvariable=self.search_var).pack(fill=tk.X, expand=True)
        self.tree = ttk.Treeview(player_tab, columns=("Name", "Ping", "SteamID", "Connected"), show="headings")
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col, command=lambda c=col: self.players.sort(c, False))
            self.tree.column(col, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tabs.add(player_tab, text="Players")
        self.tabs.pack(fill=tk.BOTH, expand=True)
        self.players = PlayerManager(self.tree)

        bot = tk.Frame(self)
        bot.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(bot, text="Command:").pack(side=tk.LEFT)
        self.command_entry = tk.Entry(bot)
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.command_entry.bind("<Return>", self._send_command)
        tk.Button(bot, text="Send", command=self._send_command).pack(side=tk.LEFT)

        self.logger = Logger(self.console_tab, self.LOG_PATH, self.TAG_COLORS, self.TAG_WHITELIST)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

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
                    self._start_receiver()
                    self._start_status_polling()
                    await self._send_json_command("status")
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
                # Auto-disconnect on receiver failure
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
                
                # Handle different message types from Rust RCON
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
                    self.players.update(cleaned)
                elif mtype == "Error":
                    self.logger.log(f"{timestamp}[ERROR] {body}")
                else:
                    self.logger.log(f"{timestamp}[{mtype}] {body}")
            else:
                self.logger.log(f"{timestamp}[ERROR] Unexpected data type: {type(raw)}")
        except json.JSONDecodeError:
            # Raw message that's not JSON - just log it
            if isinstance(raw, (str, bytes)):
                text = raw if isinstance(raw, str) else raw.decode('utf-8', errors='ignore')
                self.logger.log(f"{timestamp}[Server] {text.strip()}")
        except Exception as e:
            self.logger.log(f"[ERROR] Failed to parse message: {e}")

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
        # Give time for cleanup
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
