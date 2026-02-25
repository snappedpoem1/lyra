import sqlite3
from pathlib import Path
con = sqlite3.connect('lyra_registry.db')
cur = con.cursor()
print('tracks_active', cur.execute("select count(*) from tracks where status='active'").fetchone()[0])
print('embeddings_rows', cur.execute('select count(*) from embeddings').fetchone()[0])
print('track_scores_rows', cur.execute('select count(*) from track_scores').fetchone()[0])
print('missing_scores_active', cur.execute("select count(*) from tracks t left join track_scores s on t.track_id=s.track_id where t.status='active' and s.track_id is null").fetchone()[0])
recent = cur.execute("""
select artist,title from acquisition_queue
where source='discography' and status in ('complete','completed')
order by id desc limit 30
""").fetchall()
matched=0
with_files=0
with_scores=0
for artist,title in recent:
    row = cur.execute("select track_id, filepath from tracks where status='active' and lower(artist)=lower(?) and lower(title)=lower(?) order by updated_at desc limit 1", (artist,title)).fetchone()
    if not row:
        continue
    matched += 1
    tid, fp = row
    if fp and Path(fp).exists():
        with_files += 1
    if cur.execute('select 1 from track_scores where track_id=?',(tid,)).fetchone():
        with_scores += 1
print('recent30_exact_match_in_tracks', matched)
print('recent30_file_exists', with_files)
print('recent30_scored', with_scores)
print('sample_recent5')
for artist,title in recent[:5]:
    row = cur.execute("select track_id, filepath from tracks where status='active' and lower(artist)=lower(?) and lower(title)=lower(?) order by updated_at desc limit 1", (artist,title)).fetchone()
    print((artist,title,row))
con.close()
