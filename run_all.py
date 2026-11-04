"""Reproduce the current allocation audit from supplied records without model calls."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from package_runtime import parser, resolve

def main():
    p = parser()
    p.add_argument('--smoke-test', action='store_true', help='Verify static hashes and formal counts; no third-party packages required.')
    args = p.parse_args()
    data, output = resolve(args.data), resolve(args.output)
    if not data.is_file():
        p.error('Formal-trial input file not found.')
    if output == ROOT or data.is_relative_to(output) or any(output.is_relative_to(ROOT/n) for n in ['data','src','docs','figures','prompts']):
        p.error('Output directory would overlap protected package inputs.')
    output.mkdir(parents=True, exist_ok=True)
    stages = ['verification/smoke_check.py']
    if not args.smoke_test:
        stages += ['analysis/01_prepare_data.py','analysis/02_fit_models.py',
                   'analysis/03_uncertainty_and_strata.py','analysis/04_verify_protocol.py',
                   'analysis/05_export_tables.py','figures/plot_figures.py',
                   'verification/verify_results.py']
    env = dict(os.environ)
    env.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',
               OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    logs = output / 'logs'
    logs.mkdir(exist_ok=True)
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='allocation_plot_') as cache:
        env['MPLCONFIGDIR'] = cache
        with (logs / 'run.log').open('w', encoding='utf-8') as log:
            for relative in stages:
                print('RUN ' + relative, flush=True)
                log.write('\nRUN ' + relative + '\n'); log.flush()
                cmd = [sys.executable,str(ROOT/'src/offline_executor.py'),str(ROOT/'src'/relative),
                       '--data',str(data),'--output',str(output),
                       '--figure-formats',*args.figure_formats]
                result = subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                if result.returncode:
                    print('FAILED: '+relative+'. Inspect the selected output directory: logs/run.log.')
                    return result.returncode
    print('PASS: '+('smoke check' if args.smoke_test else 'complete offline reproduction')+
          f' ({time.monotonic()-start:.1f} seconds).')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

