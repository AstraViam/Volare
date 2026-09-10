function Prop = P50B_Propeller(varargin)
%P50B_PROPELLER  Open-water propeller with a Wageningen-like KT/KQ shape.
%
%   Prop = P50B_Propeller() builds the propeller from
%   params/volare_params.json.
%
%   OPTIONS
%     "Diameter_m"   override the diameter
%     "PitchRatio"   override P/D
%     "Verbose"      logical, default false
%
%   RETURNS a struct of functions taking (v, n) where v is boat speed in
%   m/s through the water and n is propeller speed in rev/s:
%
%     Prop.AdvanceRatio(v,n)       J
%     Prop.Thrust_N(v,n)           T
%     Prop.Torque_Nm(v,n)          Q
%     Prop.ShaftPower_W(v,n)       P delivered to the propeller
%     Prop.OpenWaterEff(v,n)       eta_o
%     Prop.Slip(v,n)               apparent slip
%     Prop.CavitationNumber(v,n)   sigma at 0.7R
%     Prop.RPSForPower(v,P)        invert power to shaft speed
%
%   WHY THE PROPELLER IS WORTH THIS MUCH ATTENTION
%   ----------------------------------------------
%   A mismatched propeller costs twenty to twenty-five points of
%   open-water efficiency. At race power that is five to ten kilowatts --
%   more than any cooling, aerodynamic or interconnect change available
%   anywhere else in this project, and it costs nothing but choosing the
%   right part. It is also the cheapest thing to get wrong, because a
%   propeller that is close to right still pushes the boat along and
%   gives no obvious symptom.
%
%   Under a hard power cap this matters more than usual, not less. The
%   25 kW ceiling of ENERGY_REQ_188 means efficiency is the only route
%   left to speed: the boat cannot answer a bad propeller with more
%   power the way an unrestricted one could.
%
%   THE COEFFICIENTS
%   ----------------
%   KT and KQ are linear-plus-quadratic fits in advance ratio, scaled on
%   pitch ratio. They reproduce the shape of a Wageningen B-series chart
%   over the working range of J and are adequate for system studies. They
%   are NOT a substitute for the manufacturer's open-water curve, and are
%   tagged as an assumption for that reason. Competr supplies a
%   counter-rotating pair, whose real curves will differ.
%
%   See also P50B_HullModel, P50B_BoatDynamics, P50B_MatchPropeller.

    %% =========================================================
    % OPTIONS
    %% =========================================================

    opts = struct("Diameter_m",[],"PitchRatio",[],"Verbose",false);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_Propeller:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    C = P50B_HydroConstants();

    Pt = P50B_LoadParams();
    P  = P50B_LoadParams("Plain",true);

    B = P.boat;

    D  = B.prop_diameter_m;
    PD = B.prop_pitch_ratio;

    if ~isempty(opts.Diameter_m); D  = opts.Diameter_m;  end
    if ~isempty(opts.PitchRatio); PD = opts.PitchRatio;  end

    w     = B.wake_fraction;
    tDed  = B.thrust_deduction;
    etaR  = B.rel_rotative_eff;
    gear  = P.motor.gearbox_ratio;

    rho = C.RhoSeawater;

    %% =========================================================
    % COEFFICIENTS
    %% =========================================================

    function J = advanceRatio(v,n)

        va = v * (1 - w);

        J = va ./ max(n * D, 1e-6);

    end

    KT = @(J) max(0.0,  0.36*PD  - 0.32*J  - 0.06*J.^2);
    KQ = @(J) max(1e-4, 0.055*PD - 0.036*J - 0.008*J.^2);

    function T = thrust(v,n)

        T = KT(advanceRatio(v,n)) .* rho .* n.^2 .* D^4;

    end

    function Q = torque(v,n)

        Q = KQ(advanceRatio(v,n)) .* rho .* n.^2 .* D^5;

    end

    function P_W = shaftPower(v,n)

        P_W = 2*pi * n .* torque(v,n) / etaR;

    end

    function e = openWaterEff(v,n)

        J = advanceRatio(v,n);

        e = min(max(J .* KT(J) ./ (2*pi*KQ(J)), 0), 0.85);

    end

    function s = slip(v,n)

        theoretical = n * PD * D;

        s = min(max(1 - v*(1-w) ./ max(theoretical,1e-6), -0.5), 1.0);

    end

    function sigma = cavitationNumber(v,n,depth_m)

        if nargin < 3 || isempty(depth_m)
            depth_m = 0.25;
        end

        p = C.AtmosphericPressure_Pa + ...
            rho * C.Gravity * depth_m - C.VapourPressure_Pa;

        vr = sqrt(max(v,0.1).^2 + (0.7*pi*n*D).^2);

        sigma = p ./ (0.5 * rho * vr.^2);

    end

    %% ---------------------------------------------------------
    % Invert power to shaft speed
    %
    % Shaft power is monotone increasing in n at fixed v, so a
    % bisection is both safe and exact to the tolerance chosen.
    % A Newton iteration would be faster but can leave the
    % bracket when KT clips to zero at high advance ratio, and
    % this is not in an inner loop that needs the speed.
    %% ---------------------------------------------------------

    function n = rpsForPower(v,P_shaft_W)

        if P_shaft_W <= 0
            n = 0;
            return;
        end

        lo = 0.5;
        hi = 180.0;

        for it = 1:40

            mid = 0.5*(lo + hi);

            if shaftPower(v,mid) < P_shaft_W
                lo = mid;
            else
                hi = mid;
            end

        end

        n = 0.5*(lo + hi);

    end

    %% =========================================================
    % ASSEMBLE
    %% =========================================================

    Prop = struct();

    Prop.Diameter_m         = D;
    Prop.PitchRatio         = PD;
    Prop.BladeAreaRatio     = B.prop_blade_area_ratio;
    Prop.NumberOfBlades     = B.prop_n_blades;
    Prop.WakeFraction       = w;
    Prop.ThrustDeduction    = tDed;
    Prop.RelativeRotativeEff = etaR;
    Prop.GearRatio          = gear;

    Prop.AdvanceRatio       = @advanceRatio;
    Prop.KT                 = KT;
    Prop.KQ                 = KQ;
    Prop.Thrust_N           = @thrust;
    Prop.Torque_Nm          = @torque;
    Prop.ShaftPower_W       = @shaftPower;
    Prop.OpenWaterEff       = @openWaterEff;
    Prop.Slip               = @slip;
    Prop.CavitationNumber   = @cavitationNumber;
    Prop.RPSForPower        = @rpsForPower;

    Prop.P = struct( ...
        "Diameter_m",       Pt.boat.prop_diameter_m, ...
        "PitchRatio",       Pt.boat.prop_pitch_ratio, ...
        "BladeAreaRatio",   Pt.boat.prop_blade_area_ratio, ...
        "NumberOfBlades",   Pt.boat.prop_n_blades, ...
        "WakeFraction",     Pt.boat.wake_fraction, ...
        "ThrustDeduction",  Pt.boat.thrust_deduction, ...
        "GearRatio",        Pt.motor.gearbox_ratio);

    if opts.Verbose

        fprintf("\nPROPELLER\n");
        fprintf("  Diameter                 : %.0f mm\n",D*1000);
        fprintf("  Pitch ratio              : %.2f\n",PD);
        fprintf("  Blades                   : %d at BAR %.2f\n", ...
            Prop.NumberOfBlades,Prop.BladeAreaRatio);
        fprintf("  Wake fraction            : %.3f\n",w);
        fprintf("  Thrust deduction         : %.3f\n",tDed);
        fprintf("  Gearbox ratio            : %.2f motor rev per prop rev\n",gear);

    end

end
