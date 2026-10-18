# -*- coding: utf-8 -*-
import re
from lxml import html as LH
p = r'E:\deepSeek\ui-design\index.html'
raw = open(p, encoding='utf-8').read()
doc = LH.fromstring(raw)
errors, warns = [], []

def xp(q): return doc.xpath(q)
def attr(e, a): return e.get(a)

pages = xp('//section[contains(concat(" ",normalize-space(@class)," ")," page ")]')
ids_pages = [s.get('id') for s in pages]
print('pages:', len(pages), ids_pages)
if len(pages) != 8: errors.append('page count != 8')
pages_id = set(ids_pages)

navs = xp('//a[contains(concat(" ",normalize-space(@class)," ")," nav-item ")]')
print('nav items:', len(navs), [n.get('data-page') for n in navs])
for n in navs:
    if 'page-' + (n.get('data-page') or '') not in pages_id:
        errors.append('nav target missing: ' + str(n.get('data-page')))

allids = [e.get('id') for e in xp('//*[@id]')]
dups = sorted({i for i in allids if allids.count(i) > 1})
print('ids:', len(allids), 'dups:', dups)
if dups: errors.append('duplicate ids: %s' % dups)

symbols = {s.get('id') for s in xp('//symbol')}
refs = set()
for u in xp('//use'):
    h = u.get('href') or ''
    if h.startswith('#'): refs.add(h[1:])
    else: refs.add('EXTERNAL:' + h)
missing = sorted(r for r in refs if r not in symbols)
print('symbols:', len(symbols), 'used:', len(refs), 'missing:', missing)
if missing: errors.append('missing symbols: %s' % missing)
print('unused symbols:', sorted(symbols - refs))

ext = re.findall(r'(?:src|href)="(https?://[^"]+)"', raw)
print('external refs:', ext[:5])
if ext: errors.append('external refs found')
if re.search(r'<script[^>]+src=', raw): errors.append('external script tag')
if re.search(r'<link[^>]+href=', raw): errors.append('link tag found')
for ph in ('CSS_PLACEHOLDER', 'JS_PLACEHOLDER'):
    if ph in raw: errors.append('placeholder remains: ' + ph)

css = re.search(r'<style>(.*?)</style>', raw, re.S).group(1)
print('css braces:', css.count('{'), css.count('}'), 'len', len(css))
if css.count('{') != css.count('}'): errors.append('css brace mismatch')

def count(q): return len(xp(q))
print('agent cards:', count('//article[contains(@class,"agent-card")]'),
      '| mem cards:', count('//article[contains(@class,"mem-card")]'),
      '| nodes:', count('//button[contains(@class,"node")]'),
      '| ev tabs:', count('//*[@data-ev-tab]'),
      '| switches:', count('//*[@data-switch]'))
print('script tags:', count('//script'), '| style tags:', count('//style'))

if count('//article[contains(@class,"agent-card")]') < 7: warns.append('agent cards < 7')
if count('//button[contains(@class,"node")]') < 7: warns.append('nodes < 7')
if count('//article[contains(@class,"mem-card")]') < 6: warns.append('memory cards < 6')

actions = sorted({e.get('data-action') for e in xp('//*[@data-action]')})
js_actions = set(re.findall(r"case '([a-z-]+)':", raw))
print('actions:', actions)
print('js actions:', sorted(js_actions))
print('unhandled actions:', sorted(set(actions) - js_actions))

for txt in ['ast 92', 'UserList.vue', 'LoopX', 'Vue2', 'TreeSelect.vue', 'src/views/UserList.vue']:
    if txt not in raw: warns.append('text missing: ' + txt)

print('\nERRORS:', errors)
print('WARNINGS:', warns)
