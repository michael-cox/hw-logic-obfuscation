#!python3

import argparse
import subprocess
import sys
import os
import re
import pathlib
import operator
import random
import itertools
import math
import copy
import tabulate

# Options for HOPE
HOPE_OPTS = ['./hope/hope', '-s', '100', '-r', '10', '-F', 'faults', '-l', 'log', '-N']

# Regular Expressions for parsing the bench file
INPUT_RE = re.compile('^INPUT\((?P<inputs>\w*)\)', flags=re.A | re.M)
OUTPUT_RE = re.compile('^OUTPUT\((?P<outputs>\w*)\)', flags=re.A | re.M)
OP_RE = re.compile('^(\w*)\s*=\s*(\w*)\((.*)\)', flags = re.M | re.A)

# The gates that need to be added to a Verilog module if it contains a DFF
DFF_GATES = ['VDD', 'CK']


# LogicOp - class containing a testbench style logic operation
# ----------
# assignee - gate that is being assigned to
# operation - string of the operation (e.g. and, nand)
# operands - list of gate parameters
class LogicOp:
    # Format strings for printing
    __bench_format = '{} = {}({})'
    __verilog_format = '  {module:<3} {mod_name}_{count}({gates});'

    # Various operation name translations for the different formats
    __to_op_dict = {
            'AND' : 0,
            'OR' : 1,
            'NOT' : 2,
            'NOR' : 3,
            'NAND' : 4,
            'DFF' : 5,
            'BUF' : 6,
            'XOR' : 7,
            'XNOR' : 8
            }
    __to_bench_dict = dict((v,k) for k,v in __to_op_dict.items())
    __to_verilog_dict = {
            5 : 'FD',
            2 : 'IV',
            4 : 'ND',
            3 : 'NR',
            0 : 'AN',
            1 : 'OR',
            7 : 'XOR',
            8 : 'XNOR'
            }

    def __init__(self, assignee, operation, operands):
        self.assignee = assignee
        self.operation = LogicOp.bench_to_op(operation)
        self.operands = operands

    # Conversion to bench formatted string
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

    # Conversion to Verilog formatted string
    def to_verilog(self, counter):
        module_name = LogicOp.op_to_verilog(self.operation)
        if self.operation != 2:
            module_name += str(len(self.operands))

        operands = [self.assignee.replace('gat', '')] + [op.replace('gat', '') for op in self.operands]
        if self.operation == 5:
            operands = ['CK'] + operands

        return '  {module:<3} {label}_{count}({operands});'.format(
            module = module_name,
            label = LogicOp.op_to_bench(self.operation),
            count = counter,
            operands = ','.join(operands))

class Fault:

    # Initially creates the Fault class that includes the @0 list and the @1 list
    @staticmethod
    def get_faults(bench, netlist):
        faults = get_hope_faults(netlist)
        faultLines = faults.split('\n')

        atZeroFaults = { "0": -1 }
        atOneFaults = { "0": -1 }

        # go through each line at sum up the total faults we find
        for line in faultLines:
            if line == "":
                break

            splitLine = line.split()
          #  print(splitLine)
           
            # we want to skip the header lines and output lines
            if splitLine[0] == "test":
                continue
            elif bench.outputs.count(splitLine[0]) > 0:
                continue
            elif splitLine[2] == "*":
                if splitLine[1] == "/0:":
                    # we use a dictionary method to uniquely key each signal and input with the total count of occurences
                    if atZeroFaults.get(splitLine[0]):
                        atZeroFaults[splitLine[0]] += 1
                    else:
                        atZeroFaults[splitLine[0]] = 1
                elif splitLine[1] == "/1:":
                    if atOneFaults.get(splitLine[0]):
                        atOneFaults[splitLine[0]] += 1
                    else:
                        atOneFaults[splitLine[0]] = 1

        # now we sort them (from greatest to least prevalence)
        sortedZeroFaults = dict(sorted(atZeroFaults.items(), key=lambda item: item[1], reverse = True))
        sortedOneFaults = dict(sorted(atOneFaults.items(), key=lambda item: item[1], reverse = True))

        # now we return the list from top to bottom of the most prevalent faults
        atZeroKeys = []
        atOneKeys = []

        for key in sortedZeroFaults:
            atZeroKeys.append(key)
        for key in sortedOneFaults:
            atOneKeys.append(key)

        return Fault(atZeroKeys, atOneKeys)

    def __init__(self, atZeroFaults, atOneFaults):
        self.atZeroFaults = atZeroFaults
        self.atOneFaults = atOneFaults

    def debug_print(self):
        print(self.atZeroFaults)
        print(self.atOneFaults)

# Bench - class to represent bench netlist
# ----------
# inputs - list of input gates
# outputs - list of output gates
# signals - list of signal gates
# ops - list of LogicOp's in order
class Bench:

    # Format strings for printing
    boiler_format = '# {name}'
    input_format = 'INPUT({gate})'
    output_format = 'OUTPUT({gate})'

    # Create a Bench from a netlist file
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
            includes_dff = False
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
        self.changed_signals = []
        self.key = ''

    def write_to_file(self, file):
        with open(file, 'w') as f:
            print(Bench.boiler_format.format(name=self.name), file=f)
            for gate in self.inputs:
                print(Bench.input_format.format(gate=gate), file=f)
            for gate in self.outputs:
                print(Bench.output_format.format(gate=gate), file=f)
            print(file=f)
            for op in self.ops:
                print(op.to_bench(), file=f)

    def insert_key_gates(self, wires, num_keybits, stuck_at):
        if len(wires) < num_keybits:
            error('Invalid number of key bits')

        # Insert num_keybits number of gates
        for i in range(num_keybits):

            # Split the G37gat->G38gat format
            wire = wires[i].split("->", 1)

            # Create and insert new gates for key bit and new signal
            key_input = 'K' + str(len(self.key)) + "gat"
            self.inputs.append(key_input)
            new_signal = 'GA' + str(len(self.signals)) + "gat"
            self.signals.append(new_signal)

            # Determine the key bit's correct value
            new_gate_op = "XOR" if random.randrange(2) == 1 else "XNOR"
            if stuck_at == 0:
                if new_gate_op == "XOR":
                    self.key += '0'
                else:
                    self.key += '1'
            elif stuck_at == 1:
                if new_gate_op == "XOR":
                    self.key += '0'
                else:
                    self.key += '1'


            # Construct a new operation
            new_op = LogicOp(new_signal, new_gate_op, [wire[0], key_input])
            
            index_to_insert = -1

            # Case 1: G37gat->G38gat
            if len(wire) >= 2 and wire[0] not in self.changed_signals:
                for op_index, op in enumerate(self.ops):
                    if op.assignee == wire[1]:
                        index = op.operands.index(wire[0])
                        op.operands[index] = new_signal
                        if index_to_insert == -1:
                            index_to_insert = op_index

            # Case 2: G38gat
            else:
                for op_index, op in enumerate(self.ops):
                    if wire[0] in op.operands:
                        index = op.operands.index(wire[0])
                        self.changed_signals.append(wire[0])
                        op.operands[index] = new_signal
                        if index_to_insert == -1:
                            index_to_insert = op_index
            if(index_to_insert != -1):
                self.ops.insert(index_to_insert, new_op)

    def debug_print(self):
        print('INPUTS: {}'.format(str(self.inputs)))
        print('OUTPUTS: {}'.format(str(self.outputs)))
        print('SIGNALS: {}'.format(str(self.signals)))
        print('OPS:')
        for op in self.ops: print(LogicOp.to_bench(op))
            
# VerilogModule
# -------------
# Verilog format of a Bench class.
class VerilogModule:
    
    # Format strings for printing
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

            op_counter = {0:0,1:0,2:0,3:0,4:0,5:0,7:0,8:0}
            for op in self.ops:
                print(op.to_verilog(op_counter[op.operation]), file=f)
                op_counter[op.operation] += 1
            print(file=f)

            print(VerilogModule.end_boiler, file=f)

    # Construct from a bench
    @staticmethod
    def from_bench(bench):
        inputs = []
        if bench.includes_dff:
            inputs = ['VDD', 'CK']
        inputs += [s.replace('gat','') for s in bench.inputs]
        outputs = [s.replace('gat','') for s in bench.outputs]
        wires = [s.replace('gat','') for s in bench.signals]
        ops = [op for op in bench.ops if op.operation != 6]

        return VerilogModule(bench.name, inputs, outputs, wires, ops)

# error - function to print errors
def error(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# parse_args - function to parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='Process command line arguments')
    parser.add_argument('input_netlist', help='the input netlist .bench file')
    parser.add_argument('-V', '--verilog', dest='verilog_out', help='specify an output verilog .v file')
    parser.add_argument('-b', '--bench', dest='bench_out', help='specify an output netlist .bench file')
    parser.add_argument('-n', '--nhammings', dest='num_hamm', type=int, default=1, help='specify how many keygate/hamming results to print. if the number specified is greater than the total number of possible hammings, print the max we can.')
    args = parser.parse_args()
    if 'verilog_out' not in args and 'bench_out' not in args:
        error('At least one output file must be specified.')
        parser.print_help()
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

# get_hamming_distance - calculates the hamming distance
# >0.5 if more ciphers different from plaintext
# <0.5 if more ciphers same as plaintext
def get_hamming_distance(correct_output, cipher_outputs):
    big_sum = 0
    for cipher_output in cipher_outputs:
        little_sum = 0
        for correct_bit, cipher_bit in zip(correct_output, cipher_output):
            little_sum += abs(int(correct_bit,2) - int(cipher_bit,2))
        big_sum += little_sum
    return big_sum / (len(correct_output) * len(cipher_outputs))

# test_hamming - generate incorrect keys and simulate using HOPE
def test_hamming(netlist, input_bits, correctKey):
    inputValue = random.randrange(0, (2 ** (input_bits)) - 1)
    inputString = bin(inputValue).replace("0b", "").zfill(input_bits)
    
    # create a test input file to pass into HOPE
    testFile = open("testbench", "w")
    testFile.write("1: " + inputString + correctKey + "\n")

    for i in range(2, 2500):
        keyValue = random.randrange(0, (2 ** len(correctKey)) - 1)
        keyString = bin(keyValue).replace("0b", "").zfill(len(correctKey))
        testFile.write(str(i) + ": " + inputString + keyString + "\n")

    testFile.close()

    # create blank fault file
    subprocess.run(["touch", "fakefaults"])

    # run HOPE with our test input file, our blank fault file, and our new netlist
    hope_args = [ "./hope/hope", "-f", "fakefaults", "-t", "testbench", "-l", "resultlog", netlist]
    hope_results = subprocess.run(hope_args, capture_output = True)

    reggie = re.compile("([01]*)\s*0 faults detected", flags = re.A)

    logFile = open("resultlog", "r")
    logText = logFile.read()
    logFile.close()
    # get responses and remove the correct key output
    cipher_outputs = reggie.findall(logText)
    correctOutput = cipher_outputs.pop(0)

    return get_hamming_distance(correctOutput, cipher_outputs)

# get_best_hamming - calculates the number of key gates that yields the best hamming distance
def get_best_hamming(bench, hammings):

    # test each number of key gates from n = floor(#inputs/2) to #inputs
    for num_keybits in range(math.floor(len(bench.inputs)/2),len(bench.inputs)):
        testbench = copy.deepcopy(bench)
        testbench.insert_key_gates(fault.atZeroFaults, num_keybits, 0)
        testbench.insert_key_gates(fault.atOneFaults, num_keybits, 1)
        keys[num_keybits] = testbench.key
        out_bench = 'tmp_bench.bench'
        testbench.write_to_file(out_bench)
        hammingResult = test_hamming(out_bench, len(testbench.inputs) - len(testbench.key), testbench.key)
        hammings[num_keybits] = abs(hammingResult - 0.5)

    os.remove(out_bench)
    sorted_hammings = [key for key in dict(sorted(hammings.items(), key=lambda item: item[1]))]

    return sorted_hammings

# print_best_hammings - tabulate and print the best hammings results
def print_best_hammings(hammings, sorted_hammings, num_hammings):
    if num_hammings > len(sorted_hammings):
        num_hammings = len(sorted_hammings)

    best_hamm_table = []
    for hamming in range(num_hammings):
        best_hamm_table.append([sorted_hammings[hamming],
            '50% +/- {:.2f}%'.format(hammings[sorted_hammings[hamming]] * 100)])

    print(tabulate.tabulate(best_hamm_table, headers=['# Keybits', 'Hamming Distance']))
    print()

if __name__ == '__main__':
    args = parse_args()
    random.seed()
    hammings = {}
    keys = {}

    # Parse the bench
    bench = Bench.from_file(args.input_netlist)

    # Calculate the testability/fault locations
    fault = Fault.get_faults(bench, args.input_netlist)

    # Optimize the hamming distances as a function of number of key gates
    sorted_hammings = get_best_hamming(bench, hammings)
    
    # Print the results
    print_best_hammings(hammings, sorted_hammings, args.num_hamm)

    # Insert the best number of key gates in our bench
    bench.insert_key_gates(fault.atZeroFaults, sorted_hammings[0], 0)
    bench.insert_key_gates(fault.atOneFaults, sorted_hammings[0], 1)

    # Print the correct key
    print('Key: {}'.format(bench.key))
    print()

    # Write the output file(s)
    if args.bench_out:
        print('Writing output bench to {}...'.format(args.bench_out))
        bench.write_to_file(args.bench_out)

    if args.verilog_out:
        if(args.bench_out): print()
        vmod = VerilogModule.from_bench(bench)
        print('Writing output Verilog Module to {}...'.format(args.verilog_out))
        print('To use this Verilog Module, you will need to import lib.v from the ISCAS directory provided.')
        vmod.write_to_file(args.verilog_out)
    
