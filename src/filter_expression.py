import operator, rdflib.term

class filter_expression(object):

    def _make_Builtin_REGEX(self, expr):
        import re
        
        assert map(type, (expr.text, expr.flags, expr.pattern)) == [rdflib.term.Variable, rdflib.term.Literal, rdflib.term.Literal]
        
        flags = 0
        for f in expr.flags:
            flags |= {
                'i': re.IGNORECASE
            }[f]
        
        pat = re.compile(expr.pattern, flags=flags)
        k = expr.text
        
        self.fn = lambda t: pat.search(getattr(t, k)) is not None
        self.s = "?%s matches /%s/%s" % (expr.text, expr.pattern, expr.flags)

    def _make_RelationalExpression(self, expr):

        opfn = getattr(operator, {
            '>' : 'gt',
            '<' : 'lt',
            '>=': 'ge',
            '<=': 'le',
            '=' : 'eq'
        }[expr.op])
        args = (expr.expr, expr.other)
        is_var = [isinstance(x, rdflib.term.Variable) for x in args]
        s0, s1 = map(str, args)
        a0, a1 = map(lambda v: v.value if isinstance(v, rdflib.term.Literal) else None, args)
        
        if all(is_var): 
            self.fn = lambda t: opfn(getattr(t, s0).value, getattr(t, s1).value)
            self.s = "?%s %s ?%s" % (s0, expr.op, s1)
        elif is_var[0]:
            self.fn = lambda t: opfn(getattr(t, s0).value, a1)
            self.s = "?%s %s %.2f" % (s0, expr.op, a1)
        elif is_var[1]:
            self.fn = lambda t: opfn(a0, getattr(t, s1).value)
            self.s = "%.2f %s ?%s" % (a0, expr.op, s1)
        else: raise Exception("Not supported")
        
    def __init__(self, expr):
        getattr(self, "_make_%s" % expr.name)(expr)
        
    def __repr__(self):
        return self.s

    def __call__(self, t):
        return self.fn(t)
