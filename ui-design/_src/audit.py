# -*- coding: utf-8 -*-
import re
from lxml import html as LH
raw = open(r'E:\deepSeek\ui-design\index.html', encoding='utf-8').read()
css = re.search(r'<style>(.*?)</style>', raw, re.S).group(1)
html = raw[raw.index('<body>'):]

classes_html = set()
for m in re.finditer(r'class="([^"]+)"', html):
    for c in m.group(1).split():
        classes_html.add(c)
classes_css = set(re.findall(r'\.([a-zA-Z_][\w-]*)', css))
# ignore dynamic js classes and generic
dynamic = {'on','active','sel','loading','open','out','done','run','idle','warn','err','ok','info','failed','recovered','agents-list','no','is-disabled','selected','js'}
unstyled = sorted(c for c in classes_html if c not in classes_css and c not in dynamic)
print('HTML classes:', len(classes_html), 'CSS classes:', len(classes_css))
print('HTML classes without CSS rule (%d):' % len(unstyled))
print(unstyled)
unused = sorted(c for c in classes_css if c not in classes_html and c not in dynamic)
print('\nCSS classes unused in HTML (%d):' % len(unused))
print(unused)
# check ids referenced in JS exist
js = re.search(r'<script>(.*?)</script>', raw, re.S).group(1)
ids_html = set(re.findall(r'id="([^"]+)"', raw))
ids_js = set(re.findall(r"\$\('#([\w-]+)'\)", js))
print('\nJS ids missing in HTML:', sorted(ids_js - ids_html))
selectors_js = set(re.findall(r"\$\('([^']+)'\)", js)) | set(re.findall(r"\$\$\('([^']+)'\)", js))
bad = []
for s in selectors_js:
    if s.startswith('#') and ' ' not in s and '[' not in s and ':' not in s:
        if s[1:] not in ids_html: bad.append(s)
print('JS simple id selectors missing:', sorted(bad))
# class selectors used by JS
jscls = set()
for s in selectors_js:
    if s.startswith('.') and ' ' not in s:
        jscls.add(s[1:].split('[')[0])
print('JS single class selectors:', sorted(jscls))
print('JS class selectors without HTML class:', sorted(c for c in jscls if c not in classes_html))
