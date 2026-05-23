import re

with open('index.css', 'r', encoding='utf-8') as f:
    css = f.read()
with open('app.js', 'r', encoding='utf-8') as f:
    js = f.read()
with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace external CSS link with inline style block
css_link = '<link rel="stylesheet" href="index.css">'
html = html.replace(css_link, '<style>\n' + css + '\n</style>')

# Replace external JS script with inline script block
js_script = '<script src="app.js"></script>'
html = html.replace(js_script, '<script>\n' + js + '\n</script>')

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('Done! index.html now has CSS and JS inlined.')
print('Total file size:', len(html), 'characters')
