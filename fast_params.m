function pf = fast_params(params)
%FAST_PARAMS  Reduced-fidelity settings for the GLOBAL search stages only.
%
%   ONLY the discretisation is reduced. Solver TOLERANCES are deliberately left
%   at their full-fidelity values: loosening them was tested and made the tool
%   SLOWER, because a loose interference tolerance causes the coupled bisection
%   to spend more evaluations on bracket expansion than it saves on refinement,
%   and it reintroduces path dependence in the objective.
%
%   Called by optimization_driver.m for the STAGE 1 and STAGE 2 global searches
%   only. Stage 3 and the final re-evaluation always use full fidelity, and the
%   stage-2 incumbent is re-scored at full fidelity before local refinement, so
%   a reported design is never a reduced-fidelity result. The full-vs-fast
%   objective gap is recorded in cs.fastVsFull and printed by postprocess.m, so
%   the reduction is never hidden.
%
%   DEFAULT: params.numerics.fast.enable = false, i.e. this function is a
%   pass-through. It is retained because the reduction was tested and measured,
%   and the measurement is worth keeping.
pf = params;
if ~params.numerics.fast.enable, return; end
f = params.numerics.fast;
pf.propeller.common.nRadial    = f.nRadial;
pf.numerics.bem.tol            = f.bem_tol;
pf.numerics.crp.tol            = f.crp_tol;
pf.numerics.thrustSolve.tol    = f.thrust_tol;
pf.numerics.ladderPoints       = f.ladder;
pf.propeller.common.nAzimuth   = 36;
end
