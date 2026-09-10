function res = resistance_model(V_ms, params, whichCase)
%RESISTANCE_MODEL  Bare-hull resistance and effective power from measured data.
%
%   res = RESISTANCE_MODEL(V_ms, params)
%
%   V_ms      : speed(s) through the water, m/s. Scalar or array.
%   params    : configuration struct from config().
%   whichCase : optional. 'design' (default, the supplied 250 kg curve) or
%               'worst' (300 kg). The 300 kg curve is never fabricated from
%               the 250 kg data; if it has not been supplied this errors with
%               an explanation rather than returning a scaled guess.
%
%   Returns a struct with fields sized like V_ms:
%     .V_ms         speed, m/s
%     .V_kn         speed, knots
%     .R_N          total bare-hull resistance, N
%     .P_E_W        effective (towrope) power, R_T * V, W
%     .provenance   cellstr, one of 'supplied' | 'interpolated' | 'extrapolated'
%   and scalar fields:
%     .anyExtrapolated  true if any query left the measured range
%     .source           where the curve came from
%     .V_range_kn       [min max] of the supplied data
%
%   METHOD
%     Shape-preserving piecewise cubic interpolation (pchip) through the
%     supplied points. pchip is used rather than spline because spline
%     overshoots between widely spaced points, and a resistance curve that
%     dips below its neighbours is not physical. pchip cannot overshoot: it
%     preserves monotonicity of the data it is given.
%
%   WHY NOT A POLYNOMIAL FIT
%     Fitting R = k*V^2, or any polynomial, and presenting it as physical
%     truth would be wrong here. A planing or semi-planing catamaran has a
%     resistance hump; the exponent is not 2 and is not constant. The supplied
%     five points are measurements. They are used as measurements.
%
%   EXTRAPOLATION
%     Queries outside the measured range are flagged, every time, in
%     .provenance and in .anyExtrapolated. The design point is 20 knots, which
%     is the top of the measured range, so the main optimisation needs no
%     extrapolation at all. If you see 'extrapolated' in an optimisation
%     result, treat the number as unvalidated.
%
%   REPLACING THE DATA
%     Set params.resistance.V_kn and params.resistance.R_N to a new curve from
%     CFD or a towing tank. Nothing else changes. See load_inputs.m.
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

    U = units();

    % --- validate ------------------------------------------------------
    if nargin < 2
        error('resistance_model:args', ...
              'usage: resistance_model(V_ms, params [, whichCase])');
    end
    if nargin < 3
        whichCase = '';
    end
    if ~isnumeric(V_ms) || isempty(V_ms)
        error('resistance_model:V', 'V_ms must be a non-empty numeric array');
    end
    if any(~isfinite(V_ms(:)))
        error('resistance_model:V', 'V_ms contains non-finite values');
    end
    if any(V_ms(:) < 0)
        error('resistance_model:V', ...
              'V_ms must be non-negative; astern resistance is not modelled');
    end

    r = params.resistance;

    % Which curve: the supplied 250 kg one, or a 300 kg curve if the user has
    % since supplied one. The 300 kg case is NEVER fabricated from the 250 kg
    % data; if it is absent the caller is told so rather than given a guess.
    useCase = 'design';
    if nargin >= 3 && ~isempty(whichCase)
        useCase = lower(whichCase);
    end

    switch useCase
        case {'design', '250'}
            Vd_kn = r.speed_kn(:);
            Rd_N  = r.R_total_N(:);
            caseName = sprintf('%g kg (supplied)', r.mass_kg);
        case {'worst', '300'}
            if isempty(r.speed_kn_300) || isempty(r.R_total_N_300)
                error('resistance_model:noData300', ...
                     ['300 kg resistance data unavailable. Sensitivity analysis ' ...
                      'at 300 kg cannot be considered validated. Supply ' ...
                      'params.resistance.speed_kn_300 and R_total_N_300 from a ' ...
                      'towing tank or CFD run. This function will not scale the ' ...
                      '250 kg curve and present the result as data.']);
            end
            Vd_kn = r.speed_kn_300(:);
            Rd_N  = r.R_total_N_300(:);
            caseName = '300 kg (supplied)';
        otherwise
            error('resistance_model:case', ...
                  'unknown case ''%s''; use ''design'' or ''worst''', useCase);
    end

    if numel(Vd_kn) ~= numel(Rd_N)
        error('resistance_model:data', ...
              'resistance curve has %d speeds but %d resistances', ...
              numel(Vd_kn), numel(Rd_N));
    end
    if numel(Vd_kn) < 2
        error('resistance_model:data', 'need at least two points to interpolate');
    end
    if any(diff(Vd_kn) <= 0)
        error('resistance_model:data', 'curve speeds must strictly increase');
    end

    % --- interpolate ---------------------------------------------------
    Vq_kn = V_ms * U.ms2kn;

    allowExtrap = true;
    if isfield(r, 'allowExtrap')
        allowExtrap = logical(r.allowExtrap);
    end

    outside = (Vq_kn < Vd_kn(1) - 1e-9) | (Vq_kn > Vd_kn(end) + 1e-9);
    if any(outside(:)) && ~allowExtrap
        error('resistance_model:extrapBlocked', ...
             ['speed %.3f kn is outside the measured range %.1f to %.1f kn and ' ...
              'params.resistance.allowExtrap is false. Set it true to permit a ' ...
              'flagged extrapolation, or supply data covering the range.'], ...
              max(Vq_kn(outside)), Vd_kn(1), Vd_kn(end));
    end

    % 'extrap' lets pchip continue its end cubic outside the data. That is
    % reported as extrapolated below; it is never presented as measured.
    R_N = interp1(Vd_kn, Rd_N, Vq_kn, 'pchip', 'extrap');

    % Resistance cannot be negative. Extrapolating below the lowest measured
    % speed can drive the end cubic under zero; clamp and let the provenance
    % tag carry the warning.
    R_N = max(R_N, 0);

    % --- provenance, per query point -----------------------------------
    lo = Vd_kn(1);
    hi = Vd_kn(end);
    % Tolerance for "is this one of the measured points": 1e-9 knots is far
    % below any speed anyone will ask for and far above float noise.
    tol = 1e-9;

    prov = cell(size(Vq_kn));
    for k = 1:numel(Vq_kn)
        v = Vq_kn(k);
        if any(abs(Vd_kn - v) <= tol)
            prov{k} = 'supplied';
        elseif v >= lo - tol && v <= hi + tol
            prov{k} = 'interpolated';
        else
            prov{k} = 'extrapolated';
        end
    end

    % --- assemble ------------------------------------------------------
    res.V_ms            = V_ms;
    res.V_kn            = Vq_kn;
    res.R_N             = R_N;
    res.P_E_W           = R_N .* V_ms;      % effective power = R_T * V
    res.provenance      = prov;
    res.anyExtrapolated = any(strcmp(prov(:), 'extrapolated'));
    res.V_range_kn      = [lo hi];
    res.method          = 'pchip';

    if isfield(r, 'source')
        res.source = r.source;
    else
        res.source = 'unspecified';
    end
    if isfield(r, 'method')
        res.method = r.method;
    end

    res.case = caseName;
    if isfield(r, 'mass_kg')
        res.displacement_kg = r.mass_kg;
    end
end
