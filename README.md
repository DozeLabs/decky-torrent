# Decky Torrent

![Decky Plugin](https://img.shields.io/badge/Decky-Plugin-blue)
![Version](https://img.shields.io/badge/release-v1.0.0-green)
![License](https://img.shields.io/badge/license-BSD--3--Clause-blue)

<p align="center">
  <img src="assets/logo.png" alt="Decky Torrent Logo" width="128" height="128" />
</p>

**Rootless background Transmission torrent client manager for Bazzite and SteamOS.**

**Decky Torrent** is a rootless background client execution manager for the Transmission torrent daemon, designed as a plugin for **Decky Loader** on SteamOS and Bazzite. The plugin orchestrates a headless Transmission container inside rootless Podman and exposes a responsive configuration interface and connection URL overlay directly within the SteamOS Gaming Mode Quick Access Menu (QAM).

---

## Features

### Rootless Orchestration
- **No Root Required**: Manages a headless Transmission daemon inside a rootless Podman container (`decky-torrent`), avoiding any modification of immutable system layers.
- **SELinux Compatibility**: Enforces strict `:Z` flag bound volume mappings to ensure proper host-to-container access without SELinux violations.

### Unified QAM Interface
- **State-aware Status Indicator**: See if the Transmission container is Running, Stopped, or Missing at a glance.
- **Quick Action Controls**: Start, Stop, and Restart the container daemon directly from the SteamOS Gaming Mode Quick Access Menu (QAM).
- **Remote Control Overlay**: Displays your remote control access URL (e.g., `http://<your-deck-ip>:9091`) directly in the QAM for easy reference.
- **Web UI & Connection Details**: Quick access to connect via browser or remote Transmission apps.

### Host Storage Passthrough
- **Internal Storage (SSD)**: Home directory (`~`) mapped to `/home_dir` inside the container.
- **Removable Media**: Removable media storage (`/run/media`) mapped to `/media` inside the container, granting direct access to SD Cards and external USB drives.

---

## Storage Mappings for Torrenting

When adding or configuring torrent downloads inside the Transmission Web UI, use the following paths to direct files to the correct physical location:

| Host Location | Container Path | Usage / Example |
| :--- | :--- | :--- |
| **Internal SSD** (`~`) | `/home_dir/...` | Route downloads to `/home_dir/Downloads/` |
| **SD Cards & USBs** (`/run/media`) | `/media/...` | Route downloads to `/media/primary/` or `/media/my_external_drive/` |

---

## Installation

### From Decky Store
*(Coming Soon / Available in the Decky Store)*

### Manual Installation
1. Download the latest release `.zip` from the [Releases](https://github.com/danielmaman/decky-torrent/releases) page.
2. Open **Decky Loader** > **Settings** > **Developer** > **Install from Zip**.
3. Select the downloaded Zip file (do not extract it!).
4. Restart Decky Loader if prompted.

---

## Development

### Prerequisites
- **Node.js** (v16.14+)
- **pnpm** (v9+)
- **SSH** enabled on your target Bazzite/SteamOS device.

### Step 1: Install Dependencies & Build Locally
Pull in the required React modules and run the compilation to generate the frontend bundle:
```bash
pnpm install
pnpm run build
```

### Step 2: Configure SSH on Bazzite / SteamOS
To deploy the plugin over the network, your development computer needs SSH access to your gaming machine:
1. Open the terminal on your Bazzite/SteamOS machine.
2. Set a password for the default user:
   ```bash
   passwd
   ```
3. Enable and start the SSH daemon:
   ```bash
   sudo systemctl enable --now sshd
   ```
4. Find the device's IP address (Settings -> Internet -> Connection Details).

### Step 3: Configure Deployment Credentials
Open or create `.vscode/settings.json` and configure it with your Bazzite/SteamOS machine credentials:
```json
{                                                                                                                                                         
  "deckip"    : "192.168.x.xxx",                                                                                         
  "deckport"  : "22",      
  "deckuser"  : "deck",    
  "deckpass"  : "xxxx",                                                                                 
  "deckkey"   : "",                                                                                                             
  "deckdir"   : "/home/deck",   
  "pluginname": "decky-torrent",
  "isDevModeEnabled": "false"                                                                                                    
}  
```

### Step 4: Build & Deploy Over Network
This repository includes configured VS Code tasks to automate build, package, network copy, and plugin reload.
1. Open the project in VS Code.
2. Open the Command Palette (`Cmd+Shift+P` / `Ctrl+Shift+P`).
3. Select **Tasks: Run Task** and choose:
   - **`setup`**: Downloads the local Decky CLI compiler tool and validates tools.
   - **`builddeploy`**: Compiles the TSX frontend, packages the plugin assets, uploads them to your device via SSH/rsync, and restarts the Decky Loader daemon to apply the updates.

### Creating an Installable Zip File
If your development machine has a container engine installed, you can use the official Decky build compiler:
```bash
# Build TSX frontend
pnpm run build

# Package with Decky CLI (outputs to ./out/)
./cli/decky plugin build
```

---

## License

Licensed under the BSD 3-Clause License. See [LICENSE](LICENSE) for details.

---

## Credits

- **Author**: [DozeLabs](https://github.com/danielmaman)
- **Framework**: [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader)
- **Container Image**: [linuxserver/transmission](https://hub.docker.com/r/linuxserver/transmission)
