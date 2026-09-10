function U = units()
%UNITS  Unit conversion constants for the propulsor design tool.
%
%   U = UNITS() returns a struct of multiplicative conversion factors.
%
%   The project works in SI internally: m, kg, s, N, Pa, W, rad, rev/s.
%   Imperial and engineering units appear only at the boundaries, where a
%   supplier quotes a propeller in inches or a motor in RPM.
%
%   USE THE FACTORS, NOT LITERALS. Writing 0.0254 inline is how a unit bug
%   gets past review; writing `26.5 * U.in2m` does not.
%
%   Naming is always <from>2<to>, so the direction is unambiguous at the call
%   site and the reader never has to decide whether to multiply or divide.
%
%   Example
%     U = units();
%     D_m = 21 * U.in2m;          % 0.5334 m
%     n_rps = 2500 * U.rpm2rps;   % 41.667 rev/s
%
%   Team Volare / ICT Mumbai - MEBC Energy Class.

% --- length -------------------------------------------------------------
U.in2m    = 0.0254;              % international inch, exact by definition
U.m2in    = 1 / 0.0254;
U.ft2m    = 0.3048;              % exact
U.m2ft    = 1 / 0.3048;
U.mm2m    = 1e-3;
U.m2mm    = 1e3;

% --- speed --------------------------------------------------------------
% International nautical mile is 1852 m exactly, so 1 knot = 1852/3600 m/s.
U.kn2ms   = 1852 / 3600;         % 0.5144444...
U.ms2kn   = 3600 / 1852;
U.kmh2ms  = 1 / 3.6;
U.ms2kmh  = 3.6;

% --- distance -----------------------------------------------------------
U.nm2m    = 1852;                % nautical mile, exact
U.m2nm    = 1 / 1852;

% --- rotation -----------------------------------------------------------
% Two different things are called "speed" for a rotor. rev/s (n) is what the
% advance coefficient J = Va/(nD) needs; rad/s (omega) is what torque times
% speed needs for power. RPM is only ever for reporting.
U.rpm2rps = 1 / 60;              % rev/min -> rev/s
U.rps2rpm = 60;
U.rpm2rads = 2 * pi / 60;        % rev/min -> rad/s
U.rads2rpm = 60 / (2 * pi);
U.rps2rads = 2 * pi;             % rev/s   -> rad/s
U.rads2rps = 1 / (2 * pi);

% --- angle --------------------------------------------------------------
U.deg2rad = pi / 180;
U.rad2deg = 180 / pi;

% --- mass and force -----------------------------------------------------
U.lb2kg   = 0.45359237;          % exact
U.kg2lb   = 1 / 0.45359237;
U.g       = 9.80665;             % standard gravity, m/s^2 (ISO 80000-3)

% --- power and energy ---------------------------------------------------
U.hp2W    = 745.699871582;       % mechanical horsepower
U.W2hp    = 1 / 745.699871582;
U.kW2W    = 1e3;
U.W2kW    = 1e-3;
U.kWh2J   = 3.6e6;
U.J2kWh   = 1 / 3.6e6;
U.Wh2J    = 3600;
U.J2Wh    = 1 / 3600;

% --- pressure -----------------------------------------------------------
U.bar2Pa  = 1e5;
U.Pa2bar  = 1e-5;
U.atm2Pa  = 101325;              % standard atmosphere, exact
U.MPa2Pa  = 1e6;
U.Pa2MPa  = 1e-6;

end
