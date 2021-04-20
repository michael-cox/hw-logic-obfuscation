#!python3

import argparse
import subprocess
import sys
import os
import re

# -s 500 -r 10 -F faults -l log -U undetected_faults
HOPE_OPTS = ['./hope/hope', '-s', '500', '-r', '10', '-F', 'faults', '-l', 'log', '-N']

INPUT_RE = re.compile('^INPUT\((?P<inputs>\w*)\)', flags=re.A | re.M)
OUTPUT_RE = re.compile('^OUTPUT\((?P<outputs>\w*)\)', flags=re.A | re.M)
OP_RE = re.compile('^(\w*)\s*=\s*(\w*)\((.*)\)', flags = re.M | re.A)

LOGIC_OP_STR = '{} = {}({})'

# LogicOp - class containing a testbench style logic operation
# ----------
# assignee - gate that is being assigned to
# operation - string of the operation (e.g. and, nand)
# operands - list of gate parameters
class LogicOp:
    def __init__(self, assignee, operation, operands):
        self.assignee = assignee
        self.operation = operation
        self.operands = operands
    def __repr__(self):
        return LOGIC_OP_STR.format(self.assignee, self.operation, ', '.join(self.operands))

# Bench - class to represent bench netlist
# ----------
# inputs - list of input gates
# outputs - list of output gates
# signals - list of signal gates
# ops - list of LogicOp's in order
class Bench:
    @staticmethod
    def from_file(netlist):
        with open(netlist, 'r') as data:
            text = data.read()
        inputs = INPUT_RE.findall(text)
        outputs = OUTPUT_RE.findall(text)
        op_full_match = OP_RE.findall(text)
        signals = [ tup[0] for tup in op_full_match if tup[0] not in outputs ]
        ops = []
        for op_reg in op_full_match:
            operands = op_reg[2]
            operands = re.sub(r'\s+', '', operands)
            ops.append(LogicOp(op_reg[0], op_reg[1], operands.split(',')))
    
        return Bench(inputs, outputs, signals, ops)

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
        for op in self.ops: print(op)

    # TODO: function for converting to verilog
    # TODO: function for representing as bench

# error - function to print errors
def error(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# parse_args - function to parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='Process command line arguments')
    parser.add_argument('input_netlist', help='the input netlist .bench file')
    parser.add_argument('output_netlist', help='the output netlist .bench file')
    args = parser.parse_args()
    return args

# get_hop_faults - runs hope and returns the fault file as a string
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

if __name__ == '__main__':
    args = parse_args()
    bench = Bench.from_file(args.input_netlist)
    bench.debug_print()

    hope_out = get_hope_faults(args.input_netlist)
    print(hope_out)
