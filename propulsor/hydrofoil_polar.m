function [Cl, Cd, info] = hydrofoil_polar(alpha_rad, Re, toc_, foc_, vent, params)
%HYDROFOIL_POLAR  Section lift and drag coefficients for a blade element.
%
%   [Cl, Cd] = HYDROFOIL_POLAR(alpha_rad, Re, toc, foc, vent, params)
%   [Cl, Cd, info] = HYDROFOIL_POLAR(...)   with diagnostics
%
%   alpha_rad : angle of attack, rad. Scalar or one value per radial station.
%   Re        : chord Reynolds number, scalar or per station.
%   toc       : thickness / chord, scalar or per station.
%   foc       : maximum camber / chord, scalar or per station.
%   vent      : ventilated fraction of the section, 0 to 1. Zero is fully
%               wetted; one is fully ventilated. Supplied by
%               surface_piercing_model.m. Pass 0 for submerged operation.
%   params    : configuration struct from config().
%
%   The signature is fixed by the caller in bem_rotor.m, which needs two
%   plain arrays and calls this once per solver iteration per station.
%
%   ============================ READ THIS ============================
%   THE DEFAULT MODEL IS PROVISIONAL AND IS NOT EXPERIMENTAL DATA.
%
%   It is a thin-aerofoil lift line with a thickness correction, a friction
%   drag estimate, and a smooth blend to flat-plate behaviour past stall. It
%   exists so the framework runs end to end and so the BEM solver has
%   something continuous to work with. It is NOT a substitute for real
%   section data and any efficiency computed from it carries that caveat.
%
%   To replace it, set params.polar.useExternal = true and supply
%   params.polar.external as a struct array with fields .alpha_rad, .Re,
%   .Cl, .Cd, from XFOIL at the section Reynolds numbers, from a cavitation
%   tunnel, or from CFD. Nothing else in the project changes. See
%   load_inputs.m.
%   ===================================================================
%
%   THE MODEL
%
%   Lift, below stall. Thin-aerofoil theory gives a slope of 2*pi per radian
%   and a zero-lift angle set by camber. For a parabolic mean line the
%   classical result is alpha_0 = -2*(f/c) radians, obtained from
%
%       alpha_0 = -(1/pi) * integral of (dz/dx)(cos(theta) - 1) d(theta)
%
%   Thickness raises the slope slightly; the usual first-order correction is
%   a factor (1 + 0.77*t/c). So
%
%       Cl = 2*pi*(1 + 0.77*t/c) * (alpha - alpha_0)
%
%   Drag, below stall. Two parts. Skin friction over both surfaces, scaled by
%   a form factor that accounts for the section being a body rather than a
%   flat plate:
%
%       Cd0 = 2*Cf(Re) * (1 + 2*(t/c) + 60*(t/c)^4)
%
%   and a quadratic rise away from the section's design lift coefficient,
%   which stands in for the pressure drag that grows as the section works away
%   from its shock-free condition:
%
%       Cd = Cd0 + k*(Cl - Cl_bucket)^2
%
%   The bucket centre is the lift at zero geometric incidence,
%   Cl_alpha*(-alpha_0), so it is proportional to camber and vanishes with it.
%   That matters: centring every section on one global constant would put the
%   drag minimum at a positive angle of attack even for an uncambered section,
%   which contradicts symmetry. Set section.Cl_design to override.
%
%   Past stall. A BEM solver will ask for angles far outside the linear
%   range, particularly near the hub and during the first iterations, and it
%   will not converge if the polar has a cliff in it. Beyond the stall angle
%   the model blends smoothly into flat-plate behaviour,
%
%       Cl -> 2*sin(alpha)*cos(alpha),   Cd -> Cd0 + 2*sin(alpha)^2
%
%   using a smoothstep over a transition band, so both curves stay C1. This
%   is a numerical-robustness device with a physical asymptote, not a stall
%   prediction. Treat any converged solution that sits past stall as invalid
%   and say so; do not report its efficiency.
%
%   VENTILATED SECTIONS
%
%   A ventilated section is not a stalled wetted section, it is a different
%   flow. The suction side carries a gas cavity at roughly atmospheric
%   pressure, so it contributes no suction, and only the pressure face works.
%   Linearised supercavitating theory for a flat plate at zero cavitation
%   number gives a lift slope of pi/2 per radian, a quarter of the 2*pi of
%   the fully wetted plate:
%
%       Cl_vent = k_sc * (pi/2) * alpha
%
%   The resultant force on a fully ventilated face is normal to that face, so
%   its streamwise component is the lift times the incidence, and the cavity
%   closes behind the section with a base drag:
%
%       Cd_vent = Cl_vent * alpha + Cd_base
%
%   k_sc and Cd_base are params.surfacePiercing.k_sc and .Cd_base, both
%   ASSUMPTIONS. The two branches are blended linearly on the ventilated
%   fraction, which is what a partially ventilated section is: part of the
%   chord wetted, part not.
%
%   LIMITATIONS
%     - No cavitation effect on the wetted polar. That is cavitation_model.m.
%     - The supercavitating branch is linear theory at sigma = 0. It has no
%       stall, no thickness effect and no Reynolds dependence, because at
%       full ventilation none of those govern.
%     - No laminar bucket, no transition modelling, no roughness.
%     - Reynolds enters through friction only, not through stall angle,
%       though in reality stall angle falls with Reynolds number.
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

    if nargin < 6
        error('hydrofoil_polar:args', ...
              'usage: hydrofoil_polar(alpha_rad, Re, toc, foc, vent, params)');
    end

    P = params.polar;
    section = struct('toc', toc_, 'foc', foc_);

    % --- external data path ---------------------------------------------
    if isfield(P, 'useExternal') && P.useExternal
        if isempty(P.external)
            error('hydrofoil_polar:noExternal', ...
                 ['params.polar.useExternal is true but params.polar.external ' ...
                  'is empty. Supply measured or computed polars, or set ' ...
                  'useExternal to false to use the provisional model.']);
        end
        pol = interpolate_external(alpha_rad, Re, P.external);
        pol.source = 'external data';
        Cl = pol.Cl; Cd = pol.Cd; info = pol;
        return;
    end

    % --- validate --------------------------------------------------------
    alpha_rad = alpha_rad(:).';
    if isscalar(Re)
        Re = repmat(Re, size(alpha_rad));
    else
        Re = Re(:).';
    end
    if numel(Re) ~= numel(alpha_rad)
        error('hydrofoil_polar:size', ...
              'Re has %d elements but alpha has %d', numel(Re), numel(alpha_rad));
    end
    if any(~isfinite(alpha_rad))
        error('hydrofoil_polar:alpha', 'alpha contains non-finite values');
    end

    n = numel(alpha_rad);
    toc_ = broadcast(section.toc,  n, 'toc');
    foc  = broadcast(section.foc,  n, 'foc');
    vent = broadcast(vent,         n, 'vent');

    if any(toc_ <= 0 | toc_ > 0.5)
        error('hydrofoil_polar:toc', ...
              'thickness/chord outside (0, 0.5]; min %.4f max %.4f', ...
              min(toc_), max(toc_));
    end
    if any(abs(foc) > 0.15)
        error('hydrofoil_polar:foc', ...
              'camber/chord beyond anything manufacturable; max |f/c| = %.4f', ...
              max(abs(foc)));
    end
    if any(vent < 0 | vent > 1)
        error('hydrofoil_polar:vent', 'ventilated fraction must lie in [0, 1]');
    end

    % Below a certain Reynolds number the friction correlation is out of its
    % range and the section behaves quite differently. Clamp and flag rather
    % than extrapolate a correlation into nonsense.
    Re_min = P.Re_min;
    ReClamped = Re < Re_min;
    Re_used = max(Re, Re_min);

    % --- linear-range lift ------------------------------------------------
    alpha0 = -2.0 .* foc;                          % rad, thin aerofoil
    Cl_alpha = P.Cl_alpha .* (1 + 0.77 .* toc_);    % per rad, thickness corrected
    Cl_lin = Cl_alpha .* (alpha_rad - alpha0);

    % --- friction and profile drag ---------------------------------------
    Cf = friction_coefficient(Re_used, P.frictionLine);
    formFactor = 1 + 2.*toc_ + 60.*toc_.^4;
    Cd0 = 2 .* Cf .* formFactor;                    % both surfaces

    % The drag bucket is centred on the section's OWN design lift, not on a
    % global constant. Using one Cl_design for every section puts the drag
    % minimum at a positive angle of attack even for an uncambered section,
    % which is wrong: a symmetric section has its minimum drag at zero
    % incidence, by symmetry.
    %
    % The natural centre is the lift the section makes at zero geometric
    % incidence, Cl_alpha * (-alpha_0), which is proportional to camber and
    % vanishes when the camber does. A section may override it explicitly.
    Cl_bucket = Cl_alpha .* (-alpha0);

    Cd_lin = Cd0 + P.dCd_dCl2 * (Cl_lin - Cl_bucket).^2;

    % --- flat-plate asymptote --------------------------------------------
    Cl_flat = 2 * sin(alpha_rad) .* cos(alpha_rad);
    Cd_flat = Cd0 + 2 * sin(alpha_rad).^2;

    % --- smooth blend across stall ---------------------------------------
    % The blend is on |alpha - alpha0|, so a cambered section stalls at the
    % same distance from its own zero-lift angle in both directions.
    a_stall = P.alpha_stall_rad;
    band    = deg2rad(6);                          % transition width
    dev     = abs(alpha_rad - alpha0);
    t = (dev - a_stall) / band;
    t = min(max(t, 0), 1);
    w = t.^2 .* (3 - 2*t);                         % smoothstep, C1 at both ends

    Cl_wet = (1 - w) .* Cl_lin  + w .* Cl_flat;
    Cd_wet = (1 - w) .* Cd_lin  + w .* Cd_flat;
    Cd_wet = max(Cd_wet, Cd0);          % never below the friction floor

    % --- ventilated (supercavitating) branch ------------------------------
    SP = params.surfacePiercing;
    Cl_vent = SP.k_sc * (pi/2) * alpha_rad;
    Cd_vent = Cl_vent .* alpha_rad + SP.Cd_base;
    Cd_vent = max(Cd_vent, SP.Cd_base);

    % --- blend on ventilated fraction -------------------------------------
    Cl = (1 - vent) .* Cl_wet  + vent .* Cl_vent;
    Cd = (1 - vent) .* Cd_wet  + vent .* Cd_vent;

    if nargout >= 3
        info.Cl         = Cl;
        info.Cd         = Cd;
        info.Cl_wet     = Cl_wet;
        info.Cd_wet     = Cd_wet;
        info.Cl_vent    = Cl_vent;
        info.Cd_vent    = Cd_vent;
        info.Cl_linear  = Cl_lin;
        info.Cd0        = Cd0;
        info.Cl_bucket  = Cl_bucket;
        info.alpha0_rad = alpha0;
        info.Cl_alpha   = Cl_alpha;
        info.stalled    = w > 0;
        info.stallFrac  = w;
        info.ventFrac   = vent;
        info.ReClamped  = ReClamped;
        info.Re_used    = Re_used;
        info.source     = P.source;
    end
end

% =========================================================================
function v = broadcast(v, n, name)
%BROADCAST  Expand a scalar to n elements, or check an array already fits.
    v = v(:).';
    if isscalar(v)
        v = repmat(v, 1, n);
    elseif numel(v) ~= n
        error('hydrofoil_polar:size', ...
              '%s has %d elements but alpha has %d', name, numel(v), n);
    end
end

% =========================================================================
function Cf = friction_coefficient(Re, line)
%FRICTION_COEFFICIENT  One-side flat-plate skin friction.
    switch lower(strtrim(char(line)))
        case {'ittc-57', 'ittc57', 'ittc'}
            Cf = 0.075 ./ (log10(Re) - 2).^2;
        case {'schlichting', 'turbulent'}
            Cf = 0.455 ./ (log10(Re)).^2.58;
        case {'blasius', 'laminar'}
            Cf = 1.328 ./ sqrt(Re);
        otherwise
            error('hydrofoil_polar:frictionLine', ...
                  'unknown friction line ''%s''', char(line));
    end
end

% =========================================================================
function pol = interpolate_external(alpha_rad, Re, ext)
%INTERPOLATE_EXTERNAL  Bilinear in (alpha, Re) over supplied polar tables.
%
%   ext.alpha_rad : vector, strictly increasing
%   ext.Re        : vector, strictly increasing
%   ext.Cl, ext.Cd: numel(alpha) x numel(Re)
%
%   Outside the supplied Reynolds range the nearest table is used rather than
%   extrapolated, and the fact is flagged, because extrapolating a measured
%   polar in Reynolds number is how a plausible wrong answer is produced.

    alpha_rad = alpha_rad(:).';
    if isscalar(Re), Re = repmat(Re, size(alpha_rad)); else, Re = Re(:).'; end

    Re_c = min(max(Re, ext.Re(1)), ext.Re(end));
    outside = (Re < ext.Re(1)) | (Re > ext.Re(end));

    Cl = zeros(size(alpha_rad));
    Cd = zeros(size(alpha_rad));
    for k = 1:numel(alpha_rad)
        Cl(k) = interp2(ext.Re(:).', ext.alpha_rad(:), ext.Cl, Re_c(k), alpha_rad(k), 'linear');
        Cd(k) = interp2(ext.Re(:).', ext.alpha_rad(:), ext.Cd, Re_c(k), alpha_rad(k), 'linear');
    end

    pol.Cl = Cl;
    pol.Cd = Cd;
    pol.ReClamped = outside;
    pol.Re_used = Re_c;
    pol.stalled = false(size(alpha_rad));
    pol.stallFrac = zeros(size(alpha_rad));
end
