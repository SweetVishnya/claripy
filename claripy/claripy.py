import itertools
bitvec_counter = itertools.count()

import logging
l = logging.getLogger('claripy.claripy')

class Claripy(object):
    def __init__(self, name, model_backends, solver_backends, parallel=None):
        self.name = name
        self.solver_backends = solver_backends
        self.model_backends = model_backends
        self.unique_names = True
        self.parallel = parallel if parallel else False

        self.true = self.BoolVal(True)
        self.false = self.BoolVal(False)

    #
    # Backend management
    #
    def backend_of_type(self, b_type):
        for b in self.model_backends + self.solver_backends:
            if type(b) is b_type:
                return b
        return None

    #
    # Solvers
    #
    def solver(self):
        '''
        Returns a new solver.
        '''
        raise NotImplementedError()

    #
    # Operations
    #

    def wrap(self, o, symbolic=False, variables=None):
        if type(o) is E:
            return o
        else:
            return E(self, o, set() if variables is None else variables, symbolic)

    @staticmethod
    def _collapse_ast(op, args): #pylint:disable=unused-argument
        raw_args = [ (a.ast if isinstance(a, E) else a) for a in args ]
        types = [ type(a) for a in raw_args ]

        if types.count(A) != 0 and not all((a.collapsible for a in raw_args if isinstance(a, A))):
                l.debug("Not collapsing because ASTs are present.")
                return False

        if op not in inverses:
            l.debug("collapsing the AST for operation %s because it's not invertible", op)
            return True

        constants = sum((types.count(t) for t in (int, long, bool, str, BVV)))
        if constants == len(args):
            l.debug("collapsing the AST for operation %s because it's full of constants", op)
            return True

        if len([ a for a in raw_args if isinstance(a, StridedInterval) and a.is_integer()]) > 1:
            l.debug("collapsing the AST for operation %s because there are more than two SIs")
            return True

        #
        # More complex checks probably go here.
        #

        # Reversible; don't collapse!
        l.debug("not collapsing the AST for operation %s!", op)
        return False

    def _do_op_raw(self, op, args, raw=False, collapse_ast=None):
        collapse_ast = self._collapse_ast(op, args) if collapse_ast is None else collapse_ast

        if collapse_ast:
            for b in self.model_backends:
                try:
                    if raw: r = b.call(op, args)
                    else:   r = b.call_expr(op, args)

                    #l.warning("YAY %s", b)
                    return r
                except BackendError:
                    #l.warning("WTF %s", b, exc_info=True)
                    continue

        # all backends failed, or we aren't collapsing
        l.debug("all model backends failed or we were told to preserve the AST for op %s", op)
        return A(self, op, args)

    def _do_op(self, op, args, variables=None, symbolic=None, raw=False, simplified=False, collapse_ast=None):
        r = self._do_op_raw(op, args, raw=raw, collapse_ast=collapse_ast)

        if symbolic is None:
            symbolic = any(arg.symbolic if isinstance(arg, E) else False for arg in args)
        if variables is None:
            all_variables = ((arg.variables if isinstance(arg, E) else set()) for arg in args)
            variables = set.union(*all_variables)

        return E(self, r, variables, symbolic, simplified=simplified)

    def BitVec(self, name, size, explicit_name=None):
        explicit_name = explicit_name if explicit_name is not None else False
        if self.unique_names and not explicit_name:
            name = "%s_%d_%d" % (name, bitvec_counter.next(), size)
        return self._do_op('BitVec', (name, size), variables={ name }, raw=True, symbolic=True, simplified=True)
    BV = BitVec

    def BitVecVal(self, *args):
        return E(self, BVV(*args), set(), False, simplified=True)
        #return self._do_op('BitVecVal', args, variables=set(), symbolic=False, raw=True)
    BVV = BitVecVal

    # Bitwise ops
    def LShR(self, *args): return self._do_op('LShR', args)
    def SignExt(self, *args): return self._do_op('SignExt', args)
    def ZeroExt(self, *args): return self._do_op('ZeroExt', args)
    def Extract(self, *args): return self._do_op('Extract', args)
    def Concat(self, *args): return self._do_op('Concat', args)
    def RotateLeft(self, *args): return self._do_op('RotateLeft', args)
    def RotateRight(self, *args): return self._do_op('RotateRight', args)
    def Reverse(self, o, lazy=True):
        if type(o) is not E or not lazy:
            return self._do_op('Reverse', (o,))

        if isinstance(o.ast, A) and o.ast.op == 'Reverse':
            return self.wrap(o.ast.args[0])
        else:
            return self.wrap(A(self, "Reverse", (o,), collapsible=True), symbolic=o.symbolic, variables=o.variables)

    #
    # Strided interval
    #
    def StridedInterval(self, name=None, bits=0, lower_bound=None, upper_bound=None, stride=None, to_conv=None):
        si = BackendVSA.CreateStridedInterval(name=name,
                                            bits=bits,
                                            lower_bound=lower_bound,
                                            upper_bound=upper_bound,
                                            stride=stride,
                                            to_conv=to_conv)
        return E(self, si, variables={ si.name }, symbolic=False)
    SI = StridedInterval

    def TopStridedInterval(self, bits, signed=False):
        si = BackendVSA.CreateTopStridedInterval(bits=bits, signed=signed)
        return E(self, si, variables={ si.name }, symbolic=False)
    TSI = TopStridedInterval

    # Value Set
    def ValueSet(self, **kwargs):
        vs = ValueSet(**kwargs)
        return E(self, vs, set(), symbolic=False)
    VS = ValueSet

    # a-loc
    def AbstractLocation(self, *args, **kwargs): #pylint:disable=no-self-use
        aloc = AbstractLocation(*args, **kwargs)
        return aloc

    #
    # Boolean ops
    #
    def BoolVal(self, *args):
        return E(self, args[0], set(), False, simplified=True)
        #return self._do_op('BoolVal', args, variables=set(), symbolic=False, raw=True)

    def And(self, *args): return self._do_op('And', args)
    def Not(self, *args): return self._do_op('Not', args)
    def Or(self, *args): return self._do_op('Or', args)
    def ULT(self, *args): return self._do_op('ULT', args)
    def ULE(self, *args): return self._do_op('ULE', args)
    def UGE(self, *args): return self._do_op('UGE', args)
    def UGT(self, *args): return self._do_op('UGT', args)

    #
    # Other ops
    #
    def If(self, *args):
        if len(args) != 3: raise ClaripyOperationError("invalid number of args passed to If")
        return self._do_op('If', args)

    #def size(self, *args): return self._do_op('size', args)

    def ite_dict(self, i, d, default):
        return self.ite_cases([ (i == c, v) for c,v in d.items() ], default)

    def ite_cases(self, cases, default):
        sofar = default
        for c,v in reversed(cases):
            sofar = self.If(c, v, sofar)
        return sofar

    def simplify(self, e):
        for b in self.model_backends:
            try: return b.simplify_expr(e)
            except BackendError: pass

        l.debug("Simplifying via solver backend")

        for b in self.solver_backends:
            try: return b.simplify_expr(e)
            except BackendError: pass

        l.warning("Unable to simplify expression")
        return e

    def is_true(self, e):
        for b in self.model_backends:
            try: return b.is_true(b.convert_expr(e))
            except BackendError: pass

        l.warning("Unable to tell the truth-value of this expression")
        return False

    def is_false(self, e):
        for b in self.model_backends:
            try:
                return b.is_false(b.convert_expr(e))
            except BackendError:
                pass

        l.warning("Unable to tell the truth-value of this expression")
        return False

    def is_identical(self, *args):
        '''
        Attempts to check if the underlying models of the expression are identical,
        even if the hashes match.

        This process is somewhat conservative: False does not necessarily mean that
        it's not identical; just that it can't (easily) be determined to be identical.
        '''
        if type(args[0].model) is StridedInterval and type(args[1].model) is StridedInterval and args[
            0].model.upper_bound == 9 and args[1].model.upper_bound == 9:
            import ipdb
            ipdb.set_trace()

        if not all([isinstance(a, E) for a in args]):
            return False

        if len(set(hash(a) for a in args)) == 1:
            return True

        first = args[0]
        identical = True
        for o in args:
            i = self._do_op_raw('Identical', (first, o), collapse_ast=True)
            identical &= i is True
        return identical

    def constraint_to_si(self, expr, bits): #pylint:disable=unused-argument
        '''
        Convert a constraint to SI if possible
        :param expr:
        :return:
        '''
        si = None
        old_expr = None

        for b in self.model_backends:
            if type(b) is BackendVSA:
                old_expr, si = b.constraint_to_si(expr)

        if si is None:
            return None, None
        else:
            return old_expr, si

    def model_object(self, e, result=None):
        for b in self.model_backends:
            try: return b.convert_expr(e, result=result)
            except BackendError: pass
        raise BackendError('no model backend can convert expression')

from .expression import E
from .ast import A
from .backends.backend import BackendError
from .bv import BVV
from .vsa import ValueSet, AbstractLocation, StridedInterval
from .backends import BackendVSA
from .errors import ClaripyOperationError
from .operations import inverses
