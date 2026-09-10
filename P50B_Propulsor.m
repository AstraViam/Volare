function Prop = P50B_Propulsor(varargin)
%P50B_PROPULSOR  The contra-rotating propulsor, from the BEM design.
%
%   Prop = P50B_Propulsor() returns a propulsor object with the same
%   interface as P50B_Propeller, built on the hydrodynamics team's
%   optimised coaxial contra-rotating design rather than on a generic
%   single-screw correlation.
%
%   OPTIONS
%     "Verbose"        logical, default false
%     "FigureOfMerit"  static-thrust figure of merit, default 0.75
%
%   WHY THIS REPLACES P50B_Propeller AS THE DEFAULT
%   -----------------------------------------------
%   The Competr datasheet says the outboard has a contra-rotating
%   propeller. P50B_Propeller models one screw with a Wageningen-like
%   KT/KQ fit, which was always a stand-in and never described the
%   hardware. The gap is not academic: the single-screw stand-in reaches
%   an open-water efficiency of 0.45 at the boat's own top speed, and the
%   contra-rotating pair reaches 0.77. Half the propulsive loss in the
%   old model was an artefact of modelling the wrong machine.
%
%   The design behind these numbers is in 04_data/hydrodynamics/ --
%   blade element momentum per rotor with Prandtl tip and hub losses,
%   coupled through slipstream contraction and swirl transport, with the
%   rotor speed solved to meet the required thrust exactly. The rear
%   rotor recovers 49% of the front rotor's swirl, which is the entire
%   point of a contra-rotating pair and the thing a single-screw model
%   cannot represent at all.
%
%   WHY THIS IS NOT A SCALED KT/KQ CURVE
%   ------------------------------------
%   The obvious way to extend one solved point to other speeds is to
%   take the single-screw KT/KQ shape and scale it to pass through the
%   BEM answer. It does not work here, and the reason is worth knowing:
%   this propulsor runs at an advance ratio of 1.91 with a pitch ratio
%   of 1.995, and the generic KT form is NEGATIVE there. It was fitted
%   to conventional screws working near J of 0.4 to 0.9, and a
%   contra-rotating pair on a fast, lightly loaded boat is nowhere near
%   that. Scaling a correlation by the ratio of a real number to a
%   negative one produces a curve that looks like physics and is not.
%
%   So the extension is momentum theory instead, anchored on the BEM
%   solution:
%
%     thrust from power     T = eta_o(v) * P / V_a
%     static thrust limit   T = FoM * (2 rho A P^2)^(1/3)
%     actual                the smaller of the two
%
%   The first is exact at the design point by construction -- it is the
%   definition of open-water efficiency, evaluated at the efficiency BEM
%   computed. The second is the ideal-actuator static thrust, which is
%   what stops the first from returning infinite thrust at zero speed.
%
%   The efficiency away from the design point follows a smooth curve
%   pinned to zero at bollard pull and to the BEM value at the design
%   advance ratio. That shape is an interpolation, not a solve. It is
%   right where it is anchored and approximate either side, and
%   Prop.NearDesignPoint(v) reports how far away a query is. For a
%   number that matters at another speed, rerun the BEM tool there.
%
%   THE ROTORS TURN AT DIFFERENT SPEEDS
%   -----------------------------------
%   Front 808.5 rev/min, rear 718.7 rev/min, from one 1300 rev/min motor
%   through gear ratios of 1.6079 and 1.8088. A single "the gearbox
%   ratio" does not exist for this machine, so GearRatio here is the
%   FRONT ratio, because that is the shaft the motor sees, and the rear
%   ratio is carried beside it.
%
%   See also P50B_Propeller, P50B_HullModel, P50B_BoatDynamics.

    opts = struct("Verbose",false,"FigureOfMerit",0.75);

    for k = 1:2:numel(varargin)

        name = string(varargin{k});

        if ~isfield(opts,name)
            error("P50B_Propulsor:UnknownOption", ...
                "Unknown option '%s'.",name);
        end

        opts.(name) = varargin{k+1};

    end

    C = P50B_HydroConstants();

    Pt = P50B_LoadParams();
    P  = P50B_LoadParams("Plain",true);

    H = P.hydro;

    rho = C.RhoSeawater;

    %% =========================================================
    % THE DESIGN POINT
    %% =========================================================

    vDesign_ms = H.propulsor_design_speed_kn / C.KnotsPerMs;

    D_f = H.front_diameter_m;
    D_r = H.rear_diameter_m;

    n_f = H.front_rpm / 60;
    n_r = H.rear_rpm / 60;

    T_total = H.front_thrust_N + H.rear_thrust_N;

    P_design_W = H.crp_shaft_power_W;

    eta_design = H.crp_efficiency;

    w    = H.wake_fraction;
    tDed = H.thrust_deduction;

    gearFront = H.front_gear_ratio;
    gearRear  = H.rear_gear_ratio;

    A_disk = pi/4 * D_f^2;

    FoM = opts.FigureOfMerit;

    Va_design = vDesign_ms * (1 - w);

    J_design = Va_design / (n_f * D_f);

    %% ---------------------------------------------------------
    % Torque coefficient referred to the FRONT shaft
    %
    % The two rotors turn at different speeds, so the pair's
    % torques cannot simply be added at one speed. What is
    % conserved is POWER, so the equivalent front-shaft torque
    % is the total power divided by the front shaft's angular
    % velocity. Adding 75.90 and 46.16 N.m and calling the
    % result the propulsor's torque at 808 rev/min would
    % overstate the shaft power by 4.4%.
    %% ---------------------------------------------------------

    Q_equiv = P_design_W / (2*pi*n_f);

    KQ_design = Q_equiv / (rho * n_f^2 * D_f^5);
    KT_design = T_total  / (rho * n_f^2 * D_f^4);

    %% ---------------------------------------------------------
    % Self-check
    %
    % eta_o = J KT / (2 pi KQ) must return the CRP efficiency the
    % BEM tool reported. If it does not, the numbers copied out
    % of the design report are inconsistent with each other and
    % nothing downstream should be trusted.
    %% ---------------------------------------------------------

    eta_check = J_design * KT_design / (2*pi*KQ_design);

    if abs(eta_check - eta_design) > 0.005

        error("P50B_Propulsor:InconsistentDesignPoint", ...
            "The design point does not close: J KT / (2 pi KQ) = %.4f " + ...
            "but hydro.crp_efficiency = %.4f. Thrust, torque, speed " + ...
            "and efficiency in the hydro section disagree with each " + ...
            "other; check them against " + ...
            "04_data/hydrodynamics/design_report.txt.", ...
            eta_check,eta_design);

    end

    %% =========================================================
    % OPEN-WATER EFFICIENCY AGAINST SPEED
    %
    % Pinned to zero at bollard pull, where a propeller does work
    % but moves nothing, and to the BEM value at the design
    % advance ratio. f(x) = x(2 - x) with x = J/J_design is the
    % simplest smooth curve with a maximum exactly at the anchor,
    % which is what keeps the design point exact.
    %
    % Real open-water curves are not symmetric about their peak
    % and this one is. That is the price of having exactly one
    % solved point to work from.
    %% =========================================================

    function e = openWaterEffAtSpeed(v)

        x = abs(v) / vDesign_ms;

        shape = max(0, x .* (2 - x));

        e = min(eta_design * shape, 0.85);

    end

    %% =========================================================
    % THRUST
    %% =========================================================

    function T = thrustFromPower(v,P_shaft_W)

        P_shaft_W = max(P_shaft_W,0);

        %% -----------------------------------------------------
        % T = eta_o(v) P / V_a, with the speed cancelled
        % analytically.
        %
        % Both eta_o and V_a go to zero linearly at v = 0, so the
        % ratio has a finite limit -- but evaluating it as
        % written gives 0 divided by a floor, which is zero
        % thrust at rest, and a boat that cannot leave the dock.
        % Substituting eta_o = eta_d (v/vD)(2 - v/vD) and
        % V_a = v (1 - w) cancels v exactly:
        %
        %     T = eta_d P (2 - v/vD) / (vD (1 - w))
        %
        % which is well behaved everywhere and still returns the
        % BEM thrust at the design point.
        %% -----------------------------------------------------

        x = abs(v) / vDesign_ms;

        T_fromEff = eta_design .* P_shaft_W .* max(0, 2 - x) ./ ...
                    (vDesign_ms * (1 - w));

        %% -----------------------------------------------------
        % Ideal-actuator static thrust, derated by a figure of
        % merit. This is what caps the expression above near
        % bollard pull, where the efficiency relation stops
        % describing anything real.
        %% -----------------------------------------------------

        T_static = FoM * (2 * rho * A_disk * P_shaft_W.^2).^(1/3);

        T = min(T_fromEff, T_static);

    end

    %% ---------------------------------------------------------
    % Shaft speed for a given power
    %
    % P = 2 pi n Q = 2 pi KQ rho n^3 D^5, so n goes as the cube
    % root of power at fixed KQ. Holding KQ at its design value
    % reproduces the BEM shaft speed exactly at the design power
    % and gives the right leading behaviour either side. It is
    % used for reporting motor speed and for the gearbox check,
    % not for thrust, which comes from the momentum balance
    % above.
    %% ---------------------------------------------------------

    function n = rpsForPower(v,P_shaft_W) %#ok<INUSL>

        if P_shaft_W <= 0
            n = 0;
            return;
        end

        n = (P_shaft_W / (2*pi * KQ_design * rho * D_f^5))^(1/3);

    end

    %% =========================================================
    % INTERFACE COMPATIBLE WITH P50B_Propeller
    %
    % The boat model calls Thrust_N(v,n) and ShaftPower_W(v,n).
    % Here thrust is a function of POWER rather than of shaft
    % speed, so these convert through the same KQ relation. The
    % round trip Thrust_N(v, RPSForPower(v,P)) returns the thrust
    % at power P, which is what the caller means.
    %% =========================================================

    function P_W = shaftPower(v,n) %#ok<INUSL>

        P_W = 2*pi * KQ_design * rho * n.^3 * D_f^5;

    end

    function T = thrust(v,n)

        T = thrustFromPower(v, shaftPower(v,n));

    end

    function Q = torque(v,n)

        Q = shaftPower(v,n) ./ max(2*pi*n,1e-9);

    end

    function J = advanceRatio(v,n)

        J = v * (1 - w) ./ max(n * D_f, 1e-6);

    end

    function e = openWaterEff(v,n) %#ok<INUSD>

        e = openWaterEffAtSpeed(v);

    end

    function s = slip(v,n)

        theoretical = n * H.front_pitch_ratio * D_f;

        s = min(max(1 - v*(1-w) ./ max(theoretical,1e-6), -0.5), 1.0);

    end

    function sigma = cavitationNumber(v,n,depth_m)

        if nargin < 3 || isempty(depth_m)
            depth_m = 0.494;   % tip depth from the BEM report
        end

        p = C.AtmosphericPressure_Pa + ...
            rho * C.Gravity * depth_m - C.VapourPressure_Pa;

        vr = sqrt(max(v,0.1).^2 + (0.7*pi*n*D_f).^2);

        sigma = p ./ (0.5 * rho * vr.^2);

    end

    function [near,err] = nearDesignPoint(v)

        err = abs(v - vDesign_ms) / vDesign_ms;

        near = err <= 0.25;

    end

    %% =========================================================
    % ASSEMBLE
    %% =========================================================

    Prop = struct();

    Prop.Type               = "contra-rotating";
    Prop.Diameter_m         = D_f;
    Prop.RearDiameter_m     = D_r;
    Prop.PitchRatio         = H.front_pitch_ratio;
    Prop.RearPitchRatio     = H.rear_pitch_ratio;
    Prop.BladeAreaRatio     = H.front_EAR;
    Prop.NumberOfBlades     = H.front_blades;
    Prop.WakeFraction       = w;
    Prop.ThrustDeduction    = tDed;
    Prop.RelativeRotativeEff = 1.0;
    Prop.GearRatio          = gearFront;
    Prop.RearGearRatio      = gearRear;
    Prop.HubDiameter_m      = H.hub_diameter_m;
    Prop.AxialGap_m         = H.axial_gap_m;
    Prop.SwirlRecovery      = H.swirl_recovery_frac;
    Prop.NetRollTorque_Nm   = H.net_roll_torque_Nm;
    Prop.DiskArea_m2        = A_disk;
    Prop.FigureOfMerit      = FoM;

    Prop.DesignSpeed_ms     = vDesign_ms;
    Prop.DesignSpeed_knots  = H.propulsor_design_speed_kn;
    Prop.DesignThrust_N     = T_total;
    Prop.DesignShaftPower_W = P_design_W;
    Prop.DesignEfficiency   = eta_design;
    Prop.DesignAdvanceRatio = J_design;
    Prop.DesignKT           = KT_design;
    Prop.DesignKQ           = KQ_design;
    Prop.DesignRPM          = H.front_rpm;
    Prop.DesignRearRPM      = H.rear_rpm;
    Prop.EfficiencyCheck    = eta_check;

    Prop.AdvanceRatio       = @advanceRatio;
    Prop.Thrust_N           = @thrust;
    Prop.ThrustFromPower_N  = @thrustFromPower;
    Prop.Torque_Nm          = @torque;
    Prop.ShaftPower_W       = @shaftPower;
    Prop.OpenWaterEff       = @openWaterEff;
    Prop.Slip               = @slip;
    Prop.CavitationNumber   = @cavitationNumber;
    Prop.RPSForPower        = @rpsForPower;
    Prop.NearDesignPoint    = @nearDesignPoint;

    Prop.Provenance = "04_data/hydrodynamics/design_report.txt, " + ...
                      "optimised submerged 3/3, run 2026-08-24";

    Prop.P = struct( ...
        "Efficiency",     Pt.hydro.crp_efficiency, ...
        "FrontDiameter_m",Pt.hydro.front_diameter_m, ...
        "RearDiameter_m", Pt.hydro.rear_diameter_m, ...
        "FrontGearRatio", Pt.hydro.front_gear_ratio, ...
        "RearGearRatio",  Pt.hydro.rear_gear_ratio, ...
        "WakeFraction",   Pt.hydro.wake_fraction, ...
        "ThrustDeduction",Pt.hydro.thrust_deduction);

    if opts.Verbose

        fprintf("\nCONTRA-ROTATING PROPULSOR\n");
        fprintf("  Source                   : %s\n",Prop.Provenance);
        fprintf("  Front rotor              : %.0f mm, %d blades, " + ...
            "P/D %.3f, %.0f rpm\n", ...
            D_f*1000,Prop.NumberOfBlades,Prop.PitchRatio,H.front_rpm);
        fprintf("  Rear rotor               : %.0f mm, %d blades, " + ...
            "P/D %.3f, %.0f rpm\n", ...
            D_r*1000,H.rear_blades,H.rear_pitch_ratio,H.rear_rpm);
        fprintf("  Gear ratios              : %.4f front, %.4f rear\n", ...
            gearFront,gearRear);
        fprintf("  Design point             : %.1f knots, %.0f N, %.2f kW\n", ...
            Prop.DesignSpeed_knots,T_total,P_design_W/1000);
        fprintf("  System efficiency        : %.4f " + ...
            "(closure check %.4f)\n",eta_design,eta_check);
        fprintf("  Equivalent J / KT / KQ   : %.4f / %.4f / %.4f\n", ...
            J_design,KT_design,KQ_design);
        fprintf("  Swirl recovered by rear  : %.1f %%\n", ...
            100*H.swirl_recovery_frac);
        fprintf("  Net roll reaction        : %.1f Nm -- the pair does " + ...
            "NOT self-cancel\n",H.net_roll_torque_Nm);
        fprintf("  Static thrust at %.1f kW  : %.0f N (FoM %.2f)\n", ...
            P_design_W/1000,thrustFromPower(0,P_design_W),FoM);

    end

end
