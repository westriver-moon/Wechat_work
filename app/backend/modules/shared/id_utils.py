import secrets


def generate_view_code(byte_length: int = 4) -> str:
    return secrets.token_hex(byte_length).upper()