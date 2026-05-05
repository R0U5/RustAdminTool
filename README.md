# Rust Admin Tool (R.A.T.)

A Python-based GUI application for managing Rust game servers via RCON (Remote Console) protocol. Features a modern tkinter interface with real-time console output, player management, and command execution.

## Features

- **Real-time Console** - View server messages, chat, and command responses in real-time
- **Player Management** - Monitor online players with SteamID, ping, and connection time
- **Player Search** - Filter players by name, SteamID, or other attributes
- **Player Sorting** - Sort player list by any column (Name, Ping, SteamID, Connected time)
- **Command Execution** - Send RCON commands directly from the GUI
- **Auto Status Polling** - Automatically refreshes server status every 15 seconds
- **Colored Logs** - Tag-based color coding for different message types ([OK], [ERROR], [Chat], etc.)
- **Connection Management** - Easy connect/disconnect with saved credentials
- **Cross-platform** - Works on Windows, Linux, and macOS (requires Python 3.7+)

## Requirements

- Python 3.7+
- websockets library
- tkinter (usually included with Python)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/RustAdminTool.git
cd RustAdminTool
```

2. Install dependencies:
```bash
pip install websockets
```

3. Run the application:
```bash
python RAT.py
```

## Usage

1. Launch the application
2. Enter your Rust server IP, port (default: 28015), and RCON password
3. Click "Connect" in the Server menu or use the default credentials if saved
4. Monitor the console for server messages
5. Use the Players tab to view and search online players
6. Type commands in the command box and press Enter or click Send

## Configuration

The application saves your connection settings to `~/Documents/RAT_config.JSON`. Passwords are obfuscated (not encrypted - use with caution).

## Message Types

- `[OK]` - Successful operations
- `[ERROR]` - Errors and connection issues
- `[WARN]` - Warnings
- `[INFO]` - Informational messages
- `[Chat]` - In-game chat messages
- `[Server]` - Server responses
- `[Command]` - Sent commands

## Disclaimer

This tool is not affiliated with Facepunch Studios or Rust. Use responsibly and ensure you have proper authorization to access the server's RCON interface.

## License

MIT License - See LICENSE file for details
