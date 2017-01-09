from __future__ import print_function

import sys
import operator
import itertools
import functools

from collections import namedtuple, defaultdict
from cStringIO import StringIO

from rdflib.term import Variable

# Just something stupid in case not running in kernprof
if 'line_profiler' not in sys.modules: profile = lambda a: a

class query_context(object):
    
    def __init__(self, query):
        self.query = query
        self.vars = sorted(map(str, query.vars))
        self.proj = query.proj
        self.l = len(self.vars)
        self.varnames = dict((b, a) for a, b in enumerate(self.vars))
        self.t = namedtuple('query_result', self.vars)
        self.solution = [None for i in self.vars]
        self.bonds = map(lambda n: (n,), range(len(self.vars)))
        
    @profile
    def get(self, k, default=None):
        n = self.varnames.get(str(k))
        if n is None: 
            return default
        for i, b in enumerate(self.bonds):
            if n in b:
                s = self.solution[i]
                break
        if s is None: return default
        else: return set(map(operator.itemgetter(n), s))
            
    # TODO: Should probably throw
    __getitem__ = get
    
    def print_statistics(self, output=None):
        if output is None: output = sys.stdout
        def _(qry, offset=0):
            for q, t in zip(qry, self.stats[1][offset:]):
                ML = 60
                q = str(q)
                if len(q) > ML + 3: q = q[0:ML] + "..."
                if len(q) < ML + 3: q = q + " " * (ML + 3 - len(q))
                print("%s | %.2f seconds" % (q, t), file=output)
                offset += 1
            if qry.right:
                print("-" * 10, file=output)
                _(qry.right, offset)
        _(self.query)
        print("\nQuery took %.2f seconds" % self.stats[0], file=output)
        
    def format_statistics(self):
        b = StringIO()
        self.print_statistics(b)
        return b.getvalue()

    def sort(self, by):
        for s in self.solution:
            if s is None: continue
            for var, desc in by[::-1]:
                idx = self.varnames[str(var)]
                s[:] = sorted(s, key=operator.itemgetter(idx), reverse=desc==-1)
    
    def print_results_table(self, output=None, all=False):
        if output is None: output = sys.stdout
        
        vs = list(self)
        get_col = lambda c: [v[c] for v in vs]
        get_col_by_name = lambda c: [getattr(v, c) for v in vs]
        
        # Not needed any more
        custom_len = lambda v: len(v.n3()) if hasattr(v, 'n3') else len(v)
        max_or_default = lambda d: lambda vs: max(vs) if len(vs) else d

        get_len = lambda vs: max_or_default(0)(map(len, vs))
        # Also serializes to n3
        filter_none = lambda vs: ["" if v is None else v.n3() if hasattr(v, 'n3') else v for v in vs]
        
        if all:
            cols = map(filter_none, map(get_col, range(len(self.vars))))
        else:
            cols = map(filter_none, map(get_col_by_name, self.proj))
            
        vars = self.vars if all else self.proj
        
        lens = map(get_len, cols)
        len2 = map(len, vars)
        lens = [max(a,b) for a,b in zip(lens, len2)]
        
        put = lambda s: print(s, file=output, end="")
        put_val = lambda v, l: put('| %s%s ' % (v or "", ' ' * (l - (len(v) if v is not None else 0))))
        
        def horizontal_separator():
            for l in lens:
                put('+')
                put('-'*(l+2))
            put('+\n')
            
        horizontal_separator()
        
        for vl in zip(vars, lens):
            put_val(*vl)
        put('|\n')
        
        horizontal_separator()
        
        for r in zip(*cols):
            for vl in zip(r, lens):
                put_val(*vl)
            put('|\n')

        horizontal_separator()
        
    def print_results(self, output=None):
        if output is None: output = sys.stdout
        vars = [self.vars.index(str(v)) for v in self.proj]
        for v in self:
            print(" ".join(str(v[n]) for n in vars), file=output)
        
    def __repr__(self, table=False):
        b = StringIO()
        if table:
            self.print_results_table(b)
        else:
            self.print_results(b)
        return b.getvalue()

    @profile
    def intersect_2(self, other, vars):
        assert len(self.solution) == 1
        assert len(other.solution) == 1

        names = sorted(map(self.varnames.get, map(str, vars)))
        itemsgetter = lambda ks: lambda v: tuple(v[i] for i in ks)
        g = itemsgetter(names)

        a_subset = defaultdict(list)
        b_subset = defaultdict(list)
        for x in self.solution[0]:
            a_subset[g(x)].append(x)
        for x in other.solution[0]:
            b_subset[g(x)].append(x)

        common_keys = set(a_subset.keys()) & set(b_subset.keys())

        r = []

        for k in common_keys:
            for x, y in itertools.product(a_subset[k], b_subset[k]):
                r.append(self.make_tuple1(x, y))

        # TODO: Immutable
        self.solution[0][:] = r
        
    @profile
    def leftjoin(self, other, vars):
        assert len(self.solution) == 1
        assert len(other.solution) == 1
        
        names = sorted(map(self.varnames.get, map(str, vars)))
        itemsgetter = lambda ks: lambda v: tuple(v[i] for i in ks)
        g = itemsgetter(names)

        a_subset = defaultdict(list)
        b_subset = defaultdict(list)
        for x in self.solution[0]:
            a_subset[g(x)].append(x)
        for x in other.solution[0]:
            b_subset[g(x)].append(x)

        r = []

        for k, a_subset_k in a_subset.iteritems():
            for x, y in itertools.product(a_subset_k, b_subset[k]):
                r.append(self.make_tuple1(x, y))
                
        # TODO: Immutable
        self.solution[0][:] = r

    @profile
    def intersect(self, a, b, keys):
        itemsgetter = lambda ks: lambda v: tuple(v[i] for i in ks)
        g = itemsgetter(keys)

        # Fixed: here duplicates are merged
        # a_subset = dict(zip(map(g, a), a))
        # b_subset = dict(zip(map(g, b), b))

        a_subset = defaultdict(list)
        b_subset = defaultdict(list)
        for x in a:
            a_subset[g(x)].append(x)
        for x in b:
            b_subset[g(x)].append(x)

        common_keys = set(a_subset.keys()) & set(b_subset.keys())

        r = []

        for k in common_keys:
            for x, y in itertools.product(a_subset[k], b_subset[k]):
                r.append(self.make_tuple1(x, y))

        # TODO: Isn't it enough to iterate over cartesian products of values in (a|b)_subset. Why iterate over original lists?
        # for x in a:
        #     x_in_b = b_subset.get(g(x))
        #     if x_in_b is not None:
        #         r.append(self.make_tuple1(x, x_in_b))
        #
        # emitted_from_a = set(r)
        #
        # for x in b:
        #     x_subset = g(x)
        #     x_in_a = a_subset.get(x_subset)
        #     if x_in_a is not None:
        #         # TODO: Does this needs to be reversed?
        #         t = self.make_tuple1(x, x_in_a)
        #         if t not in emitted_from_a:
        #             r.append(t)
            
        return r

    @profile    
    def make_tuple1(self, a, b=None):
        # Hack for map over itertools.product
        if b is None: a, b = a
        d = list(a)
        for i, r in enumerate(b):
            if r is not None: d[i] = r
        return self.t(*d)
     
    @profile    
    def make_tuple2(self, v, n, spo):
        d = [None] * len(self.vars)
        for k, v in zip(n, [x for v, x in zip(v, spo) if v]):
            d[k] = v
        return self.t(*d)
        
    def flatten(self):
        print(self.bonds)
        while len(self.bonds) > 1:
            self.merge(self.bonds[0][0], self.bonds[1][0])
        print(self.bonds)
        
    @profile        
    def merge(self, x, y):
        # See if there is already a connection established between the two variables
        for i, b in enumerate(self.bonds):
            if x in b and y in b:
                return i, b, self.solution[i]

        # Find the two bins in which the variables are allocated
        for i, b in enumerate(self.bonds):
            if x in b: bx = i
            elif y in b: by = i
            
        sx, sy = self.solution[bx], self.solution[by]
        if sx is None:
            r, b = sy, self.bonds[by]
        elif sy is None:
            r, b = sx, self.bonds[bx]
        else:
            r = map(self.make_tuple1, itertools.product(sx, sy))
            b = tuple(sorted(set(self.bonds[bx]) | set(self.bonds[by])))
            
        mins, maxs = min(bx, by), max(bx, by)
        self.solution[maxs:maxs+1] = []
        self.bonds[mins] = tuple(sorted(self.bonds[bx] + self.bonds[by]))
        self.bonds[maxs:maxs+1] = []
        self.solution[mins] = r
        return mins, b, r
        
    def __iter__(self):
        return itertools.chain(*map(iter, filter(lambda s: s is not None, self.solution)))
        
    def filter(self, f):
        var_ids = map(self.varnames.get, map(str, f.vars))
        if len(var_ids) == 1:
            for idx, b in enumerate(self.bonds):
                if var_ids[0] in b:
                    self.solution[idx] = filter(f, self.solution[idx])
                    break
        elif len(var_ids) == 2:
            idx, _, sln = self.merge(*var_ids)
            self.solution[idx] = filter(f, sln)
        else:
            raise Exception("Not implemented")
     
    @profile     
    def feed(self, filter, triples):
    
        is_var = tuple(isinstance(x, Variable) for x in filter)
        names = tuple(b for a, b in zip(is_var, filter) if a)
        is_var_idxs = [a for a, b in enumerate(is_var) if b]
        
        names = map(self.varnames.get, map(str, names))
        
        # Quicker than map
        fn = self.make_tuple2
        x = [fn(is_var, names, t) for t in triples]
        # x = map(functools.partial(self.make_tuple2, is_var, names), triples)
                
        if len(names) == 0 or len(names) == 3:
            raise Exception("Unsupported")
        elif len(names) == 1:
            n = names[0]
            for i, b in enumerate(self.bonds):
                if n in b:
                    s = self.solution[i]
                    break
        else:
            i, b, s = self.merge(*names)
            
        if s is None:
            self.solution[i] = x
        else:
            y = self.solution[i]
            # TODO: b is only the original bin and not the combined tuple, is this an issue?
            k = set(names) & set(b)
            self.solution[i] = self.intersect(y, x, keys=k)

            