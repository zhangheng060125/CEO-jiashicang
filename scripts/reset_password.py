"""Interactive administrator password rotation. Password never written to logs."""
import getpass,sys,secrets
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server as s
username=input('Username: ').strip();password=getpass.getpass('New password (12+ characters): ')
if len(password)<12:raise SystemExit('At least 12 characters required')
if password!=getpass.getpass('Repeat password: '):raise SystemExit('Passwords do not match')
with s.db() as c:
 row=c.execute('SELECT id FROM users WHERE username=?',(username,)).fetchone()
 if not row:raise SystemExit('User not found')
 salt=secrets.token_hex(16);c.execute('UPDATE users SET salt=?,hash=? WHERE id=?',(salt,s.password_hash(password,salt),row['id']));c.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
 s.audit(c,{'username':'server administrator'},'password_reset',None,'actual','',{'username':username})
if username=='admin':
 path=s.DATA/'admin-password.txt'
 if path.exists():path.unlink()
print('Password updated; existing sessions revoked.')
