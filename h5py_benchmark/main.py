import sys
import time
import h5py

f = h5py.File(sys.argv[1])

def enumerate_sizes():
    for w in f["population/IfcWindow_instances"][:]:
        yield w['OverallWidth'] * w['OverallHeight']

t0 = time.time()
size = max(enumerate_sizes())
t1 = time.time()

print("largest window size: %f" % size)
print("time spent: %.5f" % (t1 - t0))
