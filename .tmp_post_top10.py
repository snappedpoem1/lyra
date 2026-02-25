import sqlite3
con = sqlite3.connect('lyra_registry.db')
cur = con.cursor()
print('queue status counts', cur.execute('select status,count(*) from acquisition_queue group by status order by count(*) desc').fetchall())
print('recent top10 artists queue', cur.execute("select artist,count(*) from acquisition_queue where source='discography' group by artist order by count(*) desc limit 12").fetchall())
print('recent active tracks', cur.execute("select count(*) from tracks where status='active'").fetchone()[0])
con.close()
