"""Resolve package paths without depending on the working directory."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]

def parser():
    p = argparse.ArgumentParser()
    p.add_argument('--data', default='data/processed/formal_trials.csv')
    p.add_argument('--output', default='results')
    p.add_argument('--figure-formats', nargs='+', choices=['png','pdf','svg','eps'], default=['png'])
    return p

def resolve(value):
    p = Path(value).expanduser()
    return (ROOT / p).resolve() if not p.is_absolute() else p.resolve()

def paths():
    opts = parser().parse_args()
    data, output = resolve(opts.data), resolve(opts.output)
    if not data.is_file():
        raise SystemExit('Formal-trial CSV not found. Use --data to select it.')
    protected = [ROOT / n for n in ['data','src','docs','figures','prompts']]
    if output == ROOT or data.is_relative_to(output) or any(output.is_relative_to(p) for p in protected):
        raise SystemExit('Select an output directory outside the immutable input and source directories.')
    output.mkdir(parents=True, exist_ok=True)
    return ROOT, data, output, opts

def disable_network():
    def audit(event, args):
        if event in {'socket.connect','socket.connect_ex','socket.getaddrinfo','socket.gethostbyname'}:
            raise RuntimeError('Network access is disabled during offline reproduction.')
    sys.addaudithook(audit)

