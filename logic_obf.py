#!python3

import argparse
import subprocess

# -s 500 -r 10 -F faults -l log -U undetected_faults
HOPE_OPTS = ['-s', '500', '-r', '10', '-F', 'faults', '-l', 'log', '-U', 'undetected_faults']

def parse_args():
    parser = argparse.ArgumentParser(description='Process command line arguments')
    parser.add_argument('input_netlist', help='the input netlist .bench file')
    parser.add_argument('output_netlist', help='the output netlist .bench file')
    return parser.parse_args()

def test():
    args = parse_args()
    print(args)

if __name__ == '__main__':
    test()
