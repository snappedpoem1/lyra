import sqlite3, re
from difflib import SequenceMatcher

def norm(s):
    s=(s or '').lower()
    s=re.sub(r'\s*\(feat\.?[^\)]*\)','',s)
    s=re.sub(r'\s*\[[^\]]*\]','',s)
    s=re.sub(r'[^a-z0-9\s]',' ',s)
    s=re.sub(r'\s+',' ',s).strip()
    return s

con=sqlite3.connect('lyra_registry.db')
cur=con.cursor()
recent=cur.execute("select artist,title from acquisition_queue where source='discography' and status in ('complete','completed') order by id desc limit 30").fetchall()
fuzzy=0
examples=[]
for artist,title in recent:
    cand=cur.execute("select title, filepath from tracks where status='active' and lower(artist)=lower(?)",(artist,)).fetchall()
    nt=norm(title)
    best=(0,None,None)
    for t,fp in cand:
        r=SequenceMatcher(None, nt, norm(t)).ratio()
        if r>best[0]: best=(r,t,fp)
    if best[0] >= 0.84:
        fuzzy += 1
        if len(examples)<8:
            examples.append((artist,title,best[1],round(best[0],3),best[2]))
print('recent30_fuzzy_matched',fuzzy)
print('examples')
for e in examples:
    print(e)
con.close()
