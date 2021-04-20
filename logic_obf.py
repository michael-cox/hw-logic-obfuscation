#!python3

import argparse
import subprocess
import sys
import os
import re

# -s 500 -r 10 -F faults -l log -U undetected_faults
HOPE_OPTS = ['./hope/hope', '-s', '500', '-r', '10', '-F', 'faults', '-l', 'log', '-U', 'undetected_faults']

INPUT_RE = re.compile('^INPUT\((?P<inputs>\w*)\)', flags=re.A | re.M)
OUTPUT_RE = re.compile('^OUTPUT\((?P<outputs>\w*)\)', flags=re.A | re.M)
OP_RE = re.compile('^((\w*) = (\w*)\((\w*),\s(\w*)\))', flags = re.M | re.A)

class Bench:
    def __init__(self, inputs, outputs, signals, ops):
        self.inputs = inputs
        self.outputs = outputs
        self.signals = signals
        self.ops = ops
    def debug_print(self):
        print('INPUTS: {}'.format(str(self.inputs)))
        print('OUTPUTS: {}'.format(str(self.outputs)))
        print('SIGNALS: {}'.format(str(self.signals)))
        print('OPS:')
        for line in self.ops: print(line)

def error(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def parse_args():
    parser = argparse.ArgumentParser(description='Process command line arguments')
    parser.add_argument('input_netlist', help='the input netlist .bench file')
    parser.add_argument('output_netlist', help='the output netlist .bench file')
    args = parser.parse_args()
    return args

def get_hope_faults(netlist):
    hope_proc = subprocess.run(HOPE_OPTS + [netlist], capture_output=True)
    if hope_proc.stderr:
        error(hope_proc.stderr.decode('utf-8'))
        if 'hope.warning' in os.listdir():
            with open('hope.warning', 'r') as data:
                warning = data.read()
                error(warning.strip())
            os.remove('hope.warning')

    faults = ''
    if 'faults' in os.listdir():
        with open('faults', 'r') as data:
            faults = data.read()
        os.remove('faults')
    if faults:
        return faults
    error('Hope found no faults.')
    exit(-1)

def read_bench(netlist):
    with open(netlist, 'r') as data:
        text = data.read()
    inputs = INPUT_RE.findall(text)
    outputs = OUTPUT_RE.findall(text)
    op_full_match = OP_RE.findall(text)
    signals = [ tup[1] for tup in op_full_match if tup[1] not in outputs ]
    ops = [ tup[0] for tup in op_full_match ]
    return Bench(inputs, outputs, signals, ops)

if __name__ == '__main__':
    args = parse_args()
    # hope_out = get_hope_faults(args.input_netlist)
    bench = read_bench(args.input_netlist)
    bench.debug_print()
