import sqlite3
con=sqlite3.connect('lyra_registry.db')
cur=con.cursor()
print('tracks_active', cur.execute("select count(*) from tracks where status='active'").fetchone()[0])
print('embeddings_rows', cur.execute('select count(*) from embeddings').fetchone()[0])
print('track_scores_rows', cur.execute('select count(*) from track_scores').fetchone()[0])
print('missing_embedding_active', cur.execute("select count(*) from tracks t left join embeddings e on t.track_id=e.track_id and e.model='clap_htsat_unfused' where t.status='active' and e.track_id is null").fetchone()[0])
print('missing_scores_active', cur.execute("select count(*) from tracks t left join track_scores s on t.track_id=s.track_id where t.status='active' and s.track_id is null").fetchone()[0])
con.close()
