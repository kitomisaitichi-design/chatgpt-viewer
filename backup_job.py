"""Background entry point used by the Windows idle task."""
import argparse
from pathlib import Path
from viewer import Archive
from archive_backup import BackupManager,job_lock

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir',required=True);p.add_argument('--scheduled',action='store_true');args=p.parse_args()
    archive=Archive(args.data_dir,background_process=False);manager=BackupManager(archive,Path(__file__).parent)
    try:
        if args.scheduled and not manager.due():return
        manager.scheduled=args.scheduled
        with job_lock(manager.data/'backup.lock'):manager.run(upload=True)
    except Exception as e:manager.update(phase='Waiting' if isinstance(e,InterruptedError) else 'Needs attention',error=str(e),force=True)
    finally:manager.close();archive.close()

if __name__=='__main__':main()
