from __future__ import print_function

import sys
import h5py
import time
import numpy
import numbers
import operator
import itertools
import functools

import rdflib
from rdflib.namespace import RDF
from rdflib.paths import Path

from collections import defaultdict

import ifc2x3_schema as schema

import query
import query_context
import prefixes

# Just something stupid in case not running in kernprof
if 'line_profiler' not in sys.modules: profile = lambda a: a

class hdf5_instance_reference(object):

    """A representation of an HDF5 entity instance reference. This is a 
    combination of a dataset_id and row. This format is maintained as it 
    allows for efficient identity comparisons. The reference to a population 
    allows for an ifcOwl serialization."""
    
    def __init__(self, population, dsid, instid):
        self.population = population
        self.x = dsid, instid
        self.dsid = dsid
        self.instid = instid
    def __hash__(self):
        return hash(self.x)
    def __eq__(self, other):
        return self.x == other.x
    def __lt__(self, other):
        return (self.dsid, self.instid) < (other.dsid, other.instid)
    def __str__(self):
        return self.population.format_ref_string(*self.x)
    def __repr__(self):
        return "i<%d,%d>" % (self.dsid, self.instid)
    def __len__(self):
        return len(str(self))


class population(object):

    class cached_group_reference(object):
    
        """Makes sure a dataset is read only once and in 
           its entirity, unless it is very big"""
    
        def __init__(self, g):
            self.g = g
            self.c = {}
        def shape_dtype(self, k):
            v = self.c.get(k)
            if v: return v[1], v[2]
            v = self.g[k]
            v2 = [v, v.shape, v.dtype, None]
            self.c[k] = v2
            return v.shape, v.dtype
        @profile
        def data(self, k):
            v = self.c.get(k)
            if v[3] is not None: return v[3]
            if v[1][0] > 1000000:
                # print("Lazy loading", k, file=sys.stderr)
                v[3] = v[0]
            else:
                # print("Fetching", k, file=sys.stderr)
                v[3] = v[0][:]
            return v[3]

    def __init__(self, f):
        self.file = f
        self.population = population.cached_group_reference(self.file['population'])
        self.encoding = self.file['IFC2X3_encoding']
        self.dataset_names = self.encoding.attrs[u'iso_10303_26_data_set_names']
        self.dataset_name_to_id = dict(map(lambda t: t[::-1], enumerate(self.dataset_names)))
        self.instance_reference_type = self.encoding[u"_HDF_INSTANCE_REFERENCE_HANDLE_"].dtype
        self.list_boiler_plate = []
        self.list_index = 1
        
    def format_ref_string(self, dsid, instid):
        if type(dsid) != str: dsid = self.dataset_names[dsid]
        return "%s%s_%d" % (prefixes.INSTANCE, dsid, instid)        
    
    def format_ref(self, dsid, instid):
        return hdf5_instance_reference(self, dsid, instid)
    
    @profile
    def format(self, is_ref, ob, list_range=[None]): #, enum=None, vlen=None):
        tob = type(ob)
    
        if tob == numpy.ndarray:
            # print(tob, ob, file=sys.stderr)
            for x in ob[slice(*list_range)]:
                for y in self.format(is_ref, x): yield y
        elif is_ref:
            yield hdf5_instance_reference(self, ob[0], ob[1])
        elif tob in (str, unicode, numpy.string_):
            yield ob
        # Below slower inheritance checking?
        # elif isinstance(ob, (numpy.integer, numbers.Integral)):
        #     print(tob.__name__, file=sys.stderr)
        #     yield ob
        # elif tob in (numpy.int8, int):
        #     # if enum:
        #     #     # TODO: Performance
        #     #     return "ifc:" + dict(zip(enum.values(), enum.keys()))[ob]
        #     # else:
        #     yield ob
        #     # yield rdflib.term.Literal(ob, datatype="xsd:integer")
        # elif isinstance(ob, (numpy.float, numbers.Real)):
        #     print(tob.__name__, file=sys.stderr)
        #     yield ob
        #     # yield rdflib.term.Literal(ob, datatype="xsd:double")
        # Hackhackhack a bit faster, covers both numpy as well as python datatypes
        elif tob.__name__.startswith("int") or tob.__name__.startswith("float"):
            yield ob
            # q  = map(functools.partial(self.format, is_ref), ob)
            # return q            
            """
                list_uri = ":list_%d" % self.list_index
                for idx, itm in enumerate(ob):
                    item_uri = ":list_%d_%d" % (self.list_index, idx)
                    self.list_boiler_plate.append((list_uri, "list:item", item_uri))
                    self.list_boiler_plate.append((item_uri, "list:listIndex", self.format(False, idx)))
                    self.list_boiler_plate.append((item_uri, "list:listValue", self.format(is_ref, itm)))    
                self.list_index += 1
                return list_uri
            """
        elif tob == rdflib.term.Literal:
            # This occurs when an object is matched directly against a literal in the basic graph pattern
            # 
            # sparql literals are not converted to the appropriate type by rdflib
            # TODO: Find better numeral matching method then based on ttl format string.
            # TODO: Or is there a datatype associated with the literal?
            try: ob = int(ob)
            except:
                try: ob = float(ob)
                except: ob = str(ob)
            tob = type(ob)
            yield ob
        else:
            print (type(ob), ob, file=sys.stderr)
            raise Exception("Bleh")
            
    def query(self, q, context=None):
        if context is None:
            context = query_context.query_context(q)
            
        times = []
        t00 = time.time()
        for x in q:
            t10 = time.time()
            if isinstance(x, query.query.triple):
                context.feed(x, self.triples(x, context))
            else:
                context.filter(x)
            times.append(time.time() - t10)
        
            # context.print_results()
        
        if q.right:
            context2 = query_context.query_context(q.right)
            if q.right.join_type == q.JOIN_TYPE_OPTIONAL or q.right.join_type == q.JOIN_TYPE_JOIN:
                context2.solution = [None] * len(context.solution)
                for i in range(len(context.solution)):
                    if context.solution[i] is not None:
                        context2.solution[i] = context.solution[i][:]
                import copy
                context2.bonds = copy.deepcopy(context.bonds)
            context2 = self.query(q.right, context2)
            context.flatten()
            context2.flatten()
            if q.right.join_type == q.JOIN_TYPE_OPTIONAL:
                context.leftjoin(context2, q.right.join_vars)
            elif q.right.join_type == q.JOIN_TYPE_JOIN:
                context.intersect_2(context2, q.right.join_vars)
            elif q.right.join_type == q.JOIN_TYPE_UNION:
                context.union(context2, q.right.join_vars)
            # horrible just plain horrible code
            times.extend(context2.stats[1])

        context.sort(q.order)
        
        context.stats = time.time() - t00, times
        return context
        
    @profile
    def triples(self, triplefilter=None, context=None):
    
        datasets_included_by_subjects = None
        datasets_included_by_predicate = None
        datasets_included_explicitly = None
        pred_name = None
        pred_isa = False
        list_range = [None]
        
        if triplefilter:
            get_from_context = lambda v: context.get(v, v)
            filter_values = map(get_from_context, triplefilter)
            
            # print ("Filter values")
            # print (filter_values)
            # print ()
            
            if isinstance(filter_values[0], set):
                # datasets_included_by_subjects = set(map(lambda uri: uri.split('_')[0][1:], filter_values[0]))
                datasets_included_by_subjects = set(map(operator.attrgetter('dsid'), filter_values[0]))
                
            to_dsid = lambda t: self.dataset_name_to_id.get(t)
            owl_dt_to_ifc = lambda t: t[len(schema.PREFIX):]
                
            # TODO: Something here for express:hasString, etc.? -- Not here I think.
            # TODO: Predicate path for list containment
            
            # In query.validate() we have asserted that a path is only used to access list elements or select datatypes
            # therefore can simply be set to the IFC predicate, as there is no real distinction in ifc-hdf
            if isinstance(filter_values[1], query.path):
                path = filter_values[1]
                if path.list_accessor:
                    list_range = path.list_range
                filter_values_1 = path.attribute
            else:
                filter_values_1 = filter_values[1]
                
            if filter_values_1.startswith(schema.PREFIX):
                pred_name, pred_name_entity = filter_values_1[len(schema.PREFIX):].split('_')
                pred_name = pred_name[0].upper() + pred_name[1:]
                datasets_included_by_predicate = set(map(to_dsid, schema.subtypes[pred_name_entity]) + [to_dsid(pred_name_entity)])
                           
            # Distinction between filter_values_1 and filter_values[1] not necessary due to equality test
            pred_isa = filter_values[1] == RDF.type
            
            if pred_isa:
                ifct = owl_dt_to_ifc(filter_values[2])
                datasets_included_explicitly = set(map(to_dsid, schema.subtypes[ifct]) + [to_dsid(ifct)])
            else:
                if not isinstance(filter_values[2], rdflib.term.Variable):
                    if type(filter_values[2]) == set:
                        # Set elements are already formatted as they have been emitted before
                        match_ob = filter_values[2]
                        match_ob_fn = lambda v: v in match_ob
                    else:
                        match_ob = next(self.format(False, filter_values[2]))
                        match_ob_fn = lambda v: v == match_ob
                else:
                    match_ob = None
                    match_ob_fn = lambda v: True
                
        else:
            filter_values = None
            match_ob_fn = lambda v: True
            
        datasets_included = reduce(lambda x,y: y if x is None else x if y is None else x & y, (datasets_included_by_subjects, datasets_included_by_predicate, datasets_included_explicitly))

        for dsid, nm in enumerate(self.dataset_names):
            # Some bug?
            if nm in {'IfcPostalAddress', 'IfcPresentationStyleAssignment', 'IfcTrimmedCurve'}: continue
            
            # This is a rdf:type expression, so we no where not to look
            # if datasets_included_explicitly and dsid not in datasets_included_explicitly:
            #     continue
            
            # The subjects are already bound so we no where not to look
            # if datasets_included_by_subjects and nm not in datasets_included_by_subjects: continue
            # if datasets_included_by_subjects and dsid not in datasets_included_by_subjects: 
            #     continue
                
            # if datasets_included_by_predicate and dsid not in datasets_included_by_predicate: 
            #     continue
            
            if datasets_included is not None and dsid not in datasets_included: 
                continue
            
            ds_shape, ds_type = self.population.shape_dtype(nm + "_instances")
            
            # To enumerate instances and their types we do not even need to open the dataset, shape is sufficient
            if pred_isa or triplefilter is None:
                rdf_type = RDF.type
                ifc_nm = "ifc:%s" % nm
                for instid in range(ds_shape[0]):
                    subj = self.format_ref(dsid, instid)
                    yield subj, rdf_type, ifc_nm
                    
                # If filter is not None this means we are filtering on rdf:type no IFC entity attribute can ever fulfil that, so its safe to continue
                if triplefilter is not None: 
                    # print("(%s)"%nm, file=sys.stderr)
                    continue
            
            ds_names = ds_type.names[2:]
            
            # The predicate being filtered on is not part of this entity instance datatype            
            # if pred_name and not schema.attr_dict[nm].get(pred_name): continue
            if pred_name and pred_name not in ds_names: continue
            
            # print(nm, file=sys.stderr)
            
            dts = map(operator.itemgetter(0), sorted(ds_type.fields.values(), key=operator.itemgetter(1)))[2:]
            is_instance_ref = map(lambda f: f == self.instance_reference_type or (f.metadata and 'vlen' in f.metadata and f.metadata['vlen'] == self.instance_reference_type), dts)
            
            ds_data = self.population.data(nm + "_instances")
            lazy = type(ds_data) == h5py.Dataset
            if not lazy:
                ds_data_enum = enumerate(ds_data)
            if filter_values and not isinstance(filter_values[0], rdflib.term.Variable):
                if isinstance(filter_values[0], set):
                    subs_in_ds = filter(lambda x: x.dsid == dsid, filter_values[0])
                    inst_ids = set(map(operator.attrgetter('instid'), subs_in_ds))
                else:
                    raise Exception("I did not expect a single URI reference as subject")
                # print(inst_ids, file=sys.stderr)
                
                if lazy:
                    # TODO, stop encoding this in hashsets, use ranges and binary search sorted lists?
                    sorted_inst_ids = sorted(inst_ids)
                    ds_data_enum = itertools.izip(sorted_inst_ids, ds_data[sorted_inst_ids])
                else:
                    ds_data_enum = ((i, ds_data[i]) for i in inst_ids)
                    # What was I thinking here:
                    # ds_data_enum = filter(lambda a: a[0] in inst_ids, ds_data_enum)

            num_attrs = schema.num_attributes[nm]
            
            for i, (is_ref, dt) in enumerate(zip(is_instance_ref, dts)):
            
                is_inverse = i >= num_attrs
                # Why on earth? Mask is too long?
                # if dt is None: continue
                
                # print(names[i])
                if pred_name and ds_names[i] != pred_name: 
                    continue
                    
                is_select = dt.fields and 'select_bitmap' in dt.fields
                
                for instid, e in ds_data_enum:
                    
                    # hot hot hot loop, very careful here
                    
                    # cast to int because bitwise op on long is much slower in py2
                    mask = int(e[0])
                    is_nonnull = is_inverse or mask & (1 << i)
            
                    # None for inverses due to izip_longer, '1' for non-null forward attrs
                    # if is_null != '0':
                    
                    if is_nonnull:
                    
                        subj = self.format_ref(dsid, instid)
                                        
                        v = e[i+2]
                    
                        if is_select:
                            v = v[v[0]+2]

                        # This does not seem to work.
                        # m = dt.metadata or {}
                        
                        # if list_range:
                        #     for n, v in enumerate(self.format(is_ref, v)):
                        #         if n >= list_range[0] and n < list_range[1] and match_ob_fn(v):
                        #             # import inspect
                        #             # print ("using lambda at:", match_ob_fn.func_code.co_firstlineno)
                        #             # exit()
                        #             yield subj, "ifc:" + (schema.attr_dict[nm][ds_names[i]]), v
                        # else:
                        if True:
                            for v in self.format(is_ref, v, list_range=list_range): #, **m):
                            
                                """
                                if match_ob is not None:
                                    match_object = True
                                    # if not isinstance(filter_values[2], rdflib.term.Variable):
                                    if type(match_ob) == set:
                                        match_object = v in match_ob
                                    else:
                                        match_object = v == match_ob
                            
                                    if not match_object:
                                        # print("Object", v, "not matched")
                                        continue
                                """
                                if match_ob_fn(v):
                                    yield subj, "ifc:" + (schema.attr_dict[nm][ds_names[i]]), v
                                # else:
                                #     print (v)
                            
                        
                        """
                        for x in self.list_boiler_plate:
                            yield x
                            
                        self.list_boiler_plate[:] = []
                        """                        
                        