function res = bem_front_rotor(g, flow, op, params)
%BEM_FRONT_ROTOR  Blade element momentum solution for the FORWARD rotor.
%
%   res = BEM_FRONT_ROTOR(g, flow, op, params)
%
%   A thin wrapper on BEM_ROTOR. The physics of the two rotors is identical;
%   they differ only in the inflow they see and their direction of rotation,
%   and both of those already arrive as arguments.
%
%   The wrapper exists because crp_interaction.m calls the two by name, which
%   reads better at the call site than bem_rotor(gF, ...) and bem_rotor(gR, ...)
%   and makes the coupled loop easier to follow. It deliberately does NOT
%   duplicate the solver: two copies of a blade element method drift apart,
%   and a bug fixed in one is then live in the other.
%
%   FOR THE FRONT ROTOR the inflow is the wake-corrected ship speed with no
%   pre-swirl, so flow.Vt is expected to be zero. An actuator disc induces no
%   tangential velocity ahead of itself, so the rear rotor cannot pre-swirl
%   the front one. A non-zero Vt here is a modelling error and is warned
%   about rather than silently accepted.
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

    if nargin < 4
        error('bem_front_rotor:args', ...
              'usage: bem_front_rotor(g, flow, op, params)');
    end

    if isfield(flow, 'Vt') && any(abs(flow.Vt) > 1e-9)
        warning('bem_front_rotor:preswirl', ...
               ['the front rotor was given non-zero pre-swirl (max |Vt| = ' ...
                '%.4g m/s). An actuator disc induces no tangential velocity ' ...
                'upstream of itself, so the rear rotor cannot swirl the ' ...
                'front one. Check crp_interaction.m.'], max(abs(flow.Vt)));
    end

    res = bem_rotor(g, flow, op, params);
    res.rotor = 'front';
end
