import os
import subprocess
import socket
import asyncio
import decky

class Plugin:
    def __init__(self):
        self.settings_file = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")

    async def _run_command(self, cmd):
        """
        Runs a shell command asynchronously and returns (stdout, stderr, returncode).
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return stdout.decode().strip(), stderr.decode().strip(), proc.returncode
        except Exception as e:
            decky.logger.error(f"Error running command {' '.join(cmd)}: {str(e)}")
            return "", str(e), -1

    def _is_writeable(self, path):
        """
        Robustly checks if a path is writeable by attempting to write a temp file.
        Bypasses the check if the path is inside the user's home directory, since
        systemd sandboxing of Decky Loader (e.g. ProtectHome) will block the Python
        daemon from writing there, while the rootless container can write there fine.
        """
        try:
            home = os.path.abspath(os.path.expanduser("~"))
            path = os.path.abspath(path)
            
            # If the path is under the user's home directory, assume it is writeable
            if os.path.commonpath([path, home]) == home:
                decky.logger.info(f"Path {path} is within home directory {home}. Bypassing write check (systemd sandbox safety).")
                return True
        except Exception as e:
            decky.logger.warning(f"Error checking home directory commonpath: {str(e)}")

        temp_file = os.path.join(path, ".decky_write_test")
        try:
            with open(temp_file, "w") as f:
                f.write("test")
            os.remove(temp_file)
            return True
        except Exception as e:
            decky.logger.error(f"Write validation failed for {path}: {str(e)}")
            return False

    def _load_settings(self):
        try:
            os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
            if os.path.exists(self.settings_file):
                import json
                with open(self.settings_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            decky.logger.error(f"Error loading settings: {str(e)}")
        return {}

    def _save_settings(self, data):
        try:
            os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
            import json
            with open(self.settings_file, "w") as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            decky.logger.error(f"Error saving settings: {str(e)}")
            return False

    async def get_download_path(self):
        """
        Returns the configured download path.
        """
        settings = self._load_settings()
        return {"download_path": settings.get("download_path")}

    async def set_download_path(self, path: str):
        """
        Validates, creates, and saves the download path.
        """
        decky.logger.info(f"Attempting to set download path to: {path}")
        if not path or not path.strip():
            decky.logger.error("Download path is empty.")
            return {"status": "failed", "message": "Path cannot be empty."}
        
        path = path.strip()
        # Resolve shorthand home ~
        if path.startswith("~"):
            home = os.path.expanduser("~")
            path = path.replace("~", home, 1)

        path = os.path.abspath(path)

        # Check/create directory
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            decky.logger.error(f"Failed to create download directory {path}: {str(e)}")
            return {"status": "failed", "message": f"Cannot create directory: {str(e)}"}

        # Save settings
        settings = self._load_settings()
        settings["download_path"] = path
        if self._save_settings(settings):
            decky.logger.info(f"Settings saved successfully. Download path is now: {path}")
            # Schedule container removal in the background so we return immediately.
            # The container must be removed so it gets re-created with the new volume mapping,
            # but we don't need to wait for podman to finish before telling the UI we're done.
            async def _remove_container_bg():
                status = await self._get_container_status()
                if status == "running" or status == "stopped":
                    decky.logger.info("Removing container in background to apply new download path volume mapping...")
                    await self._run_command(["podman", "rm", "-f", "decky-torrent"])
                    decky.logger.info("Container removed. Ready for re-creation.")
            asyncio.create_task(_remove_container_bg())
            return {"status": "success", "message": f"Download path configured to {path}"}
        else:
            decky.logger.error(f"Failed to save settings file to {self.settings_file}")
            return {"status": "failed", "message": "Failed to save settings file."}

    async def _get_container_status(self):
        """
        Query status of the container by name.
        Returns: "running", "stopped", or "missing"
        """
        stdout, stderr, code = await self._run_command(
            ["podman", "ps", "-a", "--filter", "name=decky-torrent", "--format", "{{.State}}"]
        )
        if code != 0 or not stdout:
            return "missing"
        if "running" in stdout:
            return "running"
        return "stopped"

    async def setup_transmission(self):
        """
        Idempotent environment preparation and container initialization.
        """
        # Read configured download path
        settings = self._load_settings()
        selected_path = settings.get("download_path")

        if not selected_path:
            return {"status": "no_path", "message": "No download folder configured. Please select a folder first."}

        # Ensure selected_path exists
        try:
            os.makedirs(selected_path, exist_ok=True)
        except Exception as e:
            return {"status": "failed", "message": f"Download folder access error: {str(e)}"}

        # Resolve path boundaries
        home = os.path.expanduser("~")

        # Always use our own dedicated config directory.
        # We intentionally do NOT use the Flatpak/system Transmission config because it
        # sets rpc-bind-address=127.0.0.1 which makes the Web UI unreachable from outside
        # the container, and we cannot patch it due to systemd ProtectHome sandbox restrictions.
        # Our own directory gets a clean config generated by the linuxserver image with all
        # the correct defaults, and our env vars (WHITELIST, HOST_WHITELIST) apply cleanly.
        config_dir = os.path.join(home, "transmission/config")
        os.makedirs(config_dir, exist_ok=True)
        decky.logger.info(f"Using dedicated Transmission config directory: {config_dir}")

        status = await self._get_container_status()

        # Check if the existing container has the correct mounts and env vars
        if status in ("running", "stopped"):
            try:
                import json
                stdout, stderr, code = await self._run_command(["podman", "inspect", "decky-torrent"])
                if code == 0 and stdout:
                    inspect_data = json.loads(stdout)
                    if inspect_data and isinstance(inspect_data, list):
                        mounts = inspect_data[0].get("Mounts", [])
                        config_ok = any(
                            m.get("Destination") == "/config" and
                            os.path.abspath(m.get("Source", "")) == os.path.abspath(config_dir)
                            for m in mounts
                        )
                        downloads_ok = any(
                            m.get("Destination") == "/downloads" and
                            os.path.abspath(m.get("Source", "")) == os.path.abspath(selected_path)
                            for m in mounts
                        )
                        env = inspect_data[0].get("Config", {}).get("Env", [])
                        whitelist_ok = any("WHITELIST=*" in e for e in env)
                        host_whitelist_ok = any("HOST_WHITELIST=*" in e for e in env)

                        if not config_ok or not downloads_ok or not whitelist_ok or not host_whitelist_ok:
                            decky.logger.info(
                                f"Container config mismatch (config:{config_ok}, downloads:{downloads_ok}, "
                                f"whitelist:{whitelist_ok}, host_whitelist:{host_whitelist_ok}). Re-creating."
                            )
                            await self._run_command(["podman", "rm", "-f", "decky-torrent"])
                            status = "missing"
            except Exception as e:
                decky.logger.error(f"Error inspecting container: {str(e)}")

        if status == "running":
            return {"status": "success", "message": "Service is actively running."}

        if status == "stopped":
            stdout, stderr, code = await self._run_command(["podman", "start", "decky-torrent"])
            if code == 0:
                return {"status": "success", "message": "Service started successfully."}
            else:
                decky.logger.error(f"Failed to start container: {stderr}")
                return {"status": "failed", "message": f"Failed to start: {stderr}"}

        # Resolve UID/GID dynamically
        uid = os.getuid()
        gid = os.getgid()

        # Construct Podman command. WHITELIST=* and HOST_WHITELIST=* are read by the
        # linuxserver/transmission init script and written into settings.json on first boot,
        # disabling all IP and hostname access restrictions.
        podman_cmd = [
            "podman", "run", "-d",
            "--name=decky-torrent",
            "--security-opt", "label=disable",
            "-e", f"PUID={uid}",
            "-e", f"PGID={gid}",
            "-e", "TZ=Etc/UTC",
            "-e", "TRANSMISSION_DOWNLOAD_DIR=/downloads",
            "-e", "WHITELIST=*",
            "-e", "HOST_WHITELIST=*",
            "-p", "9091:9091",
            "-p", "51413:51413",
            "-p", "51413:51413/udp",
            "-v", f"{config_dir}:/config:Z",
            "-v", f"{selected_path}:/downloads",
            "-v", f"{home}:/home_dir",
            "-v", "/run/media:/media",
            "--restart=always",
            "docker.io/linuxserver/transmission:latest"
        ]

        stdout, stderr, code = await self._run_command(podman_cmd)
        if code == 0:
            return {"status": "success", "message": "Service initialized and started successfully."}
        else:
            decky.logger.error(f"Container run failed: {stderr}")
            return {"status": "failed", "message": f"Execution failed: {stderr}"}

    async def stop_transmission(self):
        """
        Stops the running decky-torrent container.
        """
        status = await self._get_container_status()
        if status != "running":
            return {"status": "success", "message": f"Service is not running (Current: {status})."}
        
        stdout, stderr, code = await self._run_command(["podman", "stop", "decky-torrent"])
        if code == 0:
            return {"status": "success", "message": "Service stopped successfully."}
        else:
            decky.logger.error(f"Failed to stop container: {stderr}")
            return {"status": "failed", "message": f"Failed to stop: {stderr}"}

    async def restart_transmission(self):
        """
        Restarts the decky-torrent container.
        """
        status = await self._get_container_status()
        if status == "missing":
            return await self.setup_transmission()
        
        stdout, stderr, code = await self._run_command(["podman", "restart", "decky-torrent"])
        if code == 0:
            return {"status": "success", "message": "Service restarted successfully."}
        else:
            decky.logger.error(f"Failed to restart container: {stderr}")
            return {"status": "failed", "message": f"Failed to restart: {stderr}"}

    async def get_transmission_status(self):
        """
        Retrieves the exact running state of the container.
        """
        status = await self._get_container_status()
        return {"status": status}

    async def get_local_ip(self):
        """
        Resolves the primary network adapter's local IPv4 route.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return f"http://{ip}:9091"
        except Exception:
            return "http://127.0.0.1:9091"

    async def is_dev_mode_enabled(self):
        """
        Checks if isDevModeEnabled is set to True or 'true' in settings.json.
        """
        try:
            settings = self._load_settings()
            val = settings.get("isDevModeEnabled", False)
            return {"enabled": val is True or str(val).lower() == "true"}
        except Exception as e:
            decky.logger.error(f"Error checking dev mode: {str(e)}")
        return {"enabled": False}

    async def get_logs(self):
        """
        Retrieves log files for debugging. Accessible if 'debug' flag is in plugin.json,
        or if 'isDevModeEnabled' is True or 'true' in settings.json.
        """
        try:
            import json
            is_debug = False
            
            plugin_json_path = os.path.join(decky.DECKY_PLUGIN_DIR, "plugin.json")
            if os.path.exists(plugin_json_path):
                with open(plugin_json_path, "r") as f:
                    data = json.load(f)
                flags = data.get("flags", [])
                if "debug" in flags:
                    is_debug = True
            
            if not is_debug:
                settings = self._load_settings()
                val = settings.get("isDevModeEnabled", False)
                if val is True or str(val).lower() == "true":
                    is_debug = True

            if not is_debug:
                return {"success": False, "message": "Log viewing is disabled in production."}
        except Exception as e:
            return {"success": False, "message": f"Failed to verify debug flag/settings: {str(e)}"}

        logs = {}
        # 1. Read Plugin log
        try:
            log_path = decky.DECKY_PLUGIN_LOG
            if os.path.exists(log_path):
                with open(log_path, "r") as f:
                    lines = f.readlines()
                logs["plugin"] = "".join(lines[-150:])
            else:
                logs["plugin"] = f"Plugin log file not found at: {log_path}"
        except Exception as e:
            logs["plugin"] = f"Error reading plugin log: {str(e)}"

        # 2. Read Decky Loader log
        try:
            loader_log_path = os.path.join(decky.DECKY_HOME, "logs", "decky-loader.log")
            if not os.path.exists(loader_log_path):
                loader_log_path = os.path.join(decky.DECKY_HOME, "logging", "decky-loader.log")
            
            if os.path.exists(loader_log_path):
                with open(loader_log_path, "r") as f:
                    lines = f.readlines()
                logs["loader"] = "".join(lines[-150:])
            else:
                logs["loader"] = f"Decky loader log file not found at logs/ or logging/."
        except Exception as e:
            logs["loader"] = f"Error reading loader log: {str(e)}"

        # 3. Read Podman Container logs
        try:
            stdout, stderr, code = await self._run_command(["podman", "logs", "--tail", "150", "decky-torrent"])
            if code == 0:
                logs["container"] = stdout
            else:
                logs["container"] = f"Failed to get container logs (code {code}): {stderr}"
        except Exception as e:
            logs["container"] = f"Error reading container logs: {str(e)}"

        return {"success": True, "logs": logs}

    async def list_directories(self, path: str = ""):
        """
        Lists subdirectories of a given path.
        If path is empty or 'root', lists high-level entry points.
        """
        home = os.path.expanduser("~")
        
        if not path or path == "root":
            # Return entry anchors
            roots = [
                {"name": "Home Directory (~)", "path": home},
            ]
            if os.path.exists("/run/media"):
                roots.append({"name": "Removable Media (/run/media)", "path": "/run/media"})

            # Add all available mounted volumes (real filesystems only)
            try:
                # Filesystem types that represent real storage volumes
                real_fs_types = {
                    "ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs",
                    "vfat", "ntfs", "ntfs3", "exfat", "fuseblk",
                    "hfsplus", "udf", "iso9660", "reiserfs", "jfs"
                }
                # Prefixes to skip (system/virtual mount points already covered above)
                skip_prefixes = (
                    "/proc", "/sys", "/dev", "/run/user", "/run/media",
                    "/tmp", "/boot", home
                )
                already_shown = {r["path"] for r in roots}

                with open("/proc/mounts", "r") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) < 3:
                            continue
                        mount_point = parts[1]
                        fs_type = parts[2]

                        if fs_type not in real_fs_types:
                            continue
                        if any(mount_point.startswith(pfx) for pfx in skip_prefixes):
                            continue
                        if mount_point in already_shown:
                            continue
                        if not os.path.isdir(mount_point):
                            continue

                        vol_name = os.path.basename(mount_point) or mount_point
                        roots.append({
                            "name": f"Volume: {vol_name} ({mount_point})",
                            "path": mount_point
                        })
                        already_shown.add(mount_point)
            except Exception as e:
                decky.logger.warning(f"Could not enumerate volumes from /proc/mounts: {str(e)}")

            return {"success": True, "directories": roots}

        # Resolve path
        if path.startswith("~"):
            path = path.replace("~", home, 1)
        path = os.path.abspath(path)

        if not os.path.exists(path):
            return {"success": False, "message": "Path does not exist."}
        if not os.path.isdir(path):
            return {"success": False, "message": "Path is not a directory."}

        try:
            items = []
            # List only directories
            for entry in os.scandir(path):
                try:
                    if entry.is_dir() and not entry.name.startswith("."):
                        items.append({"name": entry.name, "path": entry.path})
                except Exception:
                    pass
            
            # Sort by name
            items.sort(key=lambda x: x["name"].lower())
            
            # Parent directory path
            parent = os.path.dirname(path)
            if parent == path:
                parent = "root"

            return {
                "success": True,
                "current_path": path,
                "parent_path": parent,
                "directories": items
            }
        except PermissionError:
            return {"success": False, "message": "Permission denied reading this directory."}
        except Exception as e:
            return {"success": False, "message": f"Error reading directory: {str(e)}"}

    async def create_directory(self, parent_path: str, name: str):
        """
        Creates a new directory inside the parent path.
        """
        if not name or not name.strip():
            return {"success": False, "message": "Folder name cannot be empty."}
        
        # Resolve parent_path
        if parent_path.startswith("~"):
            home = os.path.expanduser("~")
            parent_path = parent_path.replace("~", home, 1)
        parent_path = os.path.abspath(parent_path)

        path = os.path.join(parent_path, name.strip())
        try:
            os.makedirs(path, exist_ok=True)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "message": f"Failed to create folder: {str(e)}"}

    # Asyncio-compatible long-running code, executed in a task when the plugin is loaded
    async def _main(self):
        decky.logger.info("Decky Torrent plugin initialized!")

    # Function called first during the unload process
    async def _unload(self):
        decky.logger.info("Decky Torrent plugin unloaded!")

    # Function called after `_unload` during uninstall
    async def _uninstall(self):
        decky.logger.info("Decky Torrent plugin uninstalled! Cleaning up container...")
        await self._run_command(["podman", "stop", "decky-torrent"])
        await self._run_command(["podman", "rm", "decky-torrent"])

    # Migrations that should be performed before entering `_main()`.
    async def _migration(self):
        decky.logger.info("Migrating Decky Torrent settings")
        decky.migrate_logs(os.path.join(decky.DECKY_USER_HOME,
                                                ".config", "decky-torrent", "torrent.log"))
        decky.migrate_settings(
            os.path.join(decky.DECKY_HOME, "settings", "torrent.json"),
            os.path.join(decky.DECKY_USER_HOME, ".config", "decky-torrent"))
