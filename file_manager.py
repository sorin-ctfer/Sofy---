import os
import time
import json

class FileManager:
    def __init__(self, root_path):
        self.root_path = os.path.abspath(root_path)
        if not os.path.exists(self.root_path):
            os.makedirs(self.root_path)
        
        self.tombstones_file = os.path.join(self.root_path, ".tombstones")
        self.tombstones = self._load_tombstones()

    def _load_tombstones(self):
        if os.path.exists(self.tombstones_file):
            try:
                with open(self.tombstones_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_tombstones(self):
        try:
            with open(self.tombstones_file, 'w') as f:
                json.dump(self.tombstones, f)
        except:
            pass

    def _add_tombstone(self, rel_path):
        self.tombstones[rel_path] = time.time()
        self._save_tombstones()

    def get_rel_path(self, full_path):
        return os.path.relpath(full_path, self.root_path).replace("\\", "/")

    def get_peer_folder(self, peer_username):
        """Gets (and creates if needed) the folder for a specific peer."""
        path = os.path.join(self.root_path, peer_username)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def get_group_folder(self, group_name):
        """Gets (and creates if needed) the folder for a specific group."""
        path = os.path.join(self.root_path, group_name)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def scan_folder(self, folder_path):
        """
        Scans a folder and returns metadata for all files.
        Ignores temporary .sofy files and .tombstones.
        """
        metadata = {}
        if not os.path.exists(folder_path):
            return metadata

        for filename in os.listdir(folder_path):
            if filename.endswith('.sofy') or filename == ".tombstones":
                continue
            
            filepath = os.path.join(folder_path, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                metadata[filename] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size
                }
        return metadata

    def resolve_conflicts(self, local_meta, remote_meta, folder_path):
        """
        Determines which files need to be downloaded from the remote peer.
        Also detects files that should be deleted on remote (Zombie files).
        
        Returns:
            to_download: list of filenames to request
            to_delete_remotely: list of filenames the remote should delete
        """
        to_download = []
        to_delete_remotely = []
        
        # Calculate relative prefix for this folder to look up tombstones
        # folder_path is like E:/.../SofyData/groupA
        # root_path is E:/.../SofyData
        # prefix is groupA/
        rel_prefix = self.get_rel_path(folder_path)
        
        for filename, r_data in remote_meta.items():
            rel_file_path = f"{rel_prefix}/{filename}"
            
            if filename not in local_meta:
                # File exists remotely but not locally
                
                # Check Tombstone
                if rel_file_path in self.tombstones:
                    ts_time = self.tombstones[rel_file_path]
                    # If remote file is older than deletion time, it's a zombie
                    if r_data['mtime'] < ts_time:
                        to_delete_remotely.append(filename)
                        continue
                    # If remote file is newer, it was re-created, so we download it.
                
                to_download.append(filename)
            else:
                l_data = local_meta[filename]
                # File exists in both, check timestamp
                # If remote is significantly newer (e.g., > 1 second difference)
                if r_data['mtime'] > l_data['mtime'] + 1.0:
                     to_download.append(filename)
        
        return to_download, to_delete_remotely

    def get_temp_path(self, folder_path, filename):
        return os.path.join(folder_path, filename + ".sofy")

    def get_final_path(self, folder_path, filename):
        return os.path.join(folder_path, filename)

    def finalize_file(self, folder_path, filename):
        """Renames .sofy file to the actual filename."""
        temp = self.get_temp_path(folder_path, filename)
        final = self.get_final_path(folder_path, filename)
        if os.path.exists(final):
            try:
                os.remove(final)
            except OSError:
                pass # Might be open or issue, but we try
        if os.path.exists(temp):
            os.rename(temp, final)

    def delete_file(self, folder_path, filename):
        """Deletes a file if it exists and records tombstone."""
        path = self.get_final_path(folder_path, filename)
        
        # Record tombstone even if file doesn't exist (it might be already gone but we want to remember)
        rel_path = f"{self.get_rel_path(folder_path)}/{filename}"
        self._add_tombstone(rel_path)
        
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except OSError:
                return False
        return False
