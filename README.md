# Rust Admin Tool (R.A.T.)

A Python-based GUI application for managing Rust game servers via RCON (Remote Console) protocol. This tool is inspired by and based on the popular **RustAdmin** application found in the "Rust Admin Release" folder.

## Features

### Core Features
- **Real-time Console** - View server messages, chat, and command responses in real-time
- **Player Management** - Monitor online players with SteamID, ping, and connection time
- **Player Actions** - Right-click or use buttons to Kick, Ban, Mute, Teleport, or Kill players
- **Item Database** - Built-in database of all Rust items for quick item giving
- **Player Search** - Filter players by name, SteamID, or other attributes
- **Player Sorting** - Sort player list by any column (Name, Ping, SteamID, Connected time)
- **Command Execution** - Send RCON commands directly from the GUI
- **Quick Commands** - One-click buttons for common commands (status, players, banlistex, serverinfo)
- **Ban List Viewer** - View and manage server ban list
- **Auto Status Polling** - Automatically refreshes server status every 15 seconds
- **Colored Logs** - Tag-based color coding for different message types

### Improvements Over Original RustAdmin
- Open source Python implementation
- Cross-platform compatibility (Windows, Linux, macOS)
- Modern tkinter-based GUI
- Better error handling and connection management
- Improved player parsing using RustAdmin's regex patterns
- Thread-safe operations

## Requirements

- Python 3.7+
- websockets library
- tkinter (usually included with Python)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/R0U5/RustAdminTool.git
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

### Connecting to a Server
1. Launch the application
2. Enter your Rust server IP, port (default: 28015), and RCON password
3. Click "Connect" or use Server menu
4. Monitor the console for server messages

### Managing Players
- **View Players**: Click the "Players" tab to see all online players
- **Search Players**: Use the search box to filter by name or SteamID
- **Player Actions**: Right-click any player or select and use action buttons:
  - **Kick** - Remove player from server
  - **Ban** - Permanently ban player
  - **Mute** - Mute player chat
  - **Teleport** - Teleport yourself to the player
  - **Give Item** - Give items to player from the item database
  - **Kill** - Kill the player in-game

### Commands
- Type commands in the command box and press Enter or click Send
- Use Quick Command buttons for common commands
- View ban list via Tools menu

## Configuration

The application saves your connection settings to `~/Documents/RAT_config.JSON`. 
- Passwords are obfuscated using XOR encryption with a salt file
- Not cryptographically secure - use with caution on shared computers

## Message Types

- `[OK]` - Successful operations
- `[ERROR]` - Errors and connection issues
- `[WARN]` - Warnings
- `[INFO]` - Informational messages
- `[Chat]` - In-game chat messages
- `[Server]` - Server responses
- `[Command]` - Sent commands
- `[Ban]` - Ban list entries

## Item Database

RAT.py includes a comprehensive item database (`items.json`) with:
- Item names and shortnames
- Categories (Weapons, Construction, Resources, etc.)
- Item descriptions

Use the "Give Item" dialog to quickly find and give items to players.

## Disclaimer

This tool is not affiliated with Facepunch Studios or Rust. Use responsibly and ensure you have proper authorization to access the server's RCON interface.

## License

MIT License - See LICENSE file for details
