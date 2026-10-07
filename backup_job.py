"""Background entry point used by the Windows idle task."""
import argparse
from pathlib import Path
from viewer import Archive
from archive_backup import BackupManager

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir',required=True);p.add_argument('--scheduled',action='store_true');p.add_argument('--profile');args=p.parse_args()
    archive=Archive(args.data_dir,background_process=False)
    if args.profile:
        from preferences import attach
        attach(archive,args.profile)
    manager=BackupManager(archive,Path(__file__).parent)
    try:
        if args.scheduled:manager.tick()
        else:manager.start(upload=manager.config()['auto_upload'])
        if manager.worker:manager.worker.join()
    except Exception as e:manager.update(phase='Waiting' if isinstance(e,InterruptedError) else 'Needs attention',error=str(e),force=True)
    finally:manager.close();archive.close()

if __name__=='__main__':main()
