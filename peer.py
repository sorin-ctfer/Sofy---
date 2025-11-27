import socket
import threading
import json
import struct
import time
import os
from .utils import parse_token, generate_group_token
from .file_manager import FileManager

# Protocol Constants
CMD_AUTH = "AUTH"
CMD_AUTH_OK = "AUTH_OK"
CMD_AUTH_FAIL = "AUTH_FAIL"
CMD_SYNC_LIST = "SYNC_LIST"
CMD_REQ_FILE = "REQ_FILE"
CMD_FILE_HEADER = "FILE_HEADER"
CMD_DELETE_FILE = "DELETE_FILE"
CMD_CHAT_MSG = "CHAT_MSG"
CMD_JOIN_GROUP = "JOIN_GROUP"
CMD_GROUP_MSG = "GROUP_MSG"
CMD_GROUP_MEMBERS = "GROUP_MEMBERS"
CMD_GROUP_MEMBER_UPDATE = "GROUP_MEMBER_UPDATE"
CMD_AUTH_GROUP_PEER = "AUTH_GROUP_PEER"
CMD_ERROR = "ERROR"

class PeerProtocol:
    """Handles low-level socket messaging."""
    
    @staticmethod
    def send_json(sock, data):
        json_bytes = json.dumps(data).encode('utf-8')
        # Send 4-byte length header + payload
        sock.sendall(struct.pack('>I', len(json_bytes)) + json_bytes)

    @staticmethod
    def recv_json(sock):
        # Read 4-byte length
        try:
            raw_len = PeerProtocol._recv_all(sock, 4)
        except socket.timeout:
            return None
            
        if not raw_len: return None
        msg_len = struct.unpack('>I', raw_len)[0]
        
        # Read payload
        # Once we have length, we must read the rest blocking/with loop, 
        # or we lose sync. Ideally temporary disable timeout or handle it.
        # For simplicity, we assume if header is there, payload follows fast.
        old_timeout = sock.gettimeout()
        sock.settimeout(None) # Blocking for payload
        try:
            payload = PeerProtocol._recv_all(sock, msg_len)
        finally:
            sock.settimeout(old_timeout)
            
        if not payload: return None
        return json.loads(payload.decode('utf-8'))

    @staticmethod
    def _recv_all(sock, n):
        data = b''
        while len(data) < n:
            try:
                packet = sock.recv(n - len(data))
                if not packet: return None
                data += packet
            except socket.timeout:
                # If we are in _recv_all called by recv_json's first read, 
                # we want to propagate up if no data read yet.
                # If we partially read, we should keep trying or error.
                # For header read (0 bytes so far), we want to return None/Raise to indicate no msg.
                if len(data) == 0: raise 
                # If we have partial data, we must wait.
                continue
        return data

    @staticmethod
    def send_file_content(sock, filepath):
        filesize = os.path.getsize(filepath)
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk: break
                sock.sendall(chunk)

    @staticmethod
    def recv_file_content(sock, dest_path, filesize):
        received = 0
        # This needs to be blocking
        old_timeout = sock.gettimeout()
        sock.settimeout(None)
        try:
            with open(dest_path, 'wb') as f:
                while received < filesize:
                    remaining = filesize - received
                    chunk_size = 4096 if remaining > 4096 else remaining
                    chunk = sock.recv(chunk_size)
                    if not chunk: raise ConnectionError("Connection lost during file transfer")
                    f.write(chunk)
                    received += len(chunk)
        finally:
            sock.settimeout(old_timeout)

class PeerConnection(threading.Thread):
    def __init__(self, sock, addr, manager, local_user, local_pass, is_initiator=False, target_token_pass=None, group_name=None):
        super().__init__()
        self.sock = sock
        self.addr = addr
        self.manager = manager
        self.fm = manager.fm
        self.local_user = local_user
        self.local_pass = local_pass 
        self.target_token_pass = target_token_pass
        self.is_initiator = is_initiator
        self.peer_username = None
        self.peer_port = None # The listening port of the peer
        self.group_name = group_name # If set, this connection is for a specific group
        self.running = True
        self.daemon = True
        self.dark_mode = False # Dark mode flag
        self.last_local_files = set() # Track for deletion

    def run(self):
        try:
            if not self.handshake():
                print(f"Handshake failed with {self.addr}")
                self.close()
                return
            
            # Initial scan
            my_folder = self.get_sync_folder()
            if os.path.exists(my_folder):
                 self.last_local_files = set(os.listdir(my_folder))
            
            if self.group_name:
                print(f"Joined group '{self.group_name}' via {self.addr[0]}")
            else:
                print(f"Connected with {self.peer_username} ({self.addr[0]})")
            
            self.sock.settimeout(0.5)
            last_sync = 0
            
            while self.running:
                # 1. Periodic Sync & Deletion Check
                if time.time() - last_sync > 2.0:
                    try:
                        self.sync_step_and_check_delete()
                    except Exception as e:
                        # print(f"Error sending sync/delete: {e}")
                        pass # Ignore periodic errors to keep connection alive if possible
                    last_sync = time.time()
                
                # 2. Read incoming
                try:
                    msg = PeerProtocol.recv_json(self.sock)
                    if msg: self.handle_msg(msg)
                except socket.timeout:
                    continue
                except (ConnectionError, OSError):
                    break
                except Exception as e:
                    print(f"Error in loop: {e}")
                    break
                
        except Exception as e:
            print(f"Connection error with {self.peer_username}: {e}")
        finally:
            if self.group_name:
                print(f"Disconnected from group '{self.group_name}' ({self.addr[0]})")
                self.manager.unregister_group_member(self.group_name, self)
            else:
                print(f"Disconnected from {self.peer_username}")
            self.close()

    def get_sync_folder(self):
        if self.group_name:
            return self.fm.get_group_folder(self.group_name)
        return self.fm.get_peer_folder(self.peer_username)

    def handshake(self):
        # Blocking handshake
        self.sock.settimeout(None) 
        if self.is_initiator:
            # If joining a group
            if self.group_name:
                # Check auth method
                if self.target_token_pass == 'group_peer': # Special flag for connecting to peer within group
                     PeerProtocol.send_json(self.sock, {
                        "type": CMD_AUTH_GROUP_PEER,
                        "username": self.local_user,
                        "group_name": self.group_name
                    })
                else:
                    PeerProtocol.send_json(self.sock, {
                        "type": CMD_JOIN_GROUP,
                        "username": self.local_user,
                        "group_name": self.group_name,
                        "listen_port": self.manager.port
                    })
                
                resp = PeerProtocol.recv_json(self.sock)
                if resp and resp.get("type") == CMD_AUTH_OK:
                    self.peer_username = resp.get("username", "GroupPeer")
                    if self.target_token_pass == 'group_peer':
                        self.group_name = None # Treat as P2P connection after handshake
                    return True
                return False
            else:
                # Normal P2P
                PeerProtocol.send_json(self.sock, {
                    "type": CMD_AUTH,
                    "username": self.local_user,
                    "password": self.target_token_pass
                })
                resp = PeerProtocol.recv_json(self.sock)
                if resp and resp.get("type") == CMD_AUTH_OK:
                    self.peer_username = resp["username"]
                    return True
                return False
        else:
            # Responder
            req = PeerProtocol.recv_json(self.sock)
            if not req: return False
            
            if req.get("type") == CMD_JOIN_GROUP:
                g_name = req["group_name"]
                # Check if we host this group
                if self.manager.is_group_host(g_name):
                    self.group_name = g_name
                    self.peer_username = req["username"]
                    self.peer_port = req.get("listen_port") # Store their listening port
                    
                    # Send AUTH_OK first to ensure client handshake completes before any broadcast updates
                    PeerProtocol.send_json(self.sock, {
                        "type": CMD_AUTH_OK,
                        "username": self.local_user
                    })
                    
                    self.manager.register_group_member(g_name, self)
                    return True
                else:
                    PeerProtocol.send_json(self.sock, {"type": CMD_AUTH_FAIL, "msg": "Group not found"})
                    return False
            
            elif req.get("type") == CMD_AUTH_GROUP_PEER:
                 g_name = req["group_name"]
                 requester = req["username"]
                 # I am being connected to by a group peer.
                 # Check if I am in this group (Host or Member)
                 # And if the requester is also in the group.
                 # For simplicity, if I am in the group, I trust peers who know the group name?
                 # Better: Check if requester is in my known member list.
                 known_members = self.manager.get_group_members(g_name)
                 # Note: get_group_members returns names.
                 # If I am Host, I know everyone.
                 # If I am Member, I know what Host told me.
                 
                 if (self.manager.is_group_host(g_name) or g_name in self.manager.joined_groups) and \
                    (requester in known_members or requester == self.manager.get_group_host_name(g_name)): 
                     # Allow connection
                    
                    # Check for duplicates
                    existing = self.manager.get_p2p_connection(requester)
                    if existing and existing != self:
                         PeerProtocol.send_json(self.sock, {"type": CMD_AUTH_FAIL, "msg": "Already connected"})
                         return False

                    self.peer_username = requester
                    self.group_name = None # Treat as P2P connection, not Group Sync connection?
                    # Wait, user wants "connect <user>". This implies P2P.
                    # Does P2P imply private sync folder? Yes.
                    # So group_name should be None.
                    # But we used group_name to authenticate.
                    PeerProtocol.send_json(self.sock, {
                        "type": CMD_AUTH_OK,
                        "username": self.local_user
                    })
                    return True
                 else:
                    PeerProtocol.send_json(self.sock, {"type": CMD_AUTH_FAIL, "msg": "Not in group or unknown member"})
                    return False

            elif req.get("type") == CMD_AUTH:
                if req["password"] == self.local_pass:
                    # Check for duplicates
                    requester = req["username"]
                    existing = self.manager.get_p2p_connection(requester)
                    if existing and existing != self:
                         PeerProtocol.send_json(self.sock, {"type": CMD_AUTH_FAIL, "msg": "Already connected"})
                         return False

                    self.peer_username = req["username"]
                    PeerProtocol.send_json(self.sock, {
                        "type": CMD_AUTH_OK,
                        "username": self.local_user
                    })
                    return True
                else:
                    PeerProtocol.send_json(self.sock, {"type": CMD_AUTH_FAIL})
            return False

    def sync_step_and_check_delete(self):
        # 1. Get current state
        my_folder = self.get_sync_folder()
        my_files = self.fm.scan_folder(my_folder)
        current_filenames = set(my_files.keys())
        
        # 2. Check for deletions
        # Only report deletions if we have synced at least once (last_local_files is not empty)
        # Or if we know for sure it was there.
        # Issue: if last_local_files is populated from disk on startup, and file is deleted while running.
        
        # If last_local_files is empty (first run), we shouldn't detect deletions yet?
        # No, we populated it in run().
        
        deleted = self.last_local_files - current_filenames
        for fname in deleted:
            # Check if it was really deleted or just never there?
            # It was in last_local_files, so it was there.
            
            # Send DELETE command
            # print(f"Detected deletion: {fname}, telling peer.") # Detected loop logging
            PeerProtocol.send_json(self.sock, {
                "type": CMD_DELETE_FILE,
                "filename": fname
            })
            
        # 3. Update last known state
        self.last_local_files = current_filenames
        
        # 4. Send Sync List
        PeerProtocol.send_json(self.sock, {
            "type": CMD_SYNC_LIST,
            "files": my_files
        })

    def handle_msg(self, msg):
        msg_type = msg.get("type")
        
        # In Dark Mode, ignore chat and other non-file commands
        if self.dark_mode:
            allowed_types = [CMD_SYNC_LIST, CMD_REQ_FILE, CMD_FILE_HEADER, CMD_DELETE_FILE, CMD_AUTH, CMD_AUTH_OK, CMD_AUTH_FAIL]
            if msg_type not in allowed_types:
                return

        if msg_type == CMD_SYNC_LIST:
            my_folder = self.get_sync_folder()
            my_files = self.fm.scan_folder(my_folder)
            remote_files = msg["files"]
            
            # Resolve conflicts and identify zombie files
            to_download, to_delete_remotely = self.fm.resolve_conflicts(my_files, remote_files, my_folder)
            
            for fname in to_download:
                self.request_file(fname)
            
            for fname in to_delete_remotely:
                # Tell the peer to delete this zombie file
                PeerProtocol.send_json(self.sock, {
                    "type": CMD_DELETE_FILE,
                    "filename": fname
                })
        
        elif msg_type == CMD_DELETE_FILE:
            fname = msg["filename"]
            # print(f"Peer deleted file: {fname}") # Too noisy for groups?
            my_folder = self.get_sync_folder()
            if self.fm.delete_file(my_folder, fname):
                if fname in self.last_local_files:
                    self.last_local_files.remove(fname)
                
                # If we are Host, relay deletion to others?
                # If Member A tells Host "Delete X". Host deletes X.
                # Host's other connections will see X missing in next sync_step and send DELETE.
                # So Relay is implicit via File System state!
                # But that takes up to 2 seconds.
                # Ideally we relay immediately for speed, but FS sync is robust.
                # Let's rely on FS sync for now to avoid loops.
                
        elif msg_type == CMD_GROUP_MEMBER_UPDATE:
            group_name = msg["group_name"]
            members = msg["members"] # list of {username, ip, port}
            if group_name in self.manager.joined_groups:
                 # Update local member cache
                 self.manager.update_group_members_cache(group_name, members)
        
        elif msg_type == CMD_REQ_FILE:
            my_folder = self.get_sync_folder()
            self.handle_send_file(msg["filename"], my_folder)
            
        elif msg_type == CMD_FILE_HEADER:
            my_folder = self.get_sync_folder()
            self.handle_recv_file(msg, my_folder)
            
        elif msg_type == CMD_CHAT_MSG:
            content = msg['content']
            print(f"\n({self.peer_username}) says: {content}")
            
            # Emit to UI
            self.manager.emit("chat", {"sender": self.peer_username, "content": content})
            
            # Bastion Auto-Reply Logic
            if self.manager.is_bastion:
                 if "target" in self.manager.groups:
                     token = self.manager.groups["target"]["token"]
                     reply = f"Bastion Auto-Reply: Please join the target group. Token: {token}"
                     self.send_chat(reply)

        elif msg_type == CMD_GROUP_MSG:
            # Group Broadcast
            sender = msg.get("sender", self.peer_username)
            content = msg["content"]
            print(f"\n(Group) {sender}: {content}")
            
            # Emit to UI
            self.manager.emit("group_chat", {"group": self.group_name, "sender": sender, "content": content})
            
            # If I am Host, relay to others
            if self.manager.is_group_host(self.group_name):
                self.manager.broadcast_group_msg(self.group_name, content, sender, exclude_conn=self)

    def request_file(self, filename):
        PeerProtocol.send_json(self.sock, {
            "type": CMD_REQ_FILE,
            "filename": filename
        })

    def send_chat(self, message):
        PeerProtocol.send_json(self.sock, {
            "type": CMD_CHAT_MSG,
            "content": message
        })
    
    def send_group_chat(self, message, sender_name):
        PeerProtocol.send_json(self.sock, {
            "type": CMD_GROUP_MSG,
            "content": message,
            "sender": sender_name
        })

    def handle_send_file(self, filename, my_folder):
        filepath = os.path.join(my_folder, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            PeerProtocol.send_json(self.sock, {
                "type": CMD_FILE_HEADER,
                "filename": filename,
                "size": size
            })
            PeerProtocol.send_file_content(self.sock, filepath)

    def handle_recv_file(self, header_msg, my_folder):
        filename = header_msg["filename"]
        size = header_msg["size"]
        temp_path = self.fm.get_temp_path(my_folder, filename)
        PeerProtocol.recv_file_content(self.sock, temp_path, size)
        self.fm.finalize_file(my_folder, filename)

    def close(self):
        self.running = False
        try:
            self.sock.close()
        except:
            pass


class PeerManager:
    def __init__(self, username, password, port, root_dir):
        self.username = username
        self.password = password
        self.port = port
        self.fm = FileManager(root_dir)
        self.server_sock = None
        self.connections = []
        self.running = False
        
        # Group Management
        # groups I created (Host): { "group_name": { "members": [conn, ...], "token": "..." } }
        self.groups = {} 
        # groups I joined (Member): { "group_name": conn } (Connection to Host)
        self.joined_groups = {} 
        
        # Member Cache for joined groups: { "group_name": { "members": [...], "token": "...", "host": "..." } }
        self.group_cache = {} 
        
        # Bastion Mode Flag
        self.is_bastion = False
        
        self.dark_mode = False

        # UI Callback
        self.callback = None

    def set_dark_mode(self, enabled):
        self.dark_mode = enabled
        for conn in self.connections:
            conn.dark_mode = enabled

    def emit(self, event_type, data):
        if self.callback:
            self.callback(event_type, data)

    def start_service(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.bind(('0.0.0.0', self.port))
        self.server_sock.listen(5)
        self.running = True
        
        t = threading.Thread(target=self._listen_loop)
        t.daemon = True
        t.start()
        print(f"Service started on port {self.port}")

    def _listen_loop(self):
        while self.running:
            try:
                client_sock, addr = self.server_sock.accept()
                # Pass self (manager) instead of self.fm
                conn = PeerConnection(client_sock, addr, self, self.username, self.password)
                conn.dark_mode = self.dark_mode
                conn.start()
                self.connections.append(conn)
            except OSError:
                break

    def connect_to_peer(self, token_str):
        data = parse_token(token_str)
        if not data:
            print("Invalid token.")
            return

        target_ip = data.get("ip")
        target_port = data.get("port")
        token_type = data.get("type", "user") # Default to user if not present
        
        # Check duplicate by token's user (if available) or IP/Port?
        # Token for user has username inside?
        # parse_token returns dict.
        # User token: ip, port, username, password
        # Group token: ip, port, group_name
        
        if token_type == "user":
            target_user = data.get("username")
            if target_user and self.get_p2p_connection(target_user):
                print(f"Already connected to {target_user}.")
                return
        elif token_type == "group":
            group_name = data.get("group_name")
            if group_name in self.joined_groups and self.joined_groups[group_name].is_alive():
                 print(f"Already joined group {group_name}.")
                 return

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((target_ip, target_port))
            
            if token_type == "group":
                group_name = data["group_name"]
                print(f"Connecting to group '{group_name}' at {target_ip}...")
                conn = PeerConnection(sock, (target_ip, target_port), self, 
                                      self.username, self.password, 
                                      is_initiator=True, group_name=group_name)
                conn.start()
                self.connections.append(conn)
                self.joined_groups[group_name] = conn
                
            else:
                target_pass = data.get("password")
                print(f"Connecting to user at {target_ip}...")
                conn = PeerConnection(sock, (target_ip, target_port), self, 
                                      self.username, self.password, 
                                      is_initiator=True, target_token_pass=target_pass)
                conn.start()
                self.connections.append(conn)
                
        except Exception as e:
            print(f"Failed to connect: {e}")

    def connect_to_group_peer(self, group_name, target_username):
        if self.get_p2p_connection(target_username):
             print(f"Already connected to {target_username}.")
             return

        # Find target in group cache or local group members
        target_ip = None
        target_port = None
        
        # Check if I am Host
        if self.is_group_host(group_name):
            for conn in self.groups[group_name]["members"]:
                if conn.peer_username == target_username:
                    target_ip = conn.addr[0]
                    target_port = conn.peer_port
                    break
        # Check if I am Member (using cache)
        elif group_name in self.group_cache:
            for m in self.group_cache[group_name]["members"]:
                if m["username"] == target_username:
                    target_ip = m["ip"]
                    target_port = m["port"]
                    break
                    
        if not target_ip or not target_port:
            print(f"User {target_username} not found in group {group_name}")
            return

        if target_ip == "HOST": 
            if group_name in self.joined_groups:
                conn = self.joined_groups[group_name]
                target_ip = conn.addr[0]
            else:
                 print("Cannot resolve Host IP.")
                 return

        try:
            print(f"Connecting to {target_username} ({target_ip}:{target_port})...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((target_ip, target_port))
            
            # Special auth for group peer
            conn = PeerConnection(sock, (target_ip, target_port), self, 
                                  self.username, self.password, 
                                  is_initiator=True, target_token_pass='group_peer', group_name=group_name)
            conn.start()
            self.connections.append(conn)
            
        except Exception as e:
            print(f"Failed to connect to {target_username}: {e}")

    def get_connection(self, username):
        for conn in self.connections:
            if conn.peer_username == username and conn.is_alive():
                return conn
        return None

    def get_p2p_connection(self, username):
        for conn in self.connections:
            if conn.peer_username == username and conn.is_alive() and conn.group_name is None:
                return conn
        return None

    def create_group(self, group_name):
        if group_name in self.groups:
            return self.groups[group_name]["token"]
        
        # Generate token
        # Get my IP (we don't store it, we get it again or pass it)
        # utils.get_local_ip() is stateless.
        from .utils import get_local_ip
        my_ip = get_local_ip()
        token = generate_group_token(my_ip, self.port, group_name)
        
        # Create folder
        self.fm.get_group_folder(group_name)
        
        self.groups[group_name] = {
            "members": [],
            "token": token
        }
        return token

    def is_group_host(self, group_name):
        return group_name in self.groups

    def register_group_member(self, group_name, conn):
        if group_name in self.groups:
            if conn not in self.groups[group_name]["members"]:
                self.groups[group_name]["members"].append(conn)
                self.broadcast_member_update(group_name)

    def unregister_group_member(self, group_name, conn):
        if group_name in self.groups:
            if conn in self.groups[group_name]["members"]:
                self.groups[group_name]["members"].remove(conn)
                self.broadcast_member_update(group_name)

    def broadcast_group_msg(self, group_name, msg, sender_name, exclude_conn=None):
        if group_name in self.groups:
            members = self.groups[group_name]["members"]
            for conn in members:
                if conn != exclude_conn and conn.is_alive():
                    conn.send_group_chat(msg, sender_name)
    
    def broadcast_member_update(self, group_name):
        if group_name not in self.groups: return
        
        # Collect member info
        members_info = []
        # Add Host (Me)
        members_info.append({
            "username": self.username,
            "ip": "HOST", 
            "port": self.port,
            "is_host": True
        })
        
        for conn in self.groups[group_name]["members"]:
            if conn.peer_username:
                members_info.append({
                    "username": conn.peer_username,
                    "ip": conn.addr[0],
                    "port": conn.peer_port or 0,
                    "is_host": False
                })
        
        msg = {
            "type": CMD_GROUP_MEMBER_UPDATE,
            "group_name": group_name,
            "members": members_info
        }
        
        for conn in self.groups[group_name]["members"]:
            if conn.is_alive():
                PeerProtocol.send_json(conn.sock, msg)

    def update_group_members_cache(self, group_name, members):
        if group_name not in self.group_cache:
            self.group_cache[group_name] = {}
        self.group_cache[group_name]["members"] = members
        for m in members:
            if m.get("is_host"):
                self.group_cache[group_name]["host"] = m["username"]

    def get_group_members(self, group_name):
        if group_name in self.groups:
            return [self.username] + [c.peer_username for c in self.groups[group_name]["members"] if c.peer_username]
        elif group_name in self.group_cache:
            return [m["username"] for m in self.group_cache[group_name]["members"]]
        return []

    def get_group_host_name(self, group_name):
        if group_name in self.groups:
            return self.username
        if group_name in self.group_cache:
            return self.group_cache[group_name].get("host")
        return None

    def get_group_token(self, group_name):
        if group_name in self.groups:
            return self.groups[group_name]["token"]
        if group_name in self.joined_groups:
            conn = self.joined_groups[group_name]
            host_ip = conn.addr[0]
            host_port = conn.addr[1]
            from .utils import generate_group_token
            return generate_group_token(host_ip, host_port, group_name)
        return "Token not available"

    def stop(self):
        self.running = False
        if self.server_sock:
            self.server_sock.close()
        for c in self.connections:
            c.close()
