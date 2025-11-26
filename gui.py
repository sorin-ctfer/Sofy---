import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import shutil
import threading
from .utils import generate_token, get_local_ip

# --- Anime/Cute Theme Configuration ---
THEME = {
    "bg_main": "#FFF0F5",       # Lavender Blush
    "bg_sidebar": "#FFE4E1",    # Misty Rose
    "bg_chat": "#FFFFFF",       # White
    "bg_input": "#F0F8FF",      # Alice Blue
    "accent": "#FFB7B2",        # Melon
    "button": "#FFDAC1",        # Peach
    "button_hover": "#FF9AA2",  # Salmon
    "text": "#555555",          # Dim Gray
    "highlight": "#B5EAD7",     # Magic Mint
    "self_msg": "#E2F0CB",      # Tea Green
    "peer_msg": "#F5F5F5"       # White Smoke
}

FONT_MAIN = ("Segoe UI Emoji", 10)
FONT_BOLD = ("Segoe UI Emoji", 10, "bold")
FONT_TITLE = ("Segoe UI Emoji", 12, "bold")
FONT_BIG = ("Segoe UI Emoji", 16, "bold")

class SofyGUI:
    def __init__(self, manager):
        self.manager = manager
        self.root = tk.Tk()
        self.root.title("Sofy (｡♥‿♥｡) - Connected")
        self.root.geometry("1000x650")
        self.root.configure(bg=THEME["bg_main"])
        
        # Inject callback
        self.manager.callback = self.on_event
        
        self.chat_history = {} # Key: "type:name", Value: list of strings
        self.selected_target = None # "User:name" or "Group:name"
        
        self.setup_styles()
        self.create_layout()
        
        # Start periodic updates
        self.root.after(1000, self.periodic_update)

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Frames
        self.style.configure("Main.TFrame", background=THEME["bg_main"])
        self.style.configure("Sidebar.TFrame", background=THEME["bg_sidebar"])
        self.style.configure("Chat.TFrame", background=THEME["bg_chat"])
        
        # Labels
        self.style.configure("TLabel", background=THEME["bg_main"], foreground=THEME["text"], font=FONT_MAIN)
        self.style.configure("Sidebar.TLabel", background=THEME["bg_sidebar"], foreground=THEME["text"], font=FONT_MAIN)
        self.style.configure("Title.TLabel", background=THEME["bg_sidebar"], foreground="#FF69B4", font=FONT_TITLE)
        self.style.configure("Header.TLabel", background=THEME["bg_chat"], foreground="#FF69B4", font=FONT_BIG)
        
        # Buttons
        self.style.configure("TButton", background=THEME["button"], foreground=THEME["text"], font=FONT_BOLD, borderwidth=0)
        self.style.map("TButton", background=[('active', THEME["button_hover"]), ('pressed', THEME["accent"])])
        
        self.style.configure("Send.TButton", background=THEME["accent"], foreground="white", font=FONT_BOLD)
        
        # Treeview (Contact List)
        self.style.configure("Treeview", background="white", foreground=THEME["text"], fieldbackground="white", font=FONT_MAIN, rowheight=30)
        self.style.map("Treeview", background=[('selected', THEME["accent"])], foreground=[('selected', 'white')])
        self.style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})]) # Remove borders

    def create_layout(self):
        # Main Container (Horizontal Split)
        # Left: Sidebar (Contacts)
        # Middle: Chat Area
        # Right: (Dynamic) Group Members / File Info
        
        # 1. Sidebar
        self.sidebar = ttk.Frame(self.root, width=250, style="Sidebar.TFrame")
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False) # Fixed width
        
        self.build_sidebar()
        
        # 2. Main Content Area
        self.content_area = ttk.Frame(self.root, style="Chat.TFrame")
        self.content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Default Welcome Screen
        self.welcome_frame = ttk.Frame(self.content_area, style="Chat.TFrame")
        self.welcome_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        ttk.Label(self.welcome_frame, text="(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧", font=("Segoe UI Emoji", 40), background=THEME["bg_chat"]).pack()
        ttk.Label(self.welcome_frame, text="Select a contact to start chatting!", font=FONT_TITLE, background=THEME["bg_chat"]).pack(pady=10)

        # Chat Frame (Hidden initially)
        self.chat_frame = ttk.Frame(self.content_area, style="Chat.TFrame")
        
        # Chat Header
        self.chat_header = ttk.Frame(self.chat_frame, height=50, style="Chat.TFrame")
        self.chat_header.pack(fill=tk.X, padx=20, pady=10)
        self.lbl_chat_title = ttk.Label(self.chat_header, text="", style="Header.TLabel")
        self.lbl_chat_title.pack(side=tk.LEFT)
        self.lbl_chat_subtitle = ttk.Label(self.chat_header, text="", font=FONT_MAIN, background=THEME["bg_chat"], foreground="#888")
        self.lbl_chat_subtitle.pack(side=tk.LEFT, padx=10, pady=(10,0))
        
        # Chat History
        self.txt_history = tk.Text(self.chat_frame, bg=THEME["bg_chat"], fg=THEME["text"], 
                                   font=FONT_MAIN, relief="flat", state="disabled", padx=10, pady=10)
        self.txt_history.pack(fill=tk.BOTH, expand=True, padx=20)
        self.txt_history.tag_config("me", foreground="#FF69B4", justify="right") # Pink for me
        self.txt_history.tag_config("peer", foreground="#555555", justify="left")
        self.txt_history.tag_config("sys", foreground="#888888", justify="center", font=("Segoe UI Emoji", 9, "italic"))
        
        # Input Area
        self.input_frame = ttk.Frame(self.chat_frame, height=100, style="Main.TFrame", padding=10)
        self.input_frame.pack(fill=tk.X)
        
        # Toolbar (File, Emoji, etc.)
        self.toolbar = ttk.Frame(self.input_frame, style="Main.TFrame")
        self.toolbar.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(self.toolbar, text="📁 File", command=self.do_send_file, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.toolbar, text="📂 Open Folder", command=self.do_open_folder, width=12).pack(side=tk.LEFT, padx=2)
        
        self.ent_msg = tk.Text(self.input_frame, height=3, font=FONT_MAIN, relief="flat", bg="white")
        self.ent_msg.pack(fill=tk.X, pady=5)
        self.ent_msg.bind("<Return>", self.on_enter_press)
        
        btn_send = ttk.Button(self.input_frame, text="Send (Run)", style="Send.TButton", command=self.do_send_msg)
        btn_send.pack(side=tk.RIGHT, pady=5)

        # 3. Right Sidebar (Group Members) - Only for groups
        self.member_sidebar = ttk.Frame(self.root, width=200, style="Sidebar.TFrame")
        # Packed dynamically

        self.lst_members = tk.Listbox(self.member_sidebar, bg=THEME["bg_sidebar"], relief="flat", font=FONT_MAIN, selectbackground=THEME["accent"])
        self.lst_members.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.lst_members.bind("<Double-Button-1>", self.on_member_double_click)
        self.lst_members.bind("<Button-3>", self.on_member_right_click)

    def build_sidebar(self):
        # User Info
        info_frame = ttk.Frame(self.sidebar, padding=15, style="Sidebar.TFrame")
        info_frame.pack(fill=tk.X)
        
        # Avatar (Placeholder)
        ttk.Label(info_frame, text="🐱", font=("Segoe UI Emoji", 30), style="Sidebar.TLabel").pack()
        ttk.Label(info_frame, text=self.manager.username, font=FONT_TITLE, style="Sidebar.TLabel").pack()
        ttk.Label(info_frame, text=f"IP: {get_local_ip()} | Port: {self.manager.port}", font=("Segoe UI Emoji", 8), style="Sidebar.TLabel").pack()
        
        # Buttons
        btn_frame = ttk.Frame(self.sidebar, style="Sidebar.TFrame", padding=5)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="➕ Connect", command=self.show_connect_dialog).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="✨ Create Group", command=self.show_create_group_dialog).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="🎫 My Token", command=self.show_my_token).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="🛠️ Gen Token", command=self.show_gen_token_dialog).pack(fill=tk.X, pady=2)
        
        # Contact List (Treeview)
        ttk.Label(self.sidebar, text="  CONTACTS", font=FONT_BOLD, style="Sidebar.TLabel").pack(anchor=tk.W, pady=(10, 5))
        
        self.tree = ttk.Treeview(self.sidebar, show="tree", selectmode="browse")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.on_contact_select)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        
        # Categories
        self.tree.insert("", "end", "cat_friends", text="Friends (Direct)", open=True)
        self.tree.insert("", "end", "cat_groups", text="Groups", open=True)

    # --- Actions ---

    def show_connect_dialog(self):
        token = simpledialog.askstring("Connect", "Enter Peer or Group Token:")
        if token:
            self.manager.connect_to_peer(token)
            messagebox.showinfo("Sofy", "Connection request sent! 🚀")

    def show_create_group_dialog(self):
        name = simpledialog.askstring("Create Group", "Enter Group Name:")
        if name:
            token = self.manager.create_group(name)
            self.show_token_window(f"Group: {name}", token)
            self.update_contacts()

    def show_my_token(self):
        ip = get_local_ip()
        token = generate_token(ip, self.manager.port, self.manager.username, self.manager.password)
        self.show_token_window("My Token", token)

    def show_gen_token_dialog(self):
        # Dialog to input IP, Port, User, Pass
        win = tk.Toplevel(self.root)
        win.title("Generate Token")
        win.geometry("300x350")
        win.configure(bg=THEME["bg_main"])
        
        ttk.Label(win, text="Generate Token", font=FONT_BOLD, background=THEME["bg_main"]).pack(pady=10)
        
        def entry(lbl, def_val=""):
            f = ttk.Frame(win, style="Main.TFrame")
            f.pack(fill=tk.X, padx=20, pady=2)
            ttk.Label(f, text=lbl, width=10, background=THEME["bg_main"]).pack(side=tk.LEFT)
            e = ttk.Entry(f)
            e.pack(side=tk.RIGHT, expand=True, fill=tk.X)
            if def_val: e.insert(0, str(def_val))
            return e
            
        e_ip = entry("IP:", get_local_ip())
        e_port = entry("Port:", self.manager.port)
        e_user = entry("User:", "user")
        e_pass = entry("Pass:", "123456")
        
        def do_gen():
            try:
                ip = e_ip.get()
                port = int(e_port.get())
                user = e_user.get()
                pwd = e_pass.get()
                token = generate_token(ip, port, user, pwd)
                self.show_token_window("Generated Token", token)
                win.destroy()
            except ValueError:
                messagebox.showerror("Error", "Port must be a number")
                
        ttk.Button(win, text="Generate", command=do_gen).pack(pady=20)

    def show_token_window(self, title, token):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry("400x200")
        win.configure(bg=THEME["bg_main"])
        
        ttk.Label(win, text=f"Here is the token for {title}:", background=THEME["bg_main"]).pack(pady=10)
        
        txt = tk.Text(win, height=4, width=40, font=("Consolas", 9))
        txt.pack(padx=20, pady=5)
        txt.insert("1.0", token)
        txt.config(state="disabled")
        
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=10)

    def update_contacts(self):
        # Clear existing
        self.tree.delete(*self.tree.get_children("cat_friends"))
        self.tree.delete(*self.tree.get_children("cat_groups"))
        
        # Friends
        for conn in self.manager.connections:
            if conn.is_alive() and not conn.group_name and conn.peer_username:
                # Check if selected to keep selection? (Simplification: just redraw)
                iid = f"User:{conn.peer_username}"
                text = f"👤 {conn.peer_username}"
                if not self.tree.exists(iid):
                    self.tree.insert("cat_friends", "end", iid, text=text)
        
        # Groups
        all_groups = set(list(self.manager.groups.keys()) + list(self.manager.joined_groups.keys()))
        for g in all_groups:
            iid = f"Group:{g}"
            role = "👑" if self.manager.is_group_host(g) else "🛡️"
            text = f"{role} {g}"
            if not self.tree.exists(iid):
                self.tree.insert("cat_groups", "end", iid, text=text)

    def on_contact_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        
        item = sel[0]
        if ":" not in item: return # Category selected
        
        type_, name = item.split(":", 1)
        self.selected_target = item
        
        # Update UI
        self.welcome_frame.place_forget()
        self.chat_frame.pack(fill=tk.BOTH, expand=True)
        
        self.lbl_chat_title.config(text=name)
        self.lbl_chat_subtitle.config(text=type_)
        
        # Show/Hide Member List
        if type_ == "Group":
            self.member_sidebar.pack(side=tk.RIGHT, fill=tk.Y)
            self.update_member_list(name)
        else:
            self.member_sidebar.pack_forget()
            
        self.refresh_chat_history()

    def update_member_list(self, group_name):
        self.lst_members.delete(0, tk.END)
        members = self.manager.get_group_members(group_name)
        for m in members:
            # Maybe mark host?
            display = m
            host = self.manager.get_group_host_name(group_name)
            if m == host:
                display += " (Host)"
            self.lst_members.insert(tk.END, display)

    def on_member_double_click(self, event):
        # Connect to member P2P
        sel = self.lst_members.curselection()
        if not sel: return
        val = self.lst_members.get(sel[0])
        username = val.split(" (")[0]
        
        if username == self.manager.username: return
        
        # Try to connect
        if "Group:" in self.selected_target:
            group_name = self.selected_target.split(":")[1]
            if messagebox.askyesno("Connect", f"Connect to {username}?"):
                self.manager.connect_to_group_peer(group_name, username)

    def on_tree_right_click(self, event):
        item = self.tree.identify('item', event.x, event.y)
        if not item: return
        
        self.tree.selection_set(item)
        if "Group:" in item:
            group_name = item.split(":")[1]
            m = tk.Menu(self.root, tearoff=0)
            m.add_command(label="View Token", command=lambda: self.do_view_group_token(group_name))
            m.tk_popup(event.x_root, event.y_root)
            m.grab_release()

    def do_view_group_token(self, group_name):
        token = self.manager.get_group_token(group_name)
        self.show_token_window(f"Group: {group_name}", token)

    def on_member_right_click(self, event):
        # Menu: Connect, Chat
        try:
            self.lst_members.selection_clear(0, tk.END)
            self.lst_members.selection_set(self.lst_members.nearest(event.y))
            self.lst_members.activate(self.lst_members.nearest(event.y))
            
            sel = self.lst_members.curselection()
            if not sel: return
            val = self.lst_members.get(sel[0])
            username = val.split(" (")[0]
            
            if username == self.manager.username: return
            
            m = tk.Menu(self.root, tearoff=0)
            m.add_command(label=f"Connect to {username}", command=lambda: self.do_connect_member(username))
            m.add_command(label=f"Say Hi", command=lambda: self.do_say_hi(username))
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def do_connect_member(self, username):
        if "Group:" in self.selected_target:
            group_name = self.selected_target.split(":")[1]
            self.manager.connect_to_group_peer(group_name, username)

    def do_say_hi(self, username):
        # Just pre-fill input? Or switch chat if connected?
        # If connected, switch.
        conn = self.manager.get_p2p_connection(username)
        if conn:
            # Switch to P2P chat
            # Find in tree
            iid = f"User:{username}"
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
        else:
            # Not connected. Suggest connecting.
            if messagebox.askyesno("Not Connected", f"You are not connected to {username}. Connect now?"):
                self.do_connect_member(username)

    def refresh_chat_history(self):
        self.txt_history.config(state="normal")
        self.txt_history.delete("1.0", tk.END)
        
        if self.selected_target in self.chat_history:
            for item in self.chat_history[self.selected_target]:
                # Item: {"sender": str, "content": str, "type": "me"|"peer"|"sys"}
                sender = item["sender"]
                content = item["content"]
                tag = item["type"]
                
                self.txt_history.insert(tk.END, f"{sender}:\n", ("name", tag))
                self.txt_history.insert(tk.END, f"  {content}\n\n", ("msg", tag))
                
        self.txt_history.see(tk.END)
        self.txt_history.config(state="disabled")

    def add_log(self, target, sender, content, type_):
        if target not in self.chat_history:
            self.chat_history[target] = []
        self.chat_history[target].append({"sender": sender, "content": content, "type": type_})
        
        if self.selected_target == target:
            self.refresh_chat_history()

    def on_enter_press(self, event):
        self.do_send_msg()
        return "break" # Prevent newline

    def do_send_msg(self):
        if not self.selected_target: return
        msg = self.ent_msg.get("1.0", tk.END).strip()
        if not msg: return
        
        type_, name = self.selected_target.split(":", 1)
        
        if type_ == "User":
            conn = self.manager.get_connection(name)
            if conn:
                conn.send_chat(msg)
                self.add_log(self.selected_target, "Me", msg, "me")
            else:
                self.add_log(self.selected_target, "System", "User not connected", "sys")
                
        elif type_ == "Group":
            if self.manager.is_group_host(name):
                self.manager.broadcast_group_msg(name, msg, self.manager.username)
            elif name in self.manager.joined_groups:
                conn = self.manager.joined_groups[name]
                conn.send_group_chat(msg, self.manager.username)
            self.add_log(self.selected_target, "Me", msg, "me")
            
        self.ent_msg.delete("1.0", tk.END)

    def do_send_file(self):
        if not self.selected_target: return
        
        filepath = filedialog.askopenfilename()
        if not filepath: return
        
        filename = os.path.basename(filepath)
        type_, name = self.selected_target.split(":", 1)
        
        # Determine destination sync folder
        dest_folder = None
        if type_ == "User":
            dest_folder = self.manager.fm.get_peer_folder(name)
        elif type_ == "Group":
            dest_folder = self.manager.fm.get_group_folder(name)
            
        if dest_folder:
            try:
                shutil.copy(filepath, os.path.join(dest_folder, filename))
                self.add_log(self.selected_target, "System", f"Sent file: {filename}", "sys")
                messagebox.showinfo("File Sent", f"File '{filename}' copied to sync folder!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to send file: {e}")

    def do_open_folder(self):
        if not self.selected_target: return
        type_, name = self.selected_target.split(":", 1)
        
        folder = None
        if type_ == "User":
            folder = self.manager.fm.get_peer_folder(name)
        elif type_ == "Group":
            folder = self.manager.fm.get_group_folder(name)
            
        if folder and os.path.exists(folder):
            os.startfile(folder)
        else:
            messagebox.showerror("Error", "Folder not found.")

    def periodic_update(self):
        # Update contact list connectivity status if needed
        # We just redraw for simplicity or check if count changed
        self.update_contacts()
        if self.selected_target and "Group:" in self.selected_target:
             self.update_member_list(self.selected_target.split(":")[1])
             
        self.root.after(2000, self.periodic_update)

    def on_event(self, event_type, data):
        self.root.after(0, lambda: self._handle_event_safe(event_type, data))

    def _handle_event_safe(self, event_type, data):
        if event_type == "log":
            pass # Maybe status bar?
        elif event_type == "chat":
            sender = data['sender']
            content = data['content']
            target = f"User:{sender}"
            self.add_log(target, sender, content, "peer")
            
            # Auto-open if chatting
            if not self.selected_target:
                # Notify?
                pass
                
        elif event_type == "group_chat":
            group = data['group']
            sender = data['sender']
            content = data['content']
            target = f"Group:{group}"
            if sender != self.manager.username:
                self.add_log(target, sender, content, "peer")
            
        elif event_type == "error":
            # Optional: messagebox.showerror("Error", data.get('msg'))
            # Don't spam popups
            print(f"UI Error Event: {data.get('msg')}")

    def run(self):
        self.root.mainloop()
