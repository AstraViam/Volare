function F = prandtl_loss(r, R, r_hub, phi, Z)
%PRANDTL_LOSS  Combined tip and hub loss factor for blade element momentum.
%
%   F = PRANDTL_LOSS(r, R, r_hub, phi, Z)
%
%   r     : radial station(s), m
%   R     : tip radius, m
%   r_hub : hub radius, m
%   phi   : inflow angle at the station, rad
%   Z     : blade count
%
%   WHAT IT CORRECTS
%
%   Momentum theory treats the rotor as a disc with infinitely many blades,
%   so every annulus is worked uniformly. A real rotor has Z blades, and near
%   the tip the pressure difference must vanish because flow escapes around
%   the blade end. The same happens at the root against the hub. Prandtl's
%   correction reduces the momentum-derived induction to account for it:
%
%       f_tip = (Z/2) * (R - r) / (r * sin(phi))
%       F_tip = (2/pi) * acos(exp(-f_tip))
%
%   and identically at the hub with (r - r_hub)/(r_hub * sin(phi)). The two
%   multiply.
%
%   WITHOUT IT the blade element method loads the tip as heavily as mid-span
%   and overpredicts thrust, badly for a low blade count. With three blades
%   the tip factor at the outermost station is typically 0.3 to 0.6, so the
%   error it removes is not small.
%
%   NUMERICAL NOTES
%
%   F appears in a denominator in the induction terms, so it is floored at a
%   small positive value. It approaches zero legitimately at r = R, which is
%   exactly why propeller_geometry.m places no station there: a station at
%   the tip would drive the induction to infinity and force the solver onto
%   its clamp.
%
%   sin(phi) near zero makes f large, exp(-f) tends to zero, acos tends to
%   pi/2 and F tends to 1, which is the correct limit: an axially aligned
%   flow has no tip escape to correct for.
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

    if nargin < 5
        error('prandtl_loss:args', 'usage: prandtl_loss(r, R, r_hub, phi, Z)');
    end
    if R <= 0 || r_hub < 0 || r_hub >= R
        error('prandtl_loss:radii', ...
              'need 0 <= r_hub < R; got r_hub = %g, R = %g', r_hub, R);
    end
    if Z < 1
        error('prandtl_loss:Z', 'blade count must be at least 1');
    end

    r = r(:).';
    phi = phi(:).';
    if isscalar(phi) && numel(r) > 1
        phi = repmat(phi, size(r));
    elseif isscalar(r) && numel(phi) > 1
        r = repmat(r, size(phi));
    end
    if numel(r) ~= numel(phi)
        error('prandtl_loss:size', ...
              'r has %d elements but phi has %d', numel(r), numel(phi));
    end

    % Keep sin(phi) away from zero. phi is clamped to (0, pi/2) by the caller,
    % but the first iterations of a cold start can arrive here at the edge.
    sphi = max(abs(sin(phi)), 1e-9);

    % Stations must lie strictly inside the annulus for the correction to be
    % meaningful; clamp rather than return a complex or infinite factor.
    rc = min(max(r, r_hub * (1 + 1e-12)), R * (1 - 1e-12));

    f_tip = (Z / 2) * (R - rc) ./ (rc .* sphi);
    f_hub = (Z / 2) * (rc - r_hub) ./ (r_hub * sphi);

    % exp(-f) lies in (0, 1] for f >= 0, so acos is always in domain. Clamp
    % anyway against round-off pushing it a few ulps past 1.
    F_tip = (2/pi) * acos(min(max(exp(-f_tip), 0), 1));
    F_hub = (2/pi) * acos(min(max(exp(-f_hub), 0), 1));

    F = F_tip .* F_hub;
    F = max(F, 1e-6);          % appears in a denominator downstream
end
