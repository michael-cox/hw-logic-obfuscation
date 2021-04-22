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

# -r 10 -F faults -l log -N
HOPE_OPTS = ['./hope/hope', '-s', '100', '-r', '10', '-F', 'faults', '-l', 'log', '-N']

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

        operands = [self.assignee.replace('gat', '')] + [op.replace('gat', '') for op in self.operands]
        if self.operation == 5:
            operands = ['CK'] + operands

        return '  {module:<3} {label}_{count}({operands});'.format(
            module = module_name,
            label = LogicOp.op_to_bench(self.operation),
            count = counter,
            operands = ','.join(operands))

class Fault:
    
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
        #sortedZeroFaults = sorted(atZeroFaults.items(), key=operator.itemgetter(1), reverse = True)
        #sortedOneFaults = sorted(atOneFaults.items(), key=operator.itemgetter(1), reverse = True)
       
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

    boiler_format = '# {name}'
    input_format = 'INPUT({gate})'
    output_format = 'OUTPUT({gate})'

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

        for i in range(num_keybits):

            wire = wires[i].split("->", 1)
            key_input = 'K' + str(len(self.key)) + "gat"
            self.inputs.append(key_input)
            new_signal = 'GA' + str(len(self.signals)) + "gat"
            self.signals.append(new_signal)

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


            new_op = LogicOp(new_signal, new_gate_op, [wire[0], key_input])
            
            print(wire)
            #wire = [G16, G22]
            index_to_insert = -1
            if len(wire) >= 2:
                for op_index, op in enumerate(self.ops):
                    if op.assignee == wire[1]:
                        index = op.operands.index(wire[0])
                        op.operands[index] = new_signal
                        if index_to_insert == -1:
                            index_to_insert = op_index
            else:
                for op_index, op in enumerate(self.ops):
                    if wire[0] in op.operands:
                        index = op.operands.index(wire[0])
                        op.operands[index] = new_signal
                        if index_to_insert == -1:
                            index_to_insert = op_index
            if(index_to_insert != -1):
                self.ops.insert(index_to_insert, new_op)




        # insert new key gates as inputs
        # create new wires for each insertion
        # randomly select an XOR or XNOR gate for insertion



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

            op_counter = {0:0,1:0,2:0,3:0,4:0,5:0,7:0,8:0}
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

# need function that 
# -creates test file of base input + generated keys
# -runs hope with test file
# ./hope/hope -f [blank file] -t [generated file] [benchfile]
# -saves correct output then iterates through the "wrong" outputs
# -averages the hemming distance
# netlist = path to netlist
# key = the valid key
def test_hamming(netlist, input_bits, correctKey):
    inputValue = random.randrange(0, (2 ** input_bits) - 1)
    keyValue = int(correctKey, 2)
    inputString = bin(inputValue).replace("0b", "").zfill(input_bits)

    # generate set of keys
    keys = { correctKey }

    testFile = open("testbench", "w")
    testFile.write("1: " + inputString + correctKey + "\n")
    
    for i in itertools.chain(range(2, keyValue), range(keyValue + 1, 2 ** len(correctKey))):
        keyString = bin(i).replace("0b", "").zfill(len(correctKey))
        testFile.write(str(i) + ": " + inputString + keyString + "\n")

    testFile.close()

    # create blank fault file
    # TODO: cleanup files
    subprocess.run(["touch", "fakefaults"])

    hope_args = [ "./hope/hope", "-f", "fakefaults", "-t", "testbench", "-l", "resultlog", netlist]
    hope_results = subprocess.run(hope_args, capture_output = True)

    reggie = re.compile("([01]*)\s*0 faults detected", flags = re.A)

    logFile = open("resultlog", "r")
    logText = logFile.read()
    # get responses and remove the correct key output
    cipher_outputs = reggie.findall(logText)
    correctOutput = cipher_outputs.pop(0)

    # TODO: cleanup files
    return get_hamming_distance(correctOutput, cipher_outputs)


if __name__ == '__main__':
    args = parse_args()
    random.seed()

    bench = Bench.from_file(args.input_netlist)
    fault = Fault.get_faults(bench, args.input_netlist)
    bench.insert_key_gates(fault.atZeroFaults, 10, 0)
    bench.insert_key_gates(fault.atOneFaults, 10, 1)
    print('key = {}'.format(bench.key))
    if args.bench_out:
        bench.write_to_file(args.bench_out)
        hammingResult = test_hamming(args.bench_out, len(bench.inputs), bench.key)
        print("HAMMING = " + str(hammingResult))

    vmod = VerilogModule.from_bench(bench)
    if args.verilog_out:
        vmod.write_to_file(args.verilog_out)
    
        
    # fault.debug_print()
    # print(hope_out)
