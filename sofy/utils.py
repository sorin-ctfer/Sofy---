import socket
import json
import base64

def get_local_ip():
    """Retrieves the local LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('8.8.8.8', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def generate_token(ip, port, username, password):
    """Generates a Base64 encoded token containing connection details."""
    data = {
        "ip": ip,
        "port": port,
        "username": username,
        "password": password
    }
    json_str = json.dumps(data)
    token_bytes = json_str.encode('utf-8')
    encoded_token = base64.b64encode(token_bytes)
    return encoded_token.decode('utf-8')

def generate_group_token(ip, port, group_name):
    """Generates a Base64 encoded token for a group."""
    data = {
        "type": "group",
        "ip": ip,
        "port": port,
        "group_name": group_name
    }
    json_str = json.dumps(data)
    token_bytes = json_str.encode('utf-8')
    encoded_token = base64.b64encode(token_bytes)
    return encoded_token.decode('utf-8')

def parse_token(token_str):
    """Parses the Base64 encoded token back into a dictionary."""
    try:
        token_bytes = base64.b64decode(token_str)
        json_str = token_bytes.decode('utf-8')
        return json.loads(json_str)
    except Exception as e:
        print(f"Error parsing token: {e}")
        return None
