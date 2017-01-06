from __future__ import print_function

import sys
import h5py
import time

import query
import population

VERBOSE = "-v" in sys.argv
if VERBOSE: 
    sys.args.remove("-v")

print_section = lambda s,q: (print("\n"+s), print('-'*len(s)), print(q))

query_text = open(sys.argv[2]).read()
q = query.query(query_text)
if VERBOSE: print_section("Original query:", q)
q.merge_paths()
if VERBOSE: print_section("Merged query:", q)
q.infer()
if VERBOSE: print_section("Augmented query:", q)
q.sort()
if VERBOSE: print_section("Sorted query:", q)

t0 = time.time()
pop = population.population(h5py.File(sys.argv[1], "r"))
t1 = time.time()
results = pop.query(q)
print_section("Results:", results)
t2 = time.time()

if VERBOSE: print_section("Statistics:", results.format_statistics())


print("Parse time: %.3f sec" % (t1-t0), file=sys.stderr)
print("Query time: %.3f sec" % (t2-t1), file=sys.stderr)
