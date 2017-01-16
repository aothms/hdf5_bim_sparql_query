from __future__ import print_function

import operator
import functools
import collections

import ifc2x3_schema as schema
import prefixes

import rdflib.plugins.sparql as sparql
from rdflib.namespace import RDF, XSD
from rdflib.term import Variable, Literal, URIRef, BNode
from rdflib.paths import Path, SequencePath, MulPath

class path(object):
    unboxes = False
    list_accessor = False
    list_range = None
    attribute = None
    
    INF = float("inf")
    
    def __repr__(self):
        s = "ifc:%s" % self.attribute[len(schema.PREFIX):]
        if self.list_accessor:
            s += "[%d:%d]" % self.list_range
        if self.unboxes:
            s += "/expr:getValue"
        return s
        
    # Forward startswith and slicing to self.attribute for triple sorting
    def __getitem__(self, x):
        return self.attribute[x]
        
    def startswith(self, s):
        return self.attribute.startswith(s)
    
    def __init__(self, path, is_list=False, is_boxed=False):
        self.p, self.is_list, self.is_boxed = path, is_list, is_boxed
        self.validate()
        
    def validate(self):
        p = self.p
    
        # Needs to be a SequencePath of list_attribute/hasNext*/hasContents
        # TODO: Option to refer to specific index (e.g Z-coordinate of point)
        assert isinstance(p, SequencePath), "Path root should be a sequence"
        assert isinstance(p.args[0], URIRef), "Path root first node should be a schema attribute that points to a list"
        assert p.args[0].startswith(schema.PREFIX), "Path root first node should be a schema attribute that points to a list"
        
        # TODO: probably should be boxed, just like in ifcowl, as otherwise it is not possible to retrieve the exact type, other than, say, string, which is serialized as part of the hdf5 model.
        self.is_list or self.is_boxed, "Path root first node should be a schema attribute that points to a list or boxed attribute"
        
        self.attribute = p.args[0]
        components = p.args[1:] # peel off IFC attribute
        
        if self.is_boxed:
            assert components[-1] in prefixes.EXPRESS_DATATYPES, "Path root last node should be an express datatype accessor"
            components = components[:-1] # peel off unboxing
            self.unboxes = True
        
        if self.is_list:
            assert components[-1] == prefixes.list.hasContents, "Path root last node should be contents"
            components = components[:-1] # peel off list contents
            
            min_elem, max_elem = 0, 0
            
            for pp in components:
                if pp == prefixes.list.hasNext:
                    min_elem += 1
                    max_elem += 1
                elif isinstance(pp, MulPath):
                    assert pp.path == prefixes.list.hasNext, "Path root second node should be a multiplication of next"
                    assert pp.mod == '*', "Path root second node should be a multiplication of next"
                    
            self.list_accessor = True
            # +1 to account for python slice() syntax
            self.list_range = (min_elem, max_elem + 1)

class query(object):

    IFC_PREFIX = 'http://ifcowl.openbimstandards.org/IFC2X3_TC1#'

    JOIN_TYPE_JOIN = 1
    JOIN_TYPE_OPTIONAL = 2
    JOIN_TYPE_UNION = 3

    class statement(object): 
        def key(self, **kwargs):
            return type(self).key(self, **kwargs)
    
    class filter(statement):
        
        def _make_Builtin_REGEX(self, expr):
            import re
            
            assert map(type, (expr.text, expr.flags, expr.pattern)) == [Variable, Literal, Literal]
            
            flags = 0
            for f in expr.flags:
                flags |= {
                    'i': re.IGNORECASE
                }[f]
            
            pat = re.compile(expr.pattern, flags=flags)
            k = expr.text
            
            self.fn = lambda t: pat.search(getattr(t, k)) is not None
            self.s = "F(?%s) -> {0,1} { ?%s %% /%s/%s }" % (expr.text, expr.text, expr.pattern, expr.flags)
            self.vars = {k}

        def _make_RelationalExpression(self, expr):

            opfn = getattr(operator, {
                '>' : 'gt',
                '<' : 'lt',
                '>=': 'ge',
                '<=': 'le',
                '=' : 'eq'
            }[expr.op])
            args = (expr.expr, expr.other)
            is_var = [isinstance(x, Variable) for x in args]
            s0, s1 = map(str, args)
            a0, a1 = map(lambda v: v.value if isinstance(v, Literal) else None, args)
            
            self.vars = set(x for x in args if isinstance(x, Variable))
            varnames_c = ",".join("?%s" % v for v in self.vars)
            
            if all(is_var): 
                self.fn = lambda t: opfn(getattr(t, s0), getattr(t, s1))
                self.s = "F(%s) -> {0,1} { ?%s %s ?%s }" % (varnames_c, s0, expr.op, s1)
            elif is_var[0]:
                self.fn = lambda t: opfn(getattr(t, s0), a1)
                self.s = "F(%s) -> {0,1} { ?%s %s %.2f }" % (varnames_c, s0, expr.op, a1)
            elif is_var[1]:
                self.fn = lambda t: opfn(a0, getattr(t, s1))
                self.s = "F(%s) -> {0,1} { %.2f %s ?%s }" % (varnames_c, a0, expr.op, s1)
            else: raise Exception("Not supported")
            
            
            
        def __init__(self, q, expr):
            getattr(self, "_make_%s" % expr.name)(expr)
            
        def key(self, known_variables, variable_ref_count):
            inf = float("inf")
            return (
                (-inf if self.vars < known_variables else +inf),
            )
            
        def __repr__(self):
            return self.s
            
        def __call__(self, t):
            return self.fn(t)
            
    class triple(statement):
        
        def __init__(self, q, spo):
            self.q, self.spo = q, spo
            self.vars = set(x for x in self.spo if isinstance(x, Variable))
            
        def key(self, known_variables, variable_ref_count):
            # Adapted from rdflib
            is_unknown_variable = lambda v: v not in known_variables and isinstance(v, (Variable, BNode))
            fns = [
                # Triples with unknown variables are pushed to the back
                (lambda spo: len(filter(is_unknown_variable, spo))),
                
                # Variables with many references are pushed to the front
                # This is detrimental in our tests
                # (lambda spo: -sum(variable_ref_count[v] for v in spo)),
                
                # Type statements are pushed to the front as they can quickly rule out datasets in HDF5
                (lambda spo: spo[1] != RDF.type),
                
                # Statements with literals are pushed to the front
                (lambda spo: not isinstance(spo[2], Literal)),
                
                # Statements with numeric literals are pushed even more to the front
                # This also does not help much
                # (lambda spo: not (isinstance(spo[2], Literal) and spo[2].datatype in {XSD.decimal, XSD.integer, XSD.float})),
                
                # Statements refering to a numeric type IFC attribute are pushed to the front
                # TODO: Check if the type check doesn't break anything
                (lambda spo: isinstance(spo[1], Path) or (not spo[1].startswith(query.IFC_PREFIX) or schema.numeric.get(str(spo[1][len(query.IFC_PREFIX):])) is None)),
            ]
            k = tuple(fn(self.spo) for fn in fns)
            # print(self, k)
            return k
            
        def __repr__(self):
            def fmt(x):
                if isinstance(x, Literal): return '"%s"' % x
                elif isinstance(x, path): return str(x)
                elif isinstance(x, Path): return self.q.format_path(x)
                try: a,b,c = self.q.ns.compute_qname(x)
                except: return "?%s" % x
                return "%s:%s" % (a,c)
            return " ".join(map(fmt, self.spo))
        
        def __iter__(self):
            return iter(self.spo)
            
    def merge_paths(self):
        
        def statement_by_x(index, X):
            for x in self.statements:
                if isinstance(x, query.triple):
                    if tuple(x)[index] == X: yield x
                    
        statement_by_subject = functools.partial(statement_by_x, 0)
        statement_by_object = functools.partial(statement_by_x, 2)
                    
        merged = True
        while merged:
            merged = False
            for x in self.statements:
                if isinstance(x, query.triple):
                    s,p,o = x
                    if not isinstance(p, Path):
                        if p.startswith(prefixes.EXPRESS) or p.startswith(prefixes.LIST):
                            S = list(statement_by_object(s))
                            # assert len(S) == 1
                            to_append, to_remove = [], []
                            for s2p2o2 in S:
                                s2, p2, o2 = s2p2o2
                                if isinstance(p2, SequencePath):
                                    # mutable
                                    p2.args.append(p)
                                    to_append.append(query.triple(self, (s2, p2, o)))
                                else:
                                    to_append.append(query.triple(self, (s2, SequencePath(p2, p), o)))
                                if list(statement_by_subject(o2)) == [x]:
                                    to_remove.append(s2p2o2)
                                else:
                                    pass
                                    # print("Not removing", s2p2o2, "because of", list(statement_by_subject(o2)))
                                to_remove.append(x)
                                
                            # print("old\n---")
                            # print(self)
                                
                            self.statements.extend(to_append)
                            for tr in to_remove:
                                self.statements.remove(tr)
                                
                            # print("new\n---")
                            # print(self)
                                
                            merged = True
                            break
            
    def validate(self):
        """
        Validate some requirements pertaining to list constructs
        """
        
        # Check and decorate paths
        def _():
            for x in self.statements:
            
                if isinstance(x, query.triple):
                    s,p,o = x
                
                    if isinstance(p, Path) or p.startswith(schema.PREFIX):
                        if isinstance(p, Path):
                            pred_name, pred_name_entity = p.args[0][len(schema.PREFIX):].split('_')
                        else:
                            pred_name, pred_name_entity = p[len(schema.PREFIX):].split('_')
                        pred_name = pred_name[0].upper() + pred_name[1:]
                        attribute_is_list = (pred_name_entity, pred_name) in schema.list_attributes
                        attribute_is_boxed = (pred_name_entity, pred_name) in schema.wrapped_attributes
                        if attribute_is_list: attribute_is_boxed = True
                    
                    if isinstance(p, Path):                
                        p = path(p, is_list=attribute_is_list, is_boxed=attribute_is_boxed)                   
                        
                    elif p.startswith(schema.PREFIX):
                        # List and boxed attributes need to be references as a property path
                        assert not attribute_is_list, "%s.%s is a list, which should be referenced by a predicate path" % (pred_name_entity, pred_name)
                        assert not attribute_is_boxed, "%s.%s is a boxed attribute, which should be referenced by a predicate path" % (pred_name_entity, pred_name)
                        
                    x = query.triple(x.q, (s,p,o))
                    
                yield x
                
        self.statements = list(_())
            
    def infer(self):
        type_statements = {}
        general_statements = collections.defaultdict(list)
        triple_statements = filter(lambda s: isinstance(s, query.triple), self.statements)
    
        def infer_():
            for s,p,o in triple_statements:
                if isinstance(s, Variable) and p == RDF.type:
                    type_statements[s] = o
                else:
                    general_statements[s].append(p)
        
            for s,p,o in triple_statements:
                
                # No extra triples infered based on predicate paths
                # FIXME: Update
                if isinstance(p, Path): continue
                
                if p.startswith(query.IFC_PREFIX) and isinstance(o, Variable) and o not in type_statements:
                    p = p[len(query.IFC_PREFIX):]
                    r = schema.ranges.get(p)
                    
                    if not r: continue
                    
                    # All too often a variable that is subject of an expression has already a predicate by which more narrow
                    # filtering can occur. Adding an explicit type statement then yields a detrimental additional set comparison.
                    def type_cardinality_induced():
                        for p in general_statements[o]:
                            if p.startswith(query.IFC_PREFIX):
                                type_induced = p[len(query.IFC_PREFIX):].split('_')[1]
                                yield len(schema.subtypes[type_induced])
                                
                    try: # < for min() of empty sequence
                        # TODO: lesseq seems to remove some very detrimental optimization results. Verify?
                        if min(type_cardinality_induced()) <= len(schema.subtypes[r]):
                            continue
                    except: pass
                    
                    # print "INFERED %s %s %s BECAUSE %s %s %s" % (o, RDF.type, URIRef(query.IFC_PREFIX+r), s, p, o)
                    
                    yield o, RDF.type, URIRef(query.IFC_PREFIX+r)
        
        self.statements.extend(map(self.make_triple, infer_()))
                
    def sort(self):
        # Adapted from rdflib
        known_variables = set()
        variable_ref_count = collections.defaultdict(int)
        
        for x in self.statements:
            for c in x.vars:
                variable_ref_count[c] += 1

        fn = functools.partial(query.statement.key, 
            known_variables=known_variables,
            variable_ref_count=variable_ref_count)
        
        s = list(self.statements)
        def sort_(known_variables):
            for i in range(len(s)):
                e = min(s, key=fn)
                known_variables |= e.vars
                s.remove(e)
                yield e

        self.statements = list(sort_(known_variables))
    
    def __init__(self, query_text=None, bgp=None):
        self.parent = None
        self.order = []
        self.right = None
        self.proj = None
    
        if query_text:
            asn = sparql.parser.parseQuery(query_text)
            q = sparql.algebra.translateQuery(asn)
            self.ns = q.prologue.namespace_manager
            project = q.algebra['p']
            self.vars = project._vars
            # print("vars", self.vars)
            self.proj = project['PV']
            
            bgp = project['p']

        self.make_triple = functools.partial(query.triple, self)
        self.make_filter = functools.partial(query.filter, self)
        
        def make_order(expr):
            assert isinstance(expr.expr, Variable)
            return (expr.expr, 1 if expr.order == 'ASC' else -1)
            
        self.statements = []
            
        def recurse(query_instance, asn):
            
            if asn.name == 'OrderBy':
                query_instance.order = map(make_order, asn.expr)
                recurse(query_instance, asn.p)
            elif asn.name == 'BGP':
                query_instance.statements += map(query_instance.make_triple, asn.triples)
            elif asn.name == 'Filter':
                expr = asn.expr
                def visit(expr):
                    if expr.name == 'ConditionalAndExpression':
                        for x in visit(expr.expr): yield x
                        for x in expr.other: 
                            for y in visit(x): yield y
                    else: yield expr
                
                query_instance.statements += map(query_instance.make_filter, visit(expr))
                recurse(query_instance, asn.p)
            elif asn.name == 'LeftJoin' or asn.name == 'Join' or asn.name == 'Union':
                recurse(query_instance, asn.p1)
                query_instance.right = query(bgp=asn.p2)
                query_instance.right.join_type = {
                    'LeftJoin': query.JOIN_TYPE_OPTIONAL,
                    'Join'    : query.JOIN_TYPE_JOIN,
                    'Union'   : query.JOIN_TYPE_UNION
                }[asn.name]
                query_instance.right.parent = query_instance
                query_instance.right.ns = query_instance.ns
                # Seems that this can be copied as parent graph contains also optional child graphs
                query_instance.right.vars = query_instance.vars
                query_instance.right.join_vars = asn.p1._vars & asn.p2._vars
            else:
                for k in asn.keys():
                    print(k)
                    print(asn[k])
                raise ValueError("Query block of type <%s> not understood" % asn.name)

        recurse(self, bgp)
        
        #    ?wt ifc:name_IfcRoot ?x .
        #    ?x express:hasString "1000 x 1000" .
        #              to
        #    ?wt ifc:name_IfcRoot/express:hasString "1000 x 1000" .
        
        self.merge_paths()
        
        # Necesssary as it also decorates property paths
        self.validate()

        """
        if bgp.name == 'OrderBy':
            self.order = map(make_order, bgp.expr)
            bgp = bgp['p']
        else:
            self.order = []

        if bgp.name == 'BGP':
            self.statements = map(self.make_triple, bgp['triples'])
        elif bgp.name == 'Filter':
            expr = bgp['expr']
            def visit(expr):
                if expr.name == 'ConditionalAndExpression':
                    for x in visit(expr.expr): yield x
                    for x in expr.other: 
                        for y in visit(x): yield y
                else: yield expr
            
            self.statements = map(self.make_triple, bgp['p']['triples']) + \
                              map(self.make_filter, visit(expr))
        else:
            for k in bgp.keys():
                print k
                print bgp[k]
            raise ValueError("Query block of type <%s> not understood" % bgp.name)
        """
        
    def __iter__(self):
        return iter(self.statements)

    def __repr__(self):
        indentation = 2 if self.parent else 0
        s = ("\n%s" % ((' ')*indentation)).join(map(lambda s: "%r ." % s, self.statements))
        if self.right:
            s += "\noptional {\n%s%s\n}" % ((' ')*(indentation+2), self.right)
        return s

    def format_path(self, p):
        """
        Works on only a limited amount of cases, work-around
        for lack of n3() method in rdflib <= v4.2.1
        """
        if isinstance(p, SequencePath):
            return "/".join(map(self.format_path, p.args))
        elif isinstance(p, MulPath):
            return self.format_path(p.path) + p.mod
        elif isinstance(p, URIRef):
            a,b,c = self.ns.compute_qname(p)
            return "%s:%s" % (a,c)
        else: return ""
