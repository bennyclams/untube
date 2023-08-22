
# cipher.py changes
with open("cipher.py", 'r') as f:
    data = f.read()
    lines = data.splitlines()

new_line = """
        r'a\.[a-zA-Z]\s*&&\s*\([a-z]\s*=\s*a\.get\("n"\)\)\s*&&.*?\|\|\s*([a-z]+)',
"""
new_line_2 = lines[277].replace(";", "")
new_line_3 = "        return []"
print(f"{lines[271]} -> {new_line}")
lines[271] = new_line
# print(f"{lines[277]} -> {new_line_2}")
# lines[277] = new_line_2
print(f"{lines[226]} -> {new_line_3}")
lines[226] = "        return []"
new_file = "\r\n".join(lines)
# with open("cipher.py", 'w') as f:
#     f.write(new_file)

# streams.py changes
with open("streams.py", 'r') as f:
    data = f.read()
    lines = data.splitlines()

bitrate_line = lines[61]
conditional = "if 'bitrate' in stream else 0"
print(f"{bitrate_line} -> {bitrate_line} {conditional}")
lines[61] = f"{bitrate_line} {conditional}"
new_file = "\r\n".join(lines)

with open("streams.py", 'w') as f:
    f.write(new_file)
