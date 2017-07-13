from __future__ import print_function

import sys
import array
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
        elif s.__class__.__name__ == 'bound': return s
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
            
    def project(self):
        vars = [self.vars.index(str(v)) for v in self.proj]
        for v in self:
            yield tuple(v[n] for n in vars)
        
    def __repr__(self, table=False):
        b = StringIO()
        if table:
            self.print_results_table(b)
        else:
            self.print_results(b)
        return b.getvalue()

    @profile
    def intersect_2(self, other, vars):
        raise Exception("Still used?")
        
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
    def intersect(self, A, B, keys):
    
        itemsgetter = lambda ks: lambda v: tuple(v[i] for i in ks)
        g = itemsgetter(keys)
        
        # Decorate-undecorate proved to be slower than re-executing g
        # augment = lambda t: (g(t), t)
        # A = sorted(augment(x) for x in a)
        # B = sorted(augment(x) for x in b)
        # Ag = itertools.groupby(A, operator.itemgetter(0))
        # Bg = itertools.groupby(B, operator.itemgetter(0))
        
        # Bound objects sorted by definition
        if A.__class__.__name__ != "bound":
            A = sorted(A, key=g)
        if B.__class__.__name__ != "bound":
            B = sorted(B, key=g)
        Ag = itertools.groupby(A, g)
        Bg = itertools.groupby(B, g)
        
        r = []
        
        new = tuple.__new__
        T = self.t
        
        try:       
         
            Ak, Ats = next(Ag)
            Bk, Bts = next(Bg)
            while True:
                if Ak == Bk:
                    for x, y in itertools.product(Ats, Bts):
                        # r.append(self.make_tuple1(x, y))
                        r.append(new(T, map(lambda _a, _b: _b if _a is None else _a, x, y)))
                    Ak, Ats = next(Ag)
                    Bk, Bts = next(Bg)
                elif Ak < Bk:
                    Ak, Ats = next(Ag)
                else:
                    Bk, Bts = next(Bg)
                    
        except StopIteration as e:
            pass
        
        return r
        
        # Naive join implementation below


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
        while len(self.bonds) > 1:
            self.merge(self.bonds[0][0], self.bonds[1][0])
        
    @profile        
    def merge(self, x, y, r=None):
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
            if r is None:
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
    def feed(self, filter_, triples):
    
        is_var = tuple(isinstance(x, Variable) for x in filter_)
        names = tuple(b for a, b in zip(is_var, filter_) if a)
        is_var_idxs = [a for a, b in enumerate(is_var) if b]
        
        names = map(self.varnames.get, map(str, names))
        inames = iter(names)
        
        new = tuple.__new__
        T = self.t
        N = len(T._fields)
        
        variable_to_triple_position = map( (lambda v, i: (next(inames), i) if v else (None, None)), is_var, range(3))
        variable_to_triple_position = filter( lambda vs: filter( lambda vs2: vs2 is not None, vs), variable_to_triple_position )

        # variable_to_triple_position = dict(map( (lambda v, i: (next(inames), i) if v else (None, None)), is_var, range(3)))
        # variable_to_triple_position = array.array('i', map(lambda i: variable_to_triple_position.get(i, -1), range(N)))

        # Quicker than map
        fn = self.make_tuple2
        
        # triples = list(triples)
        # print(is_var, names)
        # print(variable_to_triple_position)
        # print(triples[0])
        
        vs_ = [None] * N
        vs = [None] * N

        @profile
        def tuple_contents(t):
            # print(t)
            vs[:] = vs_
            for vpos, tpos in variable_to_triple_position:
                # print(vpos, tpos)
                vs[vpos] = t[tpos]
            return vs
            
            #     for i in range(N):
            #         p = variable_to_triple_position[i]
            #         if p == -1: yield None
            #         else: yield t[p]

        @profile
        def make_tuple2(t):
            return new(T, tuple_contents(t))
        
        # make_tuple2 = lambda t: new(T, [ t[variable_to_triple_position[i]] if variable_to_triple_position.get(i) is not None else None     for i in range(N) ])
        # print(make_tuple2(triples[0]))

        # x = [fn(is_var, names, t) for t in triples]
        
        if type(triples).__name__ == "hdf5_dataset_iterator":
            assert len(variable_to_triple_position) == 1
            x = triples.bind(T, variable_to_triple_position[0][0])
        else:
            x = [new(T, tuple_contents(t)) for t in triples]
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
        
            # Try to prevent a cartesian product here
            x_, y_ = names
            for i_, b_ in enumerate(self.bonds):
                if x_ in b_: bx = i_
                if y_ in b_: by = i_
            x3 = None
            
            # print(filter_)
            # print("bx", bx, "by", by, "names", names)
            # print("bonds", self.bonds)
            
            # sorted(names) == sorted((bx, by)) and ?
            if bx != by and None not in (self.solution[bx], self.solution[by]):
                k = set(names) & set(self.bonds[bx])
                x2 = self.intersect(self.solution[bx], x, keys=k)
                k = set(names) & set(self.bonds[by])
                x3 = self.intersect(self.solution[by], x2, keys=k)
                        
            i, b, s = self.merge(*names, r=x3)
            
        if s is None:
            self.solution[i] = x
        else:
            y = self.solution[i]
            # TODO: b is only the original bin and not the combined tuple, is this an issue?
            k = set(names) & set(b)
            self.solution[i] = self.intersect(y, x, keys=k)

            