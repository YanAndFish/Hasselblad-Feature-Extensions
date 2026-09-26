"""Run the actual shell transaction with mock I/O; no camera or USB access."""
import json
import os
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASH=Path('C:/Program Files/Git/bin/bash.exe')
MOCK=r'''
state=original
paused=0
busy_count=0
backend_log() { printf '%s state=%s paused=%s\n' "$*" "$state" "$paused"; }
backend_same() { [ "$CASE" != identity ] || [ "$tx_dirty" = 0 ]; }
backend_preflight() { [ "$CASE" != preflight ]; }
backend_freeze() { paused=1; [ "$CASE" != freeze ]; }
backend_pc_clear() {
  [ "$CASE" != pc_busy ] || return 1
  if [ "$CASE" = restore_busy ] && [ "$tx_restoring" = 1 ] && [ "$busy_count" -lt 2 ]; then
    busy_count=$((busy_count+1)); return 1
  fi
}
backend_retry_wait() { :; }
backend_is_original() { [ "$state" = original ] && [ "$CASE" != original_mismatch ]; }
backend_is_candidate() { [ "$state" = candidate ] && [ "$CASE" != verify_candidate ]; }
backend_write_candidate() {
  state=partial
  if [ "$CASE" = write_candidate ]; then return 1; fi
  state=candidate
}
backend_write_original() {
  if [ "$CASE" = write_original ]; then return 1; fi
  state=original
}
backend_thaw() {
  if [ "$state" = partial ]; then echo BUG_RESUMED_PARTIAL; exit 100; fi
  if [ "$CASE" = thaw_candidate ] && [ "$state" = candidate ]; then return 1; fi
  paused=0
}
backend_wait() {
  case "$CASE" in
    interrupted) kill -TERM $$;;
    wait_error) return 1;;
  esac
}
'''

def main():
    core=(HERE/'transaction.sh').read_text(encoding='utf-8')
    cases=['success','preflight','freeze','pc_busy','original_mismatch',
           'write_candidate','verify_candidate','thaw_candidate','wait_error',
           'interrupted','write_original','identity','restore_busy']
    results=[]
    env=dict(os.environ,HOME=str(HERE),TMPDIR=str(HERE))
    for case in cases:
        script=HERE/'transaction-test.sh'
        script.write_text('CASE='+case+'\n'+MOCK+'\n'+core+'\ntx_run\nexit $?\n',encoding='utf-8',newline='\n')
        run=subprocess.run([str(BASH),'--noprofile','--norc',str(script)],cwd=HERE,env=env,capture_output=True,text=True,timeout=5)
        out=run.stdout
        assert not run.stderr,(case,run.stderr)
        assert 'BUG_RESUMED_PARTIAL' not in out,(case,out)
        if case in ['success','restore_busy']: assert run.returncode==0 and 'RESTORED state=original paused=0' in out
        elif case in ['preflight','freeze','pc_busy','original_mismatch']:
            assert run.returncode!=0 and 'state=original paused=0' in out,(case,out)
        elif case in ['write_original','identity']:
            assert run.returncode!=0 and 'RESTORED state=' not in out,(case,out)
        else:
            assert run.returncode!=0 and 'RESTORED state=original paused=0' in out,(case,out)
        results.append(dict(case=case,exitCode=run.returncode,output=out.strip()))
    for case in cases[:8]:
        script=HERE/'transaction-test.sh'
        script.write_text('CASE='+case+'\n'+MOCK+'\n'+core+'\ntx_install_until_restart\nexit $?\n',encoding='utf-8',newline='\n')
        run=subprocess.run([str(BASH),'--noprofile','--norc',str(script)],cwd=HERE,env=env,capture_output=True,text=True,timeout=5)
        out=run.stdout
        assert not run.stderr and 'BUG_RESUMED_PARTIAL' not in out,(case,out,run.stderr)
        if case=='success':
            assert run.returncode==0 and 'ACTIVE_UNTIL_RESTART state=candidate paused=0' in out
            assert 'RESTORED state=' not in out
        elif case in ['preflight','freeze','pc_busy','original_mismatch']:
            assert run.returncode!=0 and 'state=original paused=0' in out,(case,out)
        else:
            assert run.returncode!=0 and 'RESTORED state=original paused=0' in out,(case,out)
        results.append(dict(case='until_restart_'+case,exitCode=run.returncode,output=out.strip()))
    for path in ['device_backend.sh','transaction.sh']:
        subprocess.run([str(BASH),'--noprofile','--norc','-n',str(HERE/path)],cwd=HERE,env=env,check=True)
    (HERE/'transaction-test-results.json').write_text(json.dumps(dict(status='PASS',cases=results,hardwareAccess=False),indent=2)+'\n',encoding='utf-8')
    print('PASS: '+str(len(results))+' shell transaction fault cases; zero camera access')

if __name__=='__main__':main()
