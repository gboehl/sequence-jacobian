import warnings

from .. import nonlinear
from ..steady_state import steady_state
from ..jacobian.drivers import get_G
from ..jacobian.classes import JacobianDict
from ..blocks.simple_block import simple

from ..devtools.deprecate import deprecated_shock_input_convention


def solved(unknowns, targets, block_list=[], solver=None, solver_kwargs={}, name=""):
    """Creates SolvedBlocks. Can be applied in two ways, both of which return a SolvedBlock:
        - as @solved(unknowns=..., targets=...) decorator on a single SimpleBlock
        - as function solved(blocklist=..., unknowns=..., targets=...) where blocklist
            can be any list of blocks
    """
    if block_list:
        if not name:
            name = f"{block_list[0].name}_to_{block_list[-1].name}_solved"
        # ordinary call, not as decorator
        return SolvedBlock(block_list, name, unknowns, targets, solver=solver, solver_kwargs=solver_kwargs)
    else:
        # call as decorator, return function of function
        def singleton_solved_block(f):
            return SolvedBlock([simple(f)], f.__name__, unknowns, targets, solver=solver, solver_kwargs=solver_kwargs)
        return singleton_solved_block


class SolvedBlock:
    """SolvedBlocks are mini SHADE models embedded as blocks inside larger SHADE models.

    When creating them, we need to provide the basic ingredients of a SHADE model: the list of
    blocks comprising the model, the list on unknowns, and the list of targets.

    When we use .jac to ask for the Jacobian of a SolvedBlock, we are really solving for the 'G'
    matrices of the mini SHADE models, which then become the 'curlyJ' Jacobians of the block.

    Similarly, when we use .td to evaluate a SolvedBlock on a path, we are really solving for the
    nonlinear transition path such that all internal targets of the mini SHADE model are zero.
    """

    def __init__(self, block_list, name, unknowns, targets, solver=None, solver_kwargs={}):
        self.block_list = block_list
        self.name = name
        self.unknowns = unknowns
        self.targets = targets
        self.solver = solver
        self.solver_kwargs = solver_kwargs

        # need to have inputs and outputs!!!
        self.outputs = (set.union(*(b.outputs for b in block_list)) | set(list(self.unknowns.keys()))) - set(self.targets)
        self.inputs = set.union(*(b.inputs for b in block_list)) - self.outputs

    # TODO: Deprecated methods, to be removed!
    def ss(self, *args, **kwargs):
        warnings.warn("This method has been deprecated. Please invoke by calling .steady_state", DeprecationWarning)
        return self.steady_state(*args, **kwargs)

    def td(self, *args, **kwargs):
        warnings.warn("This method has been deprecated. Please invoke by calling .impulse_nonlinear",
                      DeprecationWarning)
        return self.impulse_nonlinear(*args, **kwargs)

    def jac(self, ss, T=None, shock_list=None, **kwargs):
        if shock_list is None:
            shock_list = []
        warnings.warn("This method has been deprecated. Please invoke by calling .jacobian.\n"
                      "Also, note that the kwarg `shock_list` in .jacobian has been renamed to `shocked_vars`",
                      DeprecationWarning)
        return self.jacobian(ss, T, shock_list, **kwargs)

    def steady_state(self, consistency_check=True, ttol=1e-9, ctol=1e-9, verbose=False, **calibration):
        if self.solver is None:
            raise RuntimeError("Cannot call the ss method on this SolvedBlock without specifying a solver.")
        else:
            return steady_state(self.block_list, calibration, self.unknowns, self.targets,
                                consistency_check=consistency_check, ttol=ttol, ctol=ctol, verbose=verbose,
                                solver=self.solver, **self.solver_kwargs)

    def impulse_nonlinear(self, ss, shocked_paths=None, monotonic=False,
                          returnindividual=False, verbose=False, **kwargs):
        shocked_paths = deprecated_shock_input_convention(shocked_paths, kwargs)

        # TODO: add H_U_factored caching of some kind
        # also, inefficient since we are repeatedly starting from the steady state, need option
        # to provide a guess (not a big deal with just SimpleBlocks, of course)
        return nonlinear.td_solve(ss, self.block_list, list(self.unknowns.keys()), self.targets,
                                  shocked_paths=shocked_paths, monotonic=monotonic,
                                  returnindividual=returnindividual, verbose=verbose)

    def impulse_linear(self, ss, shocked_paths, T=None):
        return self.jacobian(ss, T, list(shocked_paths.keys())).apply(shocked_paths)

    def jacobian(self, ss, T, shocked_vars, output_list=None, save=False, use_saved=False):
        relevant_shocks = [i for i in self.inputs if i in shocked_vars]

        if not relevant_shocks:
            return JacobianDict({})
        else:
            # H_U_factored caching could be helpful here too
            return get_G(self.block_list, relevant_shocks, list(self.unknowns.keys()), self.targets,
                         T, ss, output_list, save=save, use_saved=use_saved)
