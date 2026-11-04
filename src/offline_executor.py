"""Execute an analysis or plotting step with network connections disabled."""
from pathlib import Path
import runpy
import sys
sys.dont_write_bytecode = True
from package_runtime import disable_network

if __name__ == '__main__':
    disable_network()
    target = Path(sys.argv[1]).resolve()
    source_root = Path(__file__).resolve().parent
    if not target.is_relative_to(source_root) or target.parts[-2] == 'experiment':
        raise SystemExit('Only packaged analysis, figure and verification steps can run here.')
    sys.argv = [str(target)] + sys.argv[2:]
    runpy.run_path(str(target), run_name='__main__')

