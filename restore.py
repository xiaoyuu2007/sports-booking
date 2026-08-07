import re

with open('webapp.py', 'r') as f:
    content = f.read()

with open('temp.js', 'r') as f:
    js_content = f.read()

# Replace the script block in webapp.py with temp.js
content = re.sub(r'<script>.*?</script>', '<script>\n' + js_content + '\n</script>', content, flags=re.DOTALL)

with open('webapp.py', 'w') as f:
    f.write(content)
