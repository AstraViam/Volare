function res = bem_rear_rotor(g, flow, op, params)
%BEM_REAR_ROTOR  Blade element momentum solution for the AFT rotor.
%
%   res = BEM_REAR_ROTOR(g, flow, op, params)
%
%   A thin wrapper on BEM_ROTOR, for the reasons given in bem_front_rotor.m.
%   The solver is shared; only the inflow differs.
%
%   FOR THE REAR ROTOR the inflow is NOT the ship speed. It is the front
%   rotor's slipstream: accelerated axially, contracted radially, and
%   carrying swirl. crp_interaction.m builds that flow field and passes it in
%   through flow.Va and flow.Vt.
%
%   flow.Vt is positive when the incoming fluid swirls OPPOSITE to this
%   rotor's own rotation, which is the contra-rotating case and is what adds
%   to the blade's relative tangential velocity. Recovering that swirl as
%   useful thrust is the whole reason for the second rotor, and it falls out
%   of the momentum balance rather than being applied as an efficiency
%   factor.
%
%   A rear rotor solved with flow.Va equal to the ship speed and flow.Vt zero
%   is not a contra-rotating model, it is two independent propellers on one
%   shaft. This wrapper warns when that looks to be the case.
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

    if nargin < 4
        error('bem_rear_rotor:args', ...
              'usage: bem_rear_rotor(g, flow, op, params)');
    end

    if isfield(flow, 'Vt') && all(abs(flow.Vt) < 1e-12)
        warning('bem_rear_rotor:noswirl', ...
               ['the rear rotor was given zero pre-swirl everywhere. It sits ' ...
                'in the front rotor''s slipstream and should see swirl; with ' ...
                'none, this is two independent propellers rather than a ' ...
                'contra-rotating pair. Check crp_interaction.m.']);
    end

    res = bem_rotor(g, flow, op, params);
    res.rotor = 'rear';
end
