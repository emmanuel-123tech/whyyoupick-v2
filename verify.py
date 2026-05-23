with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

css_link = 'href="index.css"'
js_src = 'src="app.js"'
has_style = '<style>' in html
has_inline_js = '<script>' in html and 'DOMContentLoaded' in html

print('External CSS link still present:', css_link in html)
print('External JS script still present:', js_src in html)
print('Inline <style> tag present:', has_style)
print('Inline JS (DOMContentLoaded) present:', has_inline_js)
