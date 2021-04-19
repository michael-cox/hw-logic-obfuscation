#!python3

import argparse
import subprocess
import sys
import os

# -s 500 -r 10 -F faults -l log -U undetected_faults
HOPE_OPTS = ['./hope/hope', '-s', '500', '-r', '10', '-F', 'faults', '-l', 'log', '-U', 'undetected_faults']

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

if __name__ == '__main__':
    args = parse_args()
    hope_out = get_hope_faults(args.input_netlist)
