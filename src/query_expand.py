import re
import sys
import rdflib.plugins.sparql as sparql

query_text = open(sys.argv[1]).read()
asn = sparql.parser.parseQuery(query_text)
q = sparql.algebra.translateQuery(asn)
ns = q.prologue.namespace_manager
nss = dict(ns.namespaces())

for k,v in nss.items():
    query_text = re.sub(r"%s:(\w+)" % k, r"<%s\1>" % v, query_text)
    
query_text = re.sub(r"\?[\w_]+", lambda m: m.group(0).replace('_', ''), query_text)
    
with open(sys.argv[2], "w") as f:
    for ln in query_text.split("\n"):
        if ln.startswith("PREFIX"): continue
        f.write(ln)
        f.write("\n")
