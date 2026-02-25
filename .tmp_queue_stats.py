import sqlite3
con = sqlite3.connect('lyra_registry.db')
cur = con.cursor()
print('acquisition_queue_total', cur.execute('select count(*) from acquisition_queue').fetchone()[0])
print('status_counts', cur.execute('select status,count(*) from acquisition_queue group by status order by count(*) desc').fetchall())
print('tracks_active', cur.execute("select count(*) from tracks where status='active'").fetchone()[0])
print('recent_completed_discography', cur.execute("select artist,title,status,source from acquisition_queue where source='discography' order by id desc limit 12").fetchall())
con.close()
