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


# LogicOp - class containing a testbench style logic operation
# ----------
# assignee - gate that is being assigned to
# operation - string of the operation (e.g. and, nand)
# operands - list of gate parameters
class LogicOp:
    __bench_format = '{} = {}({})'
    __verilog_format = '  {module:<3} {mod_name}_{count}({gates});'
    __to_op_dict = {
            'AND' : 0,
            'OR' : 1,
            'NOT' : 2,
            'NOR' : 3,
            'NAND' : 4,
            'DFF' : 5
            }
    __to_bench_dict = dict((v,k) for k,v in __to_op_dict.items())
    __to_verilog_dict = {
            5 : 'FD',
            2 : 'IV',
            4 : 'ND',
            3 : 'NR',
            0 : 'AN',
            1 : 'OR'
            }

    def __init__(self, assignee, operation, operands):
        self.assignee = assignee
        self.operation = LogicOp.bench_to_op(operation)
        self.operands = operands

    def to_bench(self):
        return LogicOp.__bench_format.format(self.assignee, LogicOp.op_to_bench(self.operation), ', '.join(self.operands))

    @staticmethod
    def bench_to_op(op):
        return LogicOp.__to_op_dict[op.upper()]

    @staticmethod
    def op_to_verilog(op):
        return LogicOp.__to_verilog_dict[op]

    @staticmethod
    def op_to_bench(op):
        return LogicOp.__to_bench_dict[op]

    def to_verilog(self, counter):
        module_name = LogicOp.op_to_verilog(self.operation)
        if self.operation != 2:
            module_name += str(len(self.operands))

        operands = [self.assignee] + self.operands
        if self.operation == 5:
            operands = ['CK'] + operands

        return '  {module:<3} {label}_{count}({operands});'.format(
            module = module_name,
            label = LogicOp.op_to_bench(self.operation),
            count = counter,
            operands = ','.join(operands))

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
            new_op = LogicOp(op_reg[0], op_reg[1], operands.split(','))
            if new_op.operation == 5:
                includes_dff = True
            ops.append(new_op)
    
        return Bench(name, inputs, outputs, signals, ops, includes_dff)

    def __init__(self, name, inputs, outputs, signals, ops, includes_dff):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.signals = signals
        self.ops = ops
        self.includes_dff = includes_dff

    def debug_print(self):
        print('INPUTS: {}'.format(str(self.inputs)))
        print('OUTPUTS: {}'.format(str(self.outputs)))
        print('SIGNALS: {}'.format(str(self.signals)))
        print('OPS:')
        for op in self.ops: print(LogicOp.to_bench(op))
            
class VerilogModule:
    start_format = 'module {name}({ports});'
    input_format = 'input {inputs};'
    output_format = 'output {outputs};'
    wire_format = '  wire {wires};'
    end_boiler = 'endmodule'

    def __init__(self, name, inputs, outputs, wires, ops):
        self.name = name
        self.inputs = inputs
        self.outputs = outputs
        self.wires = wires
        self.ops = ops

    def write_to_file(self, file):
        with open(file, 'w') as f:
            print(VerilogModule.start_format.format(name=self.name, ports=','.join(self.inputs + self.outputs)), file=f)
            print(VerilogModule.input_format.format(inputs=','.join(self.inputs)), file=f)
            print(VerilogModule.output_format.format(outputs=','.join(self.outputs)), file=f)
            print(file=f)

            print(VerilogModule.wire_format.format(wires=','.join(self.wires)), file=f)
            print(file=f)

            op_counter = {0:0,1:0,2:0,3:0,4:0,5:0}
            for op in self.ops:
                print(op.to_verilog(op_counter[op.operation]), file=f)
                op_counter[op.operation] += 1
            print(file=f)

            print(VerilogModule.end_boiler, file=f)

    @staticmethod
    def from_bench(bench):
        inputs = []
        if bench.includes_dff:
            inputs = ['VDD', 'CK']
        inputs += [s.replace('gat','') for s in bench.inputs]
        outputs = [s.replace('gat','') for s in bench.outputs]
        wires = [s.replace('gat','') for s in bench.signals]

        return VerilogModule(bench.name, inputs, outputs, wires, bench.ops)

# error - function to print errors
def error(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# parse_args - function to parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='Process command line arguments')
    parser.add_argument('input_netlist', help='the input netlist .bench file')
    parser.add_argument('output_verilog', help='the output verilog .v file')
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

    vmod = VerilogModule.from_bench(bench)
    vmod.write_to_file(args.output_verilog)
    

    # print(hope_out)
