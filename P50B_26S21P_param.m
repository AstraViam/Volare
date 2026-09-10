%% Battery parameters

%% ModuleType1
ModuleType1.BatteryCapacityCell = 27; % Battery capacity, A*hr
ModuleType1.SOCBreakpointsCell = [0, .1, .25, .5, .75, .9, 1]; % State of charge breakpoints, SOC
ModuleType1.TemperatureBreakpointsCell = [278, 293, 313]; % Temperature breakpoints, T, K
ModuleType1.OpenCircuitVoltageThermalCell = [3.49, 3.5, 3.51; 3.55, 3.57, 3.56; 3.62, 3.63, 3.64; 3.71, 3.71, 3.72; 3.91, 3.93, 3.94; 4.07, 4.08, 4.08; 4.19, 4.19, 4.19]; % Open-circuit voltage, OCV(SOC,T), V
ModuleType1.VoltageRangeCell = [0, inf]; % Terminal voltage operating range, [Min Max], V
ModuleType1.ResistanceSOCBreakpointsCell = [0, .1, .25, .5, .75, .9, 1]; % State of charge breakpoints for resistance, SOC
ModuleType1.ResistanceTemperatureBreakpointsCell = [278, 293, 313]; % Temperature breakpoints for resistance, T, K
ModuleType1.R0ThermalCell = [.0117, .0085, .009; .011, .0085, .009; .0114, .0087, .0092; .0107, .0082, .0088; .0107, .0083, .0091; .0113, .0085, .0089; .0116, .0085, .0089]; % Instantaneous resistance, R0(SOC,T), Ohm
ModuleType1.BatteryThermalMassCell = 100; % Battery thermal mass, J/K

%% ParallelAssemblyType1
ParallelAssemblyType1.BatteryCapacityCell = 27; % Battery capacity, A*hr
ParallelAssemblyType1.SOCBreakpointsCell = [0, .1, .25, .5, .75, .9, 1]; % State of charge breakpoints, SOC
ParallelAssemblyType1.TemperatureBreakpointsCell = [278, 293, 313]; % Temperature breakpoints, T, K
ParallelAssemblyType1.OpenCircuitVoltageThermalCell = [3.49, 3.5, 3.51; 3.55, 3.57, 3.56; 3.62, 3.63, 3.64; 3.71, 3.71, 3.72; 3.91, 3.93, 3.94; 4.07, 4.08, 4.08; 4.19, 4.19, 4.19]; % Open-circuit voltage, OCV(SOC,T), V
ParallelAssemblyType1.VoltageRangeCell = [0, inf]; % Terminal voltage operating range, [Min Max], V
ParallelAssemblyType1.ResistanceSOCBreakpointsCell = [0, .1, .25, .5, .75, .9, 1]; % State of charge breakpoints for resistance, SOC
ParallelAssemblyType1.ResistanceTemperatureBreakpointsCell = [278, 293, 313]; % Temperature breakpoints for resistance, T, K
ParallelAssemblyType1.R0ThermalCell = [.0117, .0085, .009; .011, .0085, .009; .0114, .0087, .0092; .0107, .0082, .0088; .0107, .0083, .0091; .0113, .0085, .0089; .0116, .0085, .0089]; % Instantaneous resistance, R0(SOC,T), Ohm
ParallelAssemblyType1.BatteryThermalMassCell = 100; % Battery thermal mass, J/K

%% Battery initial targets

%% ModuleAssembly1.Module1
ModuleAssembly1.Module1.socCell = repmat(1, 273, 1); % Cell state of charge
ModuleAssembly1.Module1.batteryVoltage = repmat(0, 273, 1); % Terminal voltage, V
ModuleAssembly1.Module1.batteryCurrent = repmat(0, 273, 1); % Current (positive in), A
ModuleAssembly1.Module1.numCycles = repmat(0, 273, 1); % Discharge cycles
ModuleAssembly1.Module1.batteryTemperature = repmat(298.15, 273, 1); % Temperature, K
ModuleAssembly1.Module1.vParallelAssembly = repmat(0, 13, 1); % Parallel Assembly Voltage, V
ModuleAssembly1.Module1.socParallelAssembly = repmat(1, 13, 1); % Parallel Assembly state of charge

%% ModuleAssembly1.Module2
ModuleAssembly1.Module2.socCell = repmat(1, 273, 1); % Cell state of charge
ModuleAssembly1.Module2.batteryVoltage = repmat(0, 273, 1); % Terminal voltage, V
ModuleAssembly1.Module2.batteryCurrent = repmat(0, 273, 1); % Current (positive in), A
ModuleAssembly1.Module2.numCycles = repmat(0, 273, 1); % Discharge cycles
ModuleAssembly1.Module2.batteryTemperature = repmat(298.15, 273, 1); % Temperature, K
ModuleAssembly1.Module2.vParallelAssembly = repmat(0, 13, 1); % Parallel Assembly Voltage, V
ModuleAssembly1.Module2.socParallelAssembly = repmat(1, 13, 1); % Parallel Assembly state of charge

% Suppress MATLAB editor message regarding readability of repmat
%#ok<*REPMAT>

%% Battery parameters

%% ModuleType1
ModuleType1.BatteryCapacityCell = 27; % Battery capacity, A*hr
ModuleType1.SOCBreakpointsCell = [0, .1, .25, .5, .75, .9, 1]; % State of charge breakpoints, SOC
ModuleType1.TemperatureBreakpointsCell = [278, 293, 313]; % Temperature breakpoints, T, K
ModuleType1.OpenCircuitVoltageThermalCell = [3.49, 3.5, 3.51; 3.55, 3.57, 3.56; 3.62, 3.63, 3.64; 3.71, 3.71, 3.72; 3.91, 3.93, 3.94; 4.07, 4.08, 4.08; 4.19, 4.19, 4.19]; % Open-circuit voltage, OCV(SOC,T), V
ModuleType1.VoltageRangeCell = [0, inf]; % Terminal voltage operating range, [Min Max], V
ModuleType1.ResistanceSOCBreakpointsCell = [0, .1, .25, .5, .75, .9, 1]; % State of charge breakpoints for resistance, SOC
ModuleType1.ResistanceTemperatureBreakpointsCell = [278, 293, 313]; % Temperature breakpoints for resistance, T, K
ModuleType1.R0ThermalCell = [.0117, .0085, .009; .011, .0085, .009; .0114, .0087, .0092; .0107, .0082, .0088; .0107, .0083, .0091; .0113, .0085, .0089; .0116, .0085, .0089]; % Instantaneous resistance, R0(SOC,T), Ohm
ModuleType1.BatteryThermalMassCell = 100; % Battery thermal mass, J/K

%% ParallelAssemblyType1
ParallelAssemblyType1.BatteryCapacityCell = 27; % Battery capacity, A*hr
ParallelAssemblyType1.SOCBreakpointsCell = [0, .1, .25, .5, .75, .9, 1]; % State of charge breakpoints, SOC
ParallelAssemblyType1.TemperatureBreakpointsCell = [278, 293, 313]; % Temperature breakpoints, T, K
ParallelAssemblyType1.OpenCircuitVoltageThermalCell = [3.49, 3.5, 3.51; 3.55, 3.57, 3.56; 3.62, 3.63, 3.64; 3.71, 3.71, 3.72; 3.91, 3.93, 3.94; 4.07, 4.08, 4.08; 4.19, 4.19, 4.19]; % Open-circuit voltage, OCV(SOC,T), V
ParallelAssemblyType1.VoltageRangeCell = [0, inf]; % Terminal voltage operating range, [Min Max], V
ParallelAssemblyType1.ResistanceSOCBreakpointsCell = [0, .1, .25, .5, .75, .9, 1]; % State of charge breakpoints for resistance, SOC
ParallelAssemblyType1.ResistanceTemperatureBreakpointsCell = [278, 293, 313]; % Temperature breakpoints for resistance, T, K
ParallelAssemblyType1.R0ThermalCell = [.0117, .0085, .009; .011, .0085, .009; .0114, .0087, .0092; .0107, .0082, .0088; .0107, .0083, .0091; .0113, .0085, .0089; .0116, .0085, .0089]; % Instantaneous resistance, R0(SOC,T), Ohm
ParallelAssemblyType1.BatteryThermalMassCell = 100; % Battery thermal mass, J/K

%% Battery initial targets

%% ModuleAssembly1.Module1
ModuleAssembly1.Module1.socCell = repmat(1, 273, 1); % Cell state of charge
ModuleAssembly1.Module1.batteryVoltage = repmat(0, 273, 1); % Terminal voltage, V
ModuleAssembly1.Module1.batteryCurrent = repmat(0, 273, 1); % Current (positive in), A
ModuleAssembly1.Module1.numCycles = repmat(0, 273, 1); % Discharge cycles
ModuleAssembly1.Module1.batteryTemperature = repmat(298.15, 273, 1); % Temperature, K
ModuleAssembly1.Module1.vParallelAssembly = repmat(0, 13, 1); % Parallel Assembly Voltage, V
ModuleAssembly1.Module1.socParallelAssembly = repmat(1, 13, 1); % Parallel Assembly state of charge

%% ModuleAssembly1.Module2
ModuleAssembly1.Module2.socCell = repmat(1, 273, 1); % Cell state of charge
ModuleAssembly1.Module2.batteryVoltage = repmat(0, 273, 1); % Terminal voltage, V
ModuleAssembly1.Module2.batteryCurrent = repmat(0, 273, 1); % Current (positive in), A
ModuleAssembly1.Module2.numCycles = repmat(0, 273, 1); % Discharge cycles
ModuleAssembly1.Module2.batteryTemperature = repmat(298.15, 273, 1); % Temperature, K
ModuleAssembly1.Module2.vParallelAssembly = repmat(0, 13, 1); % Parallel Assembly Voltage, V
ModuleAssembly1.Module2.socParallelAssembly = repmat(1, 13, 1); % Parallel Assembly state of charge

% Suppress MATLAB editor message regarding readability of repmat
%#ok<*REPMAT>
