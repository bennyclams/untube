

with open("cipher.py", 'r') as f:
    data = f.read()
    lines = data.splitlines()

new_line = """
        r'a\.[a-zA-Z]\s*&&\s*\([a-z]\s*=\s*a\.get\("n"\)\)\s*&&.*?\|\|\s*([a-z]+)',
"""
print(f"{lines[271]} -> {new_line}")
lines[271] = new_line
new_file = "\r\n".join(lines)
with open("cipher.py", 'w') as f:
    f.write(new_file)
