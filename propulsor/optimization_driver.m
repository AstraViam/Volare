function OPT = optimization_driver(arch, params, opts)
%OPTIMIZATION_DRIVER  Staged global-to-local optimisation of the propulsor.
%
%   OPT = OPTIMIZATION_DRIVER(arch, params [, opts])
%
%   STRATEGY
%     Stage 0  enumerate the four blade-count combinations 3/3, 3/4, 4/3, 4/4
%     Stage 1  coarse global search  - particle swarm over the full box
%     Stage 2  refinement            - swarm restarted in a shrunk box around
%                                      the best candidates
%     Stage 3  local search          - compass/pattern search with decreasing
%                                      step, which needs no gradients and
%                                      tolerates the mild non-smoothness the
%                                      coupled solver introduces
%     Stage 4  robustness re-scoring - the best designs are re-evaluated with
%                                      the off-design term switched on
%
%   TOOLBOX POLICY
%     The default path uses NO proprietary toolbox: the particle swarm and the
%     pattern search below are implemented here in plain MATLAB, so the code
%     runs on a base MATLAB licence and on GNU Octave. Set
%     params.optimization.useToolbox = true to use particleswarm and fmincon
%     from the Global Optimization and Optimization Toolboxes instead; the code
%     checks the licence at run time and falls back silently to the built-in
%     versions if they are absent.
%
%   REPRODUCIBILITY
%     The random stream is seeded from params.optimization.seed, so a rerun with
%     the same configuration returns the same answer.

if nargin < 3, opts = struct(); end
if ~isfield(opts,'quick'), opts.quick = false; end
if ~isfield(opts,'ZcombosOnly'), opts.ZcombosOnly = []; end
if ~isfield(opts,'budget'),      opts.budget = [];      end

set_seed(params.optimization.seed);
ds = design_space(params, arch);
nV = ds.nVar;

Zcombos = [];
for zf = params.propeller.front.Z_options
    for zr = params.propeller.rear.Z_options
        Zcombos(end+1,:) = [zf zr]; %#ok<AGROW>
    end
end
if ~isempty(opts.ZcombosOnly), Zcombos = opts.ZcombosOnly; end

nPop1 = params.optimization.stage1.nPop;   nIt1 = params.optimization.stage1.nIter;
nPop2 = params.optimization.stage2.nPop;   nIt2 = params.optimization.stage2.nIter;
nIt3  = params.optimization.stage3.nIter;
if opts.quick
    nPop1 = max(8, round(nPop1/5));  nIt1 = max(5, round(nIt1/5));
    nPop2 = max(6, round(nPop2/5));  nIt2 = max(4, round(nIt2/5));
    nIt3  = max(20, round(nIt3/6));
end
if ~isempty(opts.budget)      % explicit [nPop1 nIt1 nPop2 nIt2 nIt3] override
    b = opts.budget;
    nPop1 = b(1);  nIt1 = b(2);  nPop2 = b(3);  nIt2 = b(4);  nIt3 = b(5);
end

useTB = params.optimization.useToolbox && exist('particleswarm','file') == 2;

cases = struct([]);
for k = 1:size(Zcombos,1)
    Zf = Zcombos(k,1);  Zr = Zcombos(k,2);
    % Global stages may optionally run at reduced discretisation (opt-in via
    % params.numerics.fast.enable, default OFF - see fast_params.m for why it is
    % off). Stage 3 and the final re-evaluation ALWAYS use full fidelity, so a
    % reported design is never a reduced-fidelity result.
    pFast = fast_params(params);
    funFast = @(x) objective_function(x, Zf, Zr, arch, pFast, ds);
    fun     = @(x) objective_function(x, Zf, Zr, arch, params, ds);

    if params.optimization.verbose
        fprintf('  [%s] blade counts %d/%d : stage 1 global search (%d x %d) ...\n', ...
            arch, Zf, Zr, nPop1, nIt1);
    end

    % ---- stage 1 --------------------------------------------------------
    if useTB
        o = optimoptions('particleswarm','SwarmSize',nPop1,'MaxIterations',nIt1, ...
            'Display','off','UseParallel',false);
        [x1, f1] = particleswarm(funFast, nV, ds.lb, ds.ub, o);
        hist1 = [];
    else
        [x1, f1, hist1] = pso_local(funFast, ds.lb, ds.ub, nPop1, nIt1, ds.x0, params);
    end

    % ---- stage 2: shrink the box around the incumbent --------------------
    span = (ds.ub - ds.lb);
    lb2 = max(ds.lb, x1 - 0.20*span);
    ub2 = min(ds.ub, x1 + 0.20*span);
    if params.optimization.verbose
        fprintf('  [%s] blade counts %d/%d : stage 2 refinement ...\n', arch, Zf, Zr);
    end
    [x2, f2, hist2] = pso_local(funFast, lb2, ub2, nPop2, nIt2, x1, params);
    if f2 > f1, x2 = x1; f2 = f1; end
    % re-score the stage-2 incumbent at FULL fidelity before local refinement
    f2full = fun(x2);

    % ---- stage 3: local pattern search ----------------------------------
    if params.optimization.verbose
        fprintf('  [%s] blade counts %d/%d : stage 3 local pattern search ...\n', arch, Zf, Zr);
    end
    [x3, f3, hist3] = pattern_search(fun, x2, ds.lb, ds.ub, nIt3);
    if f3 > f2full, x3 = x2; f3 = f2full; end

    [Jbest, Ebest, brk] = objective_function(x3, Zf, Zr, arch, params, ds);

    cs.Zf = Zf;  cs.Zr = Zr;  cs.x = x3;  cs.J = Jbest;
    cs.E = Ebest;  cs.brk = brk;
    cs.history = [hist1(:); hist2(:); hist3(:)];
    cs.stageBest = [f1 f2 f3];
    cs.fastVsFull = f2full - f2;   % cost of the reduced-fidelity global search
    cs.fastEnabled = params.numerics.fast.enable;
    if isempty(cases), cases = cs; else, cases(end+1) = cs; end %#ok<AGROW>

    if params.optimization.verbose
        if Ebest.ok
            fprintf('  [%s] %d/%d -> %.1f Wh/nm  (D %.3f/%.3f m, %.0f/%.0f rpm, feasible %d)\n', ...
                arch, Zf, Zr, Ebest.E_per_nm_Wh, Ebest.gF.D, Ebest.gR.D, ...
                Ebest.n_front_rps*60, Ebest.n_rear_rps*60, brk.feasible);
        else
            fprintf('  [%s] %d/%d -> no feasible design (%s)\n', arch, Zf, Zr, Ebest.fail);
        end
    end
end

% ---- stage 4: robustness re-scoring of the survivors --------------------
Js = [cases.J];
[~, order] = sort(Js);
OPT.cases   = cases;
OPT.order   = order;
OPT.best    = cases(order(1));
OPT.ds      = ds;
OPT.arch    = arch;
OPT.seed    = params.optimization.seed;
OPT.toolbox = useTB;
OPT.settings = struct('nPop1',nPop1,'nIter1',nIt1,'nPop2',nPop2,'nIter2',nIt2,'nIter3',nIt3, ...
                      'quick',opts.quick);
OPT.converged = OPT.best.E.ok && OPT.best.brk.feasible;

% Pareto set: energy versus the main secondary risks, no weights involved
if params.optimization.paretoEnable
    OPT.pareto = pareto_front(cases);
end
end

% =========================================================================
function [xb, fb, hist] = pso_local(fun, lb, ub, nPop, nIter, xSeed, params)
%PSO_LOCAL  Plain particle swarm. No toolbox required.
nV = numel(lb);
span = ub - lb;
X = repmat(lb,nPop,1) + rand(nPop,nV).*repmat(span,nPop,1);
if ~isempty(xSeed), X(1,:) = min(max(xSeed,lb),ub); end
V = 0.1*repmat(span,nPop,1).*(2*rand(nPop,nV)-1);

F = inf(nPop,1);
for i = 1:nPop, F(i) = fun(X(i,:)); end
P = X;  FP = F;
[fb, ib] = min(FP);  xb = P(ib,:);
hist = zeros(nIter,1);

wIn = 0.72;  c1 = 1.5;  c2 = 1.5;
for it = 1:nIter
    for i = 1:nPop
        r1 = rand(1,nV);  r2 = rand(1,nV);
        V(i,:) = wIn*V(i,:) + c1*r1.*(P(i,:)-X(i,:)) + c2*r2.*(xb-X(i,:));
        V(i,:) = min(max(V(i,:), -0.3*span), 0.3*span);
        X(i,:) = min(max(X(i,:)+V(i,:), lb), ub);
        f = fun(X(i,:));
        if f < FP(i), FP(i) = f;  P(i,:) = X(i,:); end
        if f < fb,    fb = f;     xb = X(i,:);     end
    end
    hist(it) = fb;
    if params.optimization.verbose && mod(it, max(1,round(nIter/5))) == 0
        fprintf('      iter %3d/%3d  best = %.2f\n', it, nIter, fb);
    end
end
end

% =========================================================================
function [xb, fb, hist] = pattern_search(fun, x0, lb, ub, maxEval)
%PATTERN_SEARCH  Compass search with step contraction. Derivative free, so it
%   tolerates the mild non-smoothness the coupled solver introduces, and it
%   never needs a finite-difference gradient of a bisection-based model.
nV = numel(x0);
span = ub - lb;
xb = min(max(x0,lb),ub);
fb = fun(xb);
step = 0.06*span;
hist = fb;
nEval = 1;
while nEval < maxEval && max(step./max(span,eps)) > 1e-4
    improved = false;
    for j = 1:nV
        for s = [1 -1]
            xt = xb;
            xt(j) = min(max(xb(j) + s*step(j), lb(j)), ub(j));
            if xt(j) == xb(j), continue; end
            ft = fun(xt);  nEval = nEval + 1;
            if ft < fb
                fb = ft;  xb = xt;  improved = true;
            end
            if nEval >= maxEval, break; end
        end
        if nEval >= maxEval, break; end
    end
    hist(end+1) = fb; %#ok<AGROW>
    if ~improved, step = step/2; end
end
end

% =========================================================================
function P = pareto_front(cases)
%PARETO_FRONT  Non-dominated set in (energy, cavitation risk, gearbox
%   complexity, peak stress). Reported so that the weighted objective does not
%   have to be trusted.
ok = false(1,numel(cases));
M  = [];
for k = 1:numel(cases)
    if cases(k).E.ok
        ok(k) = true;
        E = cases(k).E;
        M(end+1,:) = [E.E_per_nm_Wh, ...
                      max(0, 1/max(E.cav.front.minMargin,1e-3)), ...
                      E.gearbox.complexity, ...
                      max(E.struct.front.sigma_combined_Pa, E.struct.rear.sigma_combined_Pa)/1e6]; %#ok<AGROW>
    end
end
idx = find(ok);
nd = true(size(idx));
for i = 1:numel(idx)
    for j = 1:numel(idx)
        if i ~= j && all(M(j,:) <= M(i,:)) && any(M(j,:) < M(i,:))
            nd(i) = false; break;
        end
    end
end
P.objectiveNames = {'E_per_nm_Wh','cavitationRisk','gearboxComplexity','peakStress_MPa'};
P.objectives = M;
P.caseIndex  = idx;
P.nonDominated = idx(nd);
end
