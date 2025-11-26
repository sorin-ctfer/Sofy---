import os
import time

class FileManager:
    def __init__(self, root_path):
        self.root_path = os.path.abspath(root_path)
        if not os.path.exists(self.root_path):
            os.makedirs(self.root_path)

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
        Ignores temporary .sofy files.
        """
        metadata = {}
        if not os.path.exists(folder_path):
            return metadata

        for filename in os.listdir(folder_path):
            if filename.endswith('.sofy'):
                continue
            
            filepath = os.path.join(folder_path, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                metadata[filename] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size
                }
        return metadata

    def resolve_conflicts(self, local_meta, remote_meta):
        """
        Determines which files need to be downloaded from the remote peer.
        Returns a list of filenames to request.
        """
        to_download = []
        
        for filename, r_data in remote_meta.items():
            if filename not in local_meta:
                # File exists remotely but not locally -> Download
                to_download.append(filename)
            else:
                l_data = local_meta[filename]
                # File exists in both, check timestamp
                # If remote is significantly newer (e.g., > 1 second difference)
                if r_data['mtime'] > l_data['mtime'] + 1.0:
                     to_download.append(filename)
        
        return to_download

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
        """Deletes a file if it exists."""
        path = self.get_final_path(folder_path, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except OSError:
                return False
        return False
