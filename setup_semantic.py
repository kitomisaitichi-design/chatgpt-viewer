"""Portable semantic setup. Downloads packages/model only, never conversation data."""
import importlib, json, os, runpy, shutil, site, subprocess, sys
from pathlib import Path
APP=Path(__file__).resolve().parent
PACKAGES=APP/'.semantic-packages'
STAGING=APP/'.semantic-staging'
MODEL='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
ENV={'HF_HOME':str(APP/'.semantic-cache'),'HF_HUB_DISABLE_TELEMETRY':'1',
     'HF_HUB_DISABLE_PROGRESS_BARS':'1','TOKENIZERS_PARALLELISM':'false',
     'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}

DLL_HANDLES=[]
def activate(path=PACKAGES):
    if os.name=='nt' and not DLL_HANDLES:
        DLL_HANDLES.append(os.add_dll_directory(str(APP/'runtime')))
    if path.is_dir():
        location=str(path.resolve());site.addsitedir(location)
        # App-local versions win over packages from an older full-Python setup.
        if location in sys.path:sys.path.remove(location)
        sys.path.insert(0,location);importlib.invalidate_caches()

def phase(message):print('VIEWER_SETUP:'+message,flush=True)

def pip_command(target,*requirements,index=None,constraint=None):
    args=[sys.executable,str(APP/'setup_semantic.py'),'--pip',str(target),'install',
          '--disable-pip-version-check','--no-warn-script-location','--only-binary=:all:',
          '--upgrade','--target',str(target),'--cache-dir',str(APP/'.semantic-cache'/'pip')]
    if index:args+=['--index-url',index]
    if constraint:args+=['--constraint',str(constraint),'--extra-index-url','https://download.pytorch.org/whl/cpu']
    return args+list(requirements)

def install():
    os.environ.update(ENV)
    if not (PACKAGES/'.ready').is_file():
        STAGING.mkdir(exist_ok=True)
        phase('Downloading portable CPU engine (first setup can take several minutes)…')
        subprocess.run(pip_command(STAGING,'torch',index='https://download.pytorch.org/whl/cpu'),check=True)
        activate(STAGING)
        from importlib.metadata import version
        constraint=STAGING/'torch-constraint.txt'
        constraint.write_text('torch=='+version('torch')+'\n')
        phase('Installing multilingual search packages…')
        subprocess.run(pip_command(STAGING,'sentence-transformers>=3.4,<6',constraint=constraint),check=True)
        # Import validation happens in a fresh process: pip can replace modules.
        subprocess.run([sys.executable,str(APP/'setup_semantic.py'),'--check',str(STAGING)],check=True)
        backup=APP/'.semantic-old'
        if backup.exists():shutil.rmtree(backup)
        if PACKAGES.exists():PACKAGES.rename(backup)
        STAGING.rename(PACKAGES)
        (PACKAGES/'.ready').write_text('portable CPU semantic dependencies\n')
        if backup.exists():shutil.rmtree(backup)
    activate()
    destination=APP/'models'/'semantic'
    if not (destination/'.ready').is_file():
        phase('Downloading multilingual meaning model; conversations stay on this computer…')
        from sentence_transformers import SentenceTransformer
        import torch
        torch.set_num_threads(1)
        model=SentenceTransformer(MODEL,trust_remote_code=False,device='cpu')
        temporary=APP/'models'/'semantic-staging';temporary.mkdir(parents=True,exist_ok=True)
        model.save(str(temporary))
        SentenceTransformer(str(temporary),local_files_only=True,trust_remote_code=False,device='cpu')
        if destination.exists():shutil.rmtree(destination)
        temporary.rename(destination)
        (destination/'.ready').write_text(MODEL+'\n')
    phase('Local model ready; starting archive indexing…')

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--pip':
        activate(Path(sys.argv[2]))
        tool=APP/'runtime'/'pip.pyz'
        sys.path.insert(0,str(tool));sys.argv=[str(tool)]+sys.argv[3:]
        runpy.run_path(str(tool),run_name='__main__')
    elif len(sys.argv)>1 and sys.argv[1]=='--check':
        activate(Path(sys.argv[2]))
        import numpy,torch,sentence_transformers
        print('Portable dependencies validated.',flush=True)
    else:
        try:install()
        except Exception as error:
            phase('Setup interrupted: '+str(error)+'. Select semantic search again to retry.')
            sys.exit(1)
