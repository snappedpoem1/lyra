import sqlite3
from pathlib import Path
con = sqlite3.connect('lyra_registry.db')
cur = con.cursor()
recent = cur.execute("""
select artist, title
from acquisition_queue
where source='discography' and status in ('complete','completed')
order by id desc
limit 30
""").fetchall()
print('recent_completed', len(recent))
matched=0
scored=0
for artist,title in recent:
    row = cur.execute("select track_id, filepath from tracks where status='active' and lower(artist)=lower(?) and lower(title)=lower(?) order by updated_at desc limit 1", (artist,title)).fetchone()
    if row:
        matched += 1
        tid, fp = row
        if fp and Path(fp).exists():
            pass
        s = cur.execute("select 1 from track_scores where track_id=?", (tid,)).fetchone()
        if s:
            scored += 1
print('exact_match_in_tracks', matched)
print('scored_matches', scored)
print('tracks_active', cur.execute("select count(*) from tracks where status='active'").fetchone()[0])
con.close()
