from collections import defaultdict

# This cannot be a package when using cProfile
# import schemas.ifc2x3
# schema = schemas.ifc2x3.schema

import nodes
import ifc2x3
schema = ifc2x3.schema

attr_dict = {}
subtypes = defaultdict(set)
domains = {}
ranges = {}
numeric = {}
num_attributes_ = {}
list_attributes = set()
wrapped_attributes = set()

for k, v in schema.entities.items(): 
    attr_dict[k] = {}
        
    attrs = v.attributes
    num_attributes_[k] = len(attrs)
    if v.inverse: attrs += v.inverse.elements
    for a in attrs:
        ifcowl_name = '%s_%s' % (a.name[0].lower() + a.name[1:], k)
        
        is_wrapped = False
        at = a.type
        while at in schema.types:
            is_wrapped = True
            at = schema.types[at].type.type
            
        if at in {"integer", "number", "real", "string", "binary", "boolean"}:
            if at in {"integer", "number", "real"}:
                numeric[ifcowl_name] = True
        else:
            is_wrapped = False

        attr_dict[k][a.name] = ifcowl_name
    
        domains[ifcowl_name] = k
        if a.type in schema.entities:
            ranges[ifcowl_name] = a.type
            
        if isinstance(at, nodes.AggregationType):
            if at.aggregate_type in {'list', 'array'}:
                list_attributes.add((k, a.name))
            
            while isinstance(at, nodes.AggregationType):
                at = at.type
                
            # Repeat boxing check for element type of aggregate
            is_wrapped = False
            while at in schema.types:
                is_wrapped = True
                at = schema.types[at].type.type
            is_wrapped = is_wrapped and at in {"integer", "number", "real", "string", "binary", "boolean"}
                
        if is_wrapped:
            wrapped_attributes.add((k, a.name))
            
    if v.supertypes:
        subtypes[v.supertypes[0]].update([k])
    
num_attributes = dict(num_attributes_)
        
for k, v in schema.entities.items():
    while v.supertypes:
        attr_dict[k].update(attr_dict[v.supertypes[0]])
        num_attributes[k] += num_attributes_[v.supertypes[0]]
        v = schema.entities[v.supertypes[0]]
        
del num_attributes_
        
added = True
while added:
    added = False
    for a, bs in list(subtypes.items()):
        l = len(subtypes[a])
        n = set()
        for b in bs:
            n.update(subtypes[b])
        subtypes[a].update(n)
        if not added and len(subtypes[a]) > l: added = True
    if not added: break

PREFIX = 'http://ifcowl.openbimstandards.org/IFC2X3_TC1#'
