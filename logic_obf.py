#!python3

import argparse
import subprocess
import sys
import os
import re
import pathlib

# -s 500 -r 10 -F faults -l log -U undetected_faults
HOPE_OPTS = ['./hope/hope', '-s', '500', '-r', '10', '-F', 'faults', '-l', 'log', '-N']

INPUT_RE = re.compile('^INPUT\((?P<inputs>\w*)\)', flags=re.A | re.M)
OUTPUT_RE = re.compile('^OUTPUT\((?P<outputs>\w*)\)', flags=re.A | re.M)
OP_RE = re.compile('^(\w*)\s*=\s*(\w*)\((.*)\)', flags = re.M | re.A)

DFF_GATES = ['VDD', 'CK']

LOGIC_OP_STR = '{} = {}({})'

BENCH_TO_VERILOG = {
        'DFF' : 'FD',
        'NOT' : 'IV ',
        'NAND' : 'ND',
        'NOR' : 'NR',
        'AND' : 'AN',
        'OR' : 'OR'
        }

# LogicOp - class containing a testbench style logic operation
# ----------
# assignee - gate that is being assigned to
# operation - string of the operation (e.g. and, nand)
# operands - list of gate parameters
class LogicOp:
    def __init__(self, assignee, operation, operands):
        self.assignee = assignee
        self.operation = operation.upper()
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
        extpos = netlist.rfind('.')
        name = pathlib.PurePath(netlist).stem
        inputs = INPUT_RE.findall(text)
        outputs = OUTPUT_RE.findall(text)
        op_full_match = OP_RE.findall(text)
        signals = [ tup[0] for tup in op_full_match if tup[0] not in outputs ]
        ops = []
        for op_reg in op_full_match:
            operands = op_reg[2]
            operands = re.sub(r'\s+', '', operands)
            ops.append(LogicOp(op_reg[0], op_reg[1], operands.split(',')))
    
        return Bench(name, inputs, outputs, signals, ops)

    def __init__(self, name, inputs, outputs, signals, ops):
        self.name = name
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

    # TODO: refactor to a staticmethod in a verilog class, this is a messy
    def to_verilog(self, outfile):
        with open(outfile, 'w') as verilog_file:
            included_dff_gates = []
            for op in self.ops:
                if op.operation == 'DFF':
                    included_dff_gates = DFF_GATES
                    break
            print('module {name}({ports});'.format(name=self.name,
                ports=','.join(included_dff_gates + self.inputs + self.outputs)),
                file=verilog_file)
            print('input {inputs};'.format(inputs=','.join(included_dff_gates + self.inputs)),
                    file=verilog_file)
            print('output {outputs};'.format(outputs=','.join(self.outputs)),
                    file=verilog_file)
            print(file=verilog_file)
            print('  wire {signals};'.format(signals=','.join(self.signals)),
                    file=verilog_file)
            print(file=verilog_file)
            op_count = {}
            for op in self.ops:
                count = 0
                if op.operation not in op_count:
                    op_count[op.operation] = 1
                else:
                    count = op_count[op.operation]
                    op_count[op.operation] += 1
                included_clk = []
                if op.operation == 'DFF':
                    included_clk.append('CK')
                num_operands = 0
                if op.operation != 'IV':
                    num_operands = len(op.operands)
                print('  {module:<3} {mod_name}_{count}({gates});'.format(
                    module = BENCH_TO_VERILOG[op.operation] + str(num_operands),
                    mod_name = op.operation,
                    count = count,
                    gates = ','.join(included_clk + [op.assignee] + op.operands)),
                    file=verilog_file)
            print(file=verilog_file)
            print('endmodule', file=verilog_file)
            
        
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
    bench.to_verilog('out.v')

    # print(hope_out)
