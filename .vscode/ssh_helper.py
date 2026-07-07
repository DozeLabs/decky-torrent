#!/usr/bin/env python3
import os
import sys
import json
import re
import pty
import select
import shlex
import time

def expand_variables(text, settings):
    # Parent of the script directory is the workspace folder
    workspace_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = text.replace('${workspaceFolder}', workspace_folder)
    
    # Expand ${env:VAR}
    text = re.sub(r'\$\{env:([^}]+)\}', lambda m: os.environ.get(m.group(1), ''), text)
    
    # Expand ${config:VAR}
    text = re.sub(r'\$\{config:([^}]+)\}', lambda m: settings.get(m.group(1), ''), text)
    
    return text

def load_settings():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, 'settings.json')
    if not os.path.exists(settings_path):
        print(f"Error: {settings_path} not found.")
        sys.exit(1)
    with open(settings_path, 'r') as f:
        # Strip comments manually to avoid JSON parsing issues if comments exist
        content = ""
        for line in f:
            line_content = line.split('//')[0].strip()
            if line_content:
                content += line_content
        settings = json.loads(content)
        
        # Expand variables inside all string values in settings
        expanded_settings = {}
        for k, v in settings.items():
            if isinstance(v, str):
                expanded_settings[k] = expand_variables(v, settings)
            else:
                expanded_settings[k] = v
        return expanded_settings

def run_command_with_password(cmd, password):
    print(f"Running: {' '.join(cmd)}")
    pid, fd = pty.fork()
    if pid == 0:
        # Child process
        try:
            os.execvp(cmd[0], cmd)
        except Exception as e:
            sys.stderr.write(f"Failed to execute {cmd[0]}: {e}\n")
            sys.exit(1)
    else:
        # Parent process
        password_sent = False
        host_key_accepted = False
        output_buffer = b""
        
        while True:
            try:
                r, w, x = select.select([fd], [], [], 1.0)
                if fd in r:
                    data = os.read(fd, 4096)
                    if not data:
                        break
                    # Forward child's output to stdout
                    sys.stdout.buffer.write(data)
                    sys.stdout.flush()
                    
                    output_buffer += data
                    
                    # Check for SSH host key confirmation prompt
                    if not host_key_accepted and any(x in output_buffer.lower() for x in [b"are you sure you want to continue connecting", b"authenticity of host"]):
                        os.write(fd, b"yes\n")
                        host_key_accepted = True
                        output_buffer = b""
                        
                    # Check for password prompt
                    if not password_sent and (b"password:" in output_buffer.lower() or b"password for" in output_buffer.lower() or output_buffer.lower().endswith(b"password: ")):
                        # Small delay to ensure the password input stream is ready
                        time.sleep(0.1)
                        os.write(fd, (password + "\n").encode())
                        password_sent = True
                        output_buffer = b""
            except OSError:
                break
        
        _, status = os.waitpid(pid, 0)
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        return -1

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 ssh_helper.py [copyzip|extractzip|chmodplugins|restartdecky]")
        sys.exit(1)
        
    action = sys.argv[1]
    settings = load_settings()
    
    deckip = settings.get('deckip')
    deckport = settings.get('deckport', '22')
    deckuser = settings.get('deckuser', 'deck')
    deckpass = settings.get('deckpass', '')
    deckkey = settings.get('deckkey', '').strip()
    deckdir = settings.get('deckdir', '/home/deck')
    pluginname = settings.get('pluginname')
    
    if not deckip or not pluginname:
        print("Error: deckip and pluginname must be specified in settings.json")
        sys.exit(1)
        
    key_args = shlex.split(deckkey) if deckkey else []
    
    if action == 'copyzip':
        cmd = ['scp', '-P', deckport] + key_args + [
            f"out/{pluginname}.zip",
            f"{deckuser}@{deckip}:{deckdir}/homebrew/plugins/"
        ]
    elif action == 'extractzip':
        remote_cmd = f"rm -rf '{deckdir}/homebrew/plugins/{pluginname}' && python3 -c \"import zipfile; zipfile.ZipFile('{deckdir}/homebrew/plugins/{pluginname}.zip').extractall('{deckdir}/homebrew/plugins/')\""
        cmd = ['ssh', f"{deckuser}@{deckip}", '-p', deckport] + key_args + [remote_cmd]
    elif action == 'chmodplugins':
        remote_cmd = f"echo '{deckpass}' | sudo -S chown {deckuser} {deckdir}/homebrew/plugins/"
        cmd = ['ssh', f"{deckuser}@{deckip}", '-p', deckport] + key_args + [remote_cmd]
    elif action == 'restartdecky':
        remote_cmd = f"echo '{deckpass}' | sudo -S systemctl restart plugin_loader"
        cmd = ['ssh', f"{deckuser}@{deckip}", '-p', deckport] + key_args + [remote_cmd]
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
        
    exit_code = run_command_with_password(cmd, deckpass)
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
