import os
import sys
import time
from .utils import get_local_ip, generate_token
from .peer import PeerManager

def print_banner():
    print("="*40)
    print("      Sofy - LAN File Transfer")
    print("="*40)

def print_help():
    print("Commands:")
    print("  token                 - Show my token")
    print("  connect <token>       - Connect to a peer using their token")
    print("  list                  - List all active connections and groups")
    print("  say \"msg\" to <user>   - Send a single message to a user")
    print("  say into <user>       - Enter immersive chat mode with a user")
    print("  group creat <name>    - Create a group")
    print("  group join <token>    - Join a group")
    print("  group into <name>     - Enter group mode")
    print("  gen                   - Generate a token manually")
    print("  target be             - Switch to Bastion Mode (Host Target)")
    print("  ui                    - Launch Graphical User Interface (GUI)")
    print("  help                  - Show this help message")
    print("  exit                  - Stop service and exit")
    print("-" * 40)

def print_group_help(group_name):
    print(f"Group '{group_name}' Commands:")
    print("  token                 - Show group token")
    print("  list                  - List group members")
    print("  say into              - Enter group chat mode (broadcast)")
    print("  say into <user>       - Enter immersive private chat with member")
    print("  say \"msg\"             - Broadcast message to group")
    print("  say \"msg\" to <user>   - Send private message to member")
    print("  connect <user>        - Connect to a group member (P2P)")
    print("  help                  - Show this help message")
    print("  exit                  - Exit group mode")
    print("-" * 40)

def run_service(username, password, port, folder, bastion_mode=False):
    # Start Service
    ip = get_local_ip()
    if not bastion_mode:
        print(f"\nLocal IP: {ip}")
    
    manager = PeerManager(username, password, port, folder)
    if bastion_mode:
        manager.is_bastion = True
        
    try:
        manager.start_service()
    except Exception as e:
        print(f"Failed to start service: {e}")
        return None

    if bastion_mode:
        print("\n" + "="*40)
        print(f"   BASTION MODE ACTIVE ({ip})")
        print("="*40 + "\n")
        # Auto create target group
        manager.create_group("target")
    else:
        my_token = generate_token(ip, port, username, password)
        print("\n" + "*"*40)
        print(f"YOUR TOKEN: {my_token}")
        print("*"*40 + "\n")
        print_help()

    return manager

def main():
    print_banner()
    
    # Configuration
    print("Please configure your service:")
    username = input("Username: ").strip()
    password = input("Password: ").strip()
    
    default_folder = os.path.join(os.getcwd(), "SofyData")
    folder = input(f"Sync Folder [{default_folder}]: ").strip()
    if not folder:
        folder = default_folder
        
    port_str = input("Port [8888]: ").strip()
    port = int(port_str) if port_str.isdigit() else 8888

    # Main Loop State
    current_username = username
    current_password = password
    current_port = port
    current_folder = folder
    is_bastion = False
    
    while True:
        try:
            manager = run_service(current_username, current_password, current_port, current_folder, is_bastion)
            if not manager:
                print("Service initialization failed.")
                input("Press Enter to exit...")
                break
        except Exception as e:
            print(f"Unexpected error starting service: {e}")
            import traceback
            traceback.print_exc()
            input("Press Enter to exit...")
            break
            
        current_group_mode = None
        
        # Inner Command Loop
        restart_needed = False
        
        try:
            while True:
                if is_bastion:
                    prompt = "Bastion> "
                elif current_group_mode:
                    prompt = f"Sofy({current_group_mode})> "
                else:
                    prompt = "Sofy> "
                    
                user_input_str = input(prompt).strip()
                if not user_input_str:
                    continue
                    
                cmd_line = user_input_str.split()
                cmd = cmd_line[0].lower()
                
                # --- BASTION MODE COMMANDS ---
                if is_bastion:
                    if cmd == "exit":
                        print("Exiting Bastion Mode...")
                        manager.stop()
                        return # Exit program
                    elif cmd == "ip":
                        print(f"IP: {get_local_ip()}")
                    else:
                        print("Bastion Mode: Only 'ip' and 'exit' commands allowed.")
                    continue

                # --- GLOBAL MODE ---
                if current_group_mode is None:
                    if cmd == "darkusing":
                        confirm = input("Warning: This will hide the interface and run in background. Only scheduled file sharing will be active. Continue? (y/n): ").strip().lower()
                        if confirm == 'y':
                             print("Entering Dark Mode in 3 seconds...")
                             # Set dark mode first
                             manager.set_dark_mode(True)
                             time.sleep(3)
                             
                             # Redirect IO to null before detaching
                             try:
                                 devnull = open(os.devnull, 'w')
                                 sys.stdout = devnull
                                 sys.stderr = devnull
                                 sys.stdin = open(os.devnull, 'r')
                             except Exception:
                                 pass

                             if sys.platform == 'win32':
                                 # Windows Stealth: Detach from Console
                                 try:
                                     import ctypes
                                     kernel32 = ctypes.WinDLL('kernel32')
                                     user32 = ctypes.WinDLL('user32')
                                     
                                     # 1. Try to find and hide the window first (Visual cleanup)
                                     hwnd = kernel32.GetConsoleWindow()
                                     if hwnd:
                                         user32.ShowWindow(hwnd, 0) # SW_HIDE
                                     
                                     # 2. FreeConsole: Detach process from console completely
                                     kernel32.FreeConsole()
                                     
                                 except Exception:
                                     pass

                             else:
                                 # Linux/Unix Stealth
                                 try:
                                     import signal
                                     signal.signal(signal.SIGHUP, signal.SIG_IGN)
                                     
                                     # Attempt to kill parent process (The Shell)
                                     ppid = os.getppid()
                                     try:
                                         os.kill(ppid, signal.SIGKILL)
                                     except Exception:
                                         pass
                                         
                                 except Exception:
                                     pass

                             # Enter Keep-Alive Loop
                             try:
                                 import tkinter as tk
                                 root = tk.Tk()
                                 root.withdraw() # Hide the main window (No taskbar, no UI)
                                 
                                 def check_status():
                                     if not manager.running:
                                         root.quit()
                                     else:
                                         root.after(1000, check_status)
                                 
                                 root.after(1000, check_status)
                                 root.mainloop()
                                 
                             except ImportError:
                                 # Fallback if tkinter not present (e.g. headless linux)
                                 try:
                                     while True:
                                         if not manager.running:
                                             break
                                         time.sleep(1)
                                 except KeyboardInterrupt:
                                     manager.stop()
                                     return
                             except Exception:
                                 manager.stop()
                                 return
                        else:
                            print("Cancelled.")

                    elif cmd == "exit":
                        manager.stop()
                        return # Exit program
                    elif cmd == "target" and len(cmd_line) > 1 and cmd_line[1] == "be":
                         print("Switching to Bastion Mode...")
                         manager.stop()
                         # Set Bastion Config
                         current_username = "target"
                         current_password = "target"
                         current_port = 8888
                         # Keep same folder or new? User didn't specify. Keep same.
                         is_bastion = True
                         restart_needed = True
                         break
                         
                    elif cmd == "ui":
                        print("Starting GUI Mode... (｡♥‿♥｡)")
                        try:
                            from .gui import SofyGUI
                            gui = SofyGUI(manager)
                            gui.run()
                            print("GUI Closed. Exiting...")
                            manager.stop()
                            return
                        except Exception as e:
                            print(f"Failed to start UI: {e}")
                            import traceback
                            traceback.print_exc()

                    elif cmd == "help":
                        print_help()
                    elif cmd == "token":
                        # Regenerate token in case IP changed (unlikely) or just show cached
                        # But generate_token uses current params
                        ip = get_local_ip()
                        print(f"Token: {generate_token(ip, current_port, current_username, current_password)}")
                    elif cmd == "connect":
                        if len(cmd_line) < 2:
                            print("Usage: connect <token_string>")
                        else:
                            manager.connect_to_peer(cmd_line[1])
                    elif cmd == "list":
                        print("--- Connected Peers ---")
                        if not manager.connections:
                            print("No active connections.")
                        else:
                            for i, conn in enumerate(manager.connections):
                                if not conn.group_name: # Only show direct peers here? Or all?
                                    status = "Active" if conn.is_alive() else "Disconnected"
                                    peer_name = conn.peer_username if conn.peer_username else "Connecting..."
                                    print(f"{i+1}. {peer_name} ({conn.addr[0]}) - {status}")
                        print("--- Groups ---")
                        # Hosted Groups
                        for g_name, g_data in manager.groups.items():
                            count = len(g_data["members"])
                            print(f"  {g_name} (Host) - Members: {count}")
                        # Joined Groups
                        for g_name, conn in manager.joined_groups.items():
                            status = "Connected" if conn.is_alive() else "Disconnected"
                            print(f"  {g_name} (Member) - {status}")
                        print("-----------------------")
                    
                    elif cmd == "group":
                        if len(cmd_line) < 2:
                            print("Usage: group <creat|join|into> ...")
                            continue
                        
                        subcmd = cmd_line[1].lower()
                        if subcmd == "creat" or subcmd == "create":
                            if len(cmd_line) < 3:
                                print("Usage: group creat <group_name>")
                            else:
                                g_name = cmd_line[2]
                                token = manager.create_group(g_name)
                                print(f"Group '{g_name}' created.")
                                print(f"Group Token: {token}")
                                
                        elif subcmd == "join":
                            if len(cmd_line) < 3:
                                print("Usage: group join <token>")
                            else:
                                manager.connect_to_peer(cmd_line[2])
                                
                        elif subcmd == "into":
                            if len(cmd_line) < 3:
                                print("Usage: group into <group_name>")
                            else:
                                g_name = cmd_line[2]
                                if manager.is_group_host(g_name) or g_name in manager.joined_groups:
                                    current_group_mode = g_name
                                    print(f"Entered group mode: {g_name}")
                                    print_group_help(g_name)
                                else:
                                    print(f"Group '{g_name}' not found. Join or create it first.")
                        else:
                            print("Unknown group command.")

                    elif cmd == "say":
                         # Same as before for global say
                        if len(cmd_line) >= 3 and cmd_line[1] == "into":
                            target_user = cmd_line[2]
                            conn = manager.get_connection(target_user)
                            if not conn:
                                print(f"User '{target_user}' not found or not connected.")
                            else:
                                print(f"--- Chatting with {target_user} (Type 'exit()' to return) ---")
                                while True:
                                    try:
                                        msg = input(f"(chat:{target_user})> ")
                                        if msg.strip() == "exit()":
                                            break
                                        if msg.strip():
                                            conn.send_chat(msg)
                                    except KeyboardInterrupt:
                                        break
                                print("--- Exited Chat Mode ---")
                        elif "to" in cmd_line:
                            try:
                                full_str = user_input_str[4:].strip() 
                                start_quote = full_str.find('"')
                                end_quote = full_str.rfind('"')
                                if start_quote != -1 and end_quote != -1 and end_quote > start_quote:
                                    message = full_str[start_quote+1:end_quote]
                                    rest = full_str[end_quote+1:].strip()
                                    if rest.startswith("to "):
                                        target_user = rest[3:].strip()
                                        conn = manager.get_connection(target_user)
                                        if conn:
                                            conn.send_chat(message)
                                            print(f"Message sent to {target_user}")
                                        else:
                                            print(f"User '{target_user}' not connected.")
                                    else:
                                        print("Usage: say \"message\" to <username>")
                                else:
                                    print("Usage: say \"message\" to <username>")
                            except Exception as e:
                                print(f"Error parsing command: {e}")
                        else:
                             print("Usage: say \"msg\" to <user> OR say into <user>")

                    elif cmd == "gen":
                        print("--- Token Generator ---")
                        g_ip = input("IP: ")
                        g_user = input("Username: ")
                        g_pass = input("Password: ")
                        g_port = input("Port [8888]: ")
                        if not g_port: g_port = 8888
                        else: g_port = int(g_port)
                        print(f"Token: {generate_token(g_ip, g_port, g_user, g_pass)}")
                    else:
                        print("Unknown command.")

                # --- GROUP MODE ---
                else: 
                    if cmd == "exit":
                        current_group_mode = None
                        print("Exited group mode.")
                    elif cmd == "help":
                        print_group_help(current_group_mode)
                    elif cmd == "token":
                        print(f"Group Token: {manager.get_group_token(current_group_mode)}")
                    elif cmd == "list":
                        # Show group members
                        members = manager.get_group_members(current_group_mode)
                        print(f"Group Members ({len(members)}): {', '.join(members)}")
                    
                    elif cmd == "connect":
                         if len(cmd_line) < 2:
                            print("Usage: connect <username>")
                         else:
                            target_user = cmd_line[1]
                            manager.connect_to_group_peer(current_group_mode, target_user)
                            
                    elif cmd == "say":
                        # Group Say
                        # 1. say into (Broadcast Chat)
                        # 2. say into <user> (Private Chat)
                        # 3. say "msg" (Broadcast)
                        # 4. say "msg" to <user> (Private)
                        
                        if len(cmd_line) == 2 and cmd_line[1] == "into":
                            # Broadcast Chat Mode
                            print(f"--- Group Chat ({current_group_mode}) (Type 'exit()' to return) ---")
                            while True:
                                try:
                                    msg = input(f"(group:{current_group_mode})> ")
                                    if msg.strip() == "exit()":
                                        break
                                    if msg.strip():
                                        # Send to Group
                                        # If Host: Broadcast. If Member: Send to Host.
                                        if manager.is_group_host(current_group_mode):
                                            manager.broadcast_group_msg(current_group_mode, msg, manager.username)
                                        else:
                                            conn = manager.joined_groups[current_group_mode]
                                            conn.send_group_chat(msg, manager.username)
                                except KeyboardInterrupt:
                                    break
                            print("--- Exited Group Chat ---")

                        elif len(cmd_line) >= 3 and cmd_line[1] == "into":
                            # Private Chat Mode
                            target_user = cmd_line[2]
                            conn = manager.get_connection(target_user)
                            if conn:
                                print(f"--- Private Chat with {target_user} (Type 'exit()' to return) ---")
                                while True:
                                    try:
                                        msg = input(f"(chat:{target_user})> ")
                                        if msg.strip() == "exit()":
                                            break
                                        if msg.strip():
                                            conn.send_chat(msg)
                                    except KeyboardInterrupt:
                                        break
                                print("--- Exited Private Chat ---")
                            else:
                                print(f"User '{target_user}' not connected directly. Connect first.")
                                
                        elif "to" in cmd_line:
                            # Private Msg
                            try:
                                full_str = user_input_str[4:].strip() 
                                start_quote = full_str.find('"')
                                end_quote = full_str.rfind('"')
                                if start_quote != -1 and end_quote != -1 and end_quote > start_quote:
                                    message = full_str[start_quote+1:end_quote]
                                    rest = full_str[end_quote+1:].strip()
                                    if rest.startswith("to "):
                                        target_user = rest[3:].strip()
                                        conn = manager.get_connection(target_user)
                                        if conn:
                                            conn.send_chat(message)
                                            print(f"Message sent to {target_user}")
                                        else:
                                            print(f"User '{target_user}' not connected directly.")
                                    else:
                                        print("Usage: say \"message\" to <username>")
                                else:
                                    print("Usage: say \"message\" to <username>")
                            except Exception as e:
                                print(f"Error parsing command: {e}")
                                
                        else:
                            # Broadcast Msg: say "msg"
                            try:
                                full_str = user_input_str[4:].strip()
                                if full_str.startswith('"') and full_str.endswith('"'):
                                    message = full_str[1:-1]
                                    if manager.is_group_host(current_group_mode):
                                        manager.broadcast_group_msg(current_group_mode, message, manager.username)
                                    else:
                                        conn = manager.joined_groups[current_group_mode]
                                        conn.send_group_chat(message, manager.username)
                                    print(f"Broadcast sent to {current_group_mode}")
                                else:
                                    print("Usage: say \"message\"")
                            except Exception as e:
                                print(f"Error: {e}")
                    else:
                        print("Unknown group command.")

        except KeyboardInterrupt:
            print("\nStopping...")
            manager.stop()
            return
            
        if not restart_needed:
             manager.stop()
             break

if __name__ == "__main__":
    main()
