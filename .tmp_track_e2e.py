import sqlite3
from pathlib import Path
con=sqlite3.connect('lyra_registry.db')
cur=con.cursor()
artist='Kanye West'
title='The New Workout Plan'
row=cur.execute("select track_id,filepath,status,artist,title,album,updated_at from tracks where lower(artist)=lower(?) and lower(title)=lower(?) order by updated_at desc limit 1",(artist,title)).fetchone()
print('track_row',row)
if row:
    tid=row[0]
    print('file_exists', Path(row[1]).exists())
    emb=cur.execute("select model, indexed_at from embeddings where track_id=? order by indexed_at desc limit 1",(tid,)).fetchone()
    print('embedding_row',emb)
    score=cur.execute("select energy,valence,tension,density,warmth,movement,space,rawness,complexity,nostalgia,score_version from track_scores where track_id=?",(tid,)).fetchone()
    print('score_row',score)
con.close()
