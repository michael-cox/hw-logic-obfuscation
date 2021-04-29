# Logic Obfuscation
This is a final project for ECE459 Hardware security. This script takes a
netlist of ISCAS85 circuits and places keygates in it to obfuscate logic when
the correct key is not present.

## Dependencies
The only required package is tabulate, which can be installed with:
```pip install tabulate```

## Usage
```
usage: logic_obf.py [-h] [-V VERILOG_OUT] [-b BENCH_OUT] [-n NUM_HAMM] input_netlist

Process command line arguments

positional arguments:
  input_netlist         the input netlist .bench file

optional arguments:
  -h, --help            show this help message and exit
  -V VERILOG_OUT, --verilog VERILOG_OUT
                        specify an output verilog .v file
  -b BENCH_OUT, --bench BENCH_OUT
                        specify an output netlist .bench file
  -n NUM_HAMM, --nhammings NUM_HAMM
                        specify how many keygate/hamming results to print. if the number specified is greater than the total number of
                        possible hammings, print the max we can.
```

## Notes
To import a Verilog module to Vivado, you must include the `lib.v` file
provided with the ISCAS zip. In our circuits, there is one bench that
contains a `NAND` with 8 operands, which translates into an `ND8` operation
in Verilog. `lib.v` does not implement this module, but this should be an
easy manual fix by implementing and including an `ND8` module.
