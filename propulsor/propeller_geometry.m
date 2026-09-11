function g = propeller_geometry(design, params)
%PROPELLER_GEOMETRY  Build a blade from a handful of smooth shape numbers.
%
%   g = PROPELLER_GEOMETRY(design, params)
%
%   design : struct describing one rotor. Required fields:
%              .D_m      diameter, m
%              .Z        blade count
%              .P07_m    pitch at 0.7R, m
%            Optional, each defaulting to params.propeller.common:
%              .EAR      expanded area ratio
%              .hubRatio r_hub / R
%              .shape    overrides for the distribution control points
%              .skew_tip_deg, .rake_tip_deg
%              .nRadial  number of radial elements
%
%   Returns the struct bem_rotor.m and crp_interaction.m consume:
%     .D .R .Z .r_hub          scalars, m
%     .r .x .dr                radial stations, m and r/R
%     .c .theta .toc .foc      per station: chord m, pitch angle rad, t/c, f/c
%   plus, for reporting and CAD export:
%     .P .skew_deg .rake_m .A_expanded .EAR .pitchRatio07 .coords
%
%   WHY A SHAPE PARAMETERISATION
%
%   The optimiser could be given a free chord value at every radial station.
%   It should not be. Twenty-four independent chords produce a saw-toothed
%   blade that scores well against a blade-element model, because the model
%   integrates strip by strip and never sees the discontinuity, and that
%   blade cannot be manufactured. Independent stations also multiply the
%   search dimension for no physical gain, since a real blade has only a few
%   degrees of freedom worth having.
%
%   So each distribution is interpolated through a handful of control points.
%   The interpolant is pchip, which is shape preserving: it cannot overshoot
%   between knots, so a positive set of control chords can never produce a
%   negative chord in between. A cubic spline can, and would.
%
%   CELL-CENTRED STATIONS
%
%   Stations sit at the CENTRES of equal-width annuli, not at their edges.
%   This matters and is easy to get wrong. A station exactly at r = R puts
%   the Prandtl tip factor at zero, drives the momentum-derived induction to
%   infinity, forces the solver onto its clamp, and leaves spurious load on
%   an element that physically carries none. bem_rotor.m documents the same
%   choice; the two must agree.
%
%   CHORD SCALE AND EXPANDED AREA RATIO
%
%   The chord control points are a SHAPE only. Their scale is set so the
%   blade hits the requested expanded area ratio exactly:
%
%       EAR = Z * integral(c dr) / (pi*D^2/4)
%
%   so shape and area are independent design variables. Changing EAR does not
%   change the shape, and changing the shape does not change the area.
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

    if nargin < 2
        error('propeller_geometry:args', ...
              'usage: propeller_geometry(design, params)');
    end
    C = params.propeller.common;

    % --- required design variables ---------------------------------------
    req = {'D_m', 'Z', 'P07_m'};
    for k = 1:numel(req)
        if ~isfield(design, req{k})
            error('propeller_geometry:missing', ...
                  'design.%s is required', req{k});
        end
    end
    D = design.D_m;
    Z = design.Z;
    P07 = design.P07_m;

    % --- optional, with configured defaults ------------------------------
    EAR      = pick(design, 'EAR',          C.EAR_ref);
    hubRatio = pick(design, 'hubRatio',     C.D_hub_m / D);
    nRadial  = pick(design, 'nRadial',      C.nRadial);
    skewTip  = pick(design, 'skew_tip_deg', C.skew_tip_deg);
    rakeTip  = pick(design, 'rake_tip_deg', C.rake_tip_deg);
    sh       = pick(design, 'shape',        C.shape);

    % --- validate ---------------------------------------------------------
    if D <= 0,        error('propeller_geometry:D', 'diameter must be positive'); end
    if D > C.D_max_m + 1e-12
        error('propeller_geometry:Dmax', ...
              'diameter %.4f m exceeds the %.4f m limit (21 in)', D, C.D_max_m);
    end
    if ~any(Z == [2 3 4 5 6 7])
        error('propeller_geometry:Z', 'blade count %g is not a sensible integer', Z);
    end
    if P07 <= 0, error('propeller_geometry:P07', 'pitch must be positive'); end
    if hubRatio <= 0 || hubRatio >= 1
        error('propeller_geometry:hub', ...
              'hub ratio %.4f must lie in (0, 1); the hub cannot exceed the disc', ...
              hubRatio);
    end
    if EAR <= 0, error('propeller_geometry:EAR', 'EAR must be positive'); end
    if nRadial < 4
        error('propeller_geometry:nRadial', ...
              'need at least 4 radial elements, got %g', nRadial);
    end

    R = D / 2;
    r_hub = hubRatio * R;

    % --- cell-centred radial stations ------------------------------------
    edges = linspace(r_hub, R, nRadial + 1);
    r  = 0.5 * (edges(1:end-1) + edges(2:end));
    dr = diff(edges);
    x  = r / R;

    % --- distributions, pchip through the control points -----------------
    chordShape = pchip_at(sh.chord_x, sh.chord_val, x);
    if any(chordShape <= 0)
        error('propeller_geometry:chordShape', ...
              'chord shape went non-positive; check shape.chord_val');
    end

    % Scale the shape so the expanded area ratio comes out exactly right.
    A_disk = pi * D^2 / 4;
    shapeArea = sum(chordShape .* dr);
    kScale = EAR * A_disk / (Z * shapeArea);
    c = kScale * chordShape;

    % Pitch, quoted at 0.7R and shaped around it.
    P = P07 * pchip_at(sh.pitch_x, sh.pitch_ratio, x);
    theta = atan2(P, 2*pi*r);            % geometric pitch angle, rad

    % Section shape.
    toc_ = pchip_at(sh.toc_x, sh.toc_val, x);
    toc_ = max(toc_, C.toc_min);         % manufacturable floor
    foc  = pchip_at(sh.foc_x, sh.foc_val, x);

    % Skew and rake grow from zero at the hub to their tip values.
    xn = (x - hubRatio) / max(1 - hubRatio, eps);
    skew_deg = skewTip * xn .^ sh.skew_exp;
    rake_m   = (rakeTip * pi/180) * R * (xn .^ sh.rake_exp);

    % --- smoothness, the constraint that keeps the blade manufacturable ---
    dcdx = diff(c / D) ./ diff(x);
    smoothOK = all(abs(dcdx) <= C.dcdx_max);

    % --- assemble ---------------------------------------------------------
    g.D        = D;
    g.R        = R;
    g.Z        = Z;
    g.r_hub    = r_hub;
    g.hubRatio = hubRatio;
    g.r        = r;
    g.x        = x;
    g.dr       = dr;
    g.edges    = edges;
    g.c        = c;
    g.theta    = theta;
    g.toc      = toc_;
    g.foc      = foc;

    g.P            = P;
    g.P07_m        = P07;
    g.pitchRatio07 = P07 / D;
    g.skew_deg     = skew_deg;
    g.rake_m       = rake_m;
    g.A_expanded   = Z * sum(c .* dr);
    g.EAR          = g.A_expanded / A_disk;
    g.A_disk       = A_disk;
    g.chordScale   = kScale;
    g.smoothOK     = smoothOK;
    g.maxdcdx      = max(abs(dcdx));
    g.nRadial      = nRadial;

    % --- generating line, for CAD and CFD export -------------------------
    % Cylindrical coordinates of the section reference point at each station:
    % axial position from rake, angular position from skew.
    g.coords.r_m       = r;
    g.coords.x_over_R  = x;
    g.coords.axial_m   = rake_m;
    g.coords.theta_deg = skew_deg;
    g.coords.y_m       = r .* sin(skew_deg * pi/180);
    g.coords.z_m       = r .* cos(skew_deg * pi/180);
end

% =========================================================================
function v = pick(s, name, dflt)
    if isfield(s, name) && ~isempty(s.(name))
        v = s.(name);
    else
        v = dflt;
    end
end

% =========================================================================
function y = pchip_at(xc, yc, xq)
%PCHIP_AT  Shape-preserving interpolation, clamped to the control range.
%
%   Queries outside the control points are clamped rather than extrapolated.
%   A blade station can sit marginally outside the control span when the hub
%   ratio is unusual, and extrapolating a cubic there is how a negative chord
%   appears at the root.
    xc = xc(:).'; yc = yc(:).';
    if numel(xc) ~= numel(yc)
        error('propeller_geometry:shape', ...
              'shape has %d abscissae and %d values', numel(xc), numel(yc));
    end
    if any(diff(xc) <= 0)
        error('propeller_geometry:shape', 'shape abscissae must increase');
    end
    xq = min(max(xq, xc(1)), xc(end));
    y = interp1(xc, yc, xq, 'pchip');
end
