function C = P50B_HydroConstants()
%P50B_HYDROCONSTANTS  Fluid and unit constants shared by the boat model.
%
%   C = P50B_HydroConstants() returns the constants used by the hull,
%   propeller and dynamics models.
%
%   These are held in one place, and are deliberately identical to the
%   module-level constants at the top of python/volare/boat.py. If the
%   two ever drift, the MATLAB and Python boats stop being the same boat
%   and tools/crosscheck.py will say so -- which is the point.
%
%   Seawater, not fresh water. Monaco is the Mediterranean, and 1025
%   against 998 kg/m3 is 2.7% on every hydrodynamic force in the model.
%
%   See also P50B_HullModel, P50B_Propeller, P50B_BoatDynamics.

    C = struct();

    C.Gravity             = 9.80665;      % m/s^2
    C.RhoSeawater         = 1025.0;       % kg/m^3
    C.KinematicViscosity  = 1.05e-6;      % m^2/s, seawater near 20 degC
    C.RhoAir              = 1.20;         % kg/m^3
    C.VapourPressure_Pa   = 2340.0;       % water at ~20 degC
    C.AtmosphericPressure_Pa = 101325.0;

    C.KmhPerMs            = 3.6;
    C.KnotsPerMs          = 1.9438445;
    C.NauticalMile_m      = 1852.0;

end
