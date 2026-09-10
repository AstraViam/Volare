function [params, report] = load_inputs(params, inputs)
%LOAD_INPUTS  Ingest externally supplied data files into the parameter struct.
%
%   [params, report] = LOAD_INPUTS(params, inputs)
%
%   PURPOSE
%   config.m holds the DEFAULTS and the declared assumptions. This function is
%   the single place where MEASURED or CFD data replaces those assumptions, so
%   that (a) the core solver never has to be edited when new data arrives, and
%   (b) there is one auditable record of what was replaced and what is still
%   assumed. Every successful substitution removes the corresponding entry from
%   the assumption register, so print_assumptions.m automatically stops claiming
%   a value is assumed once it has been measured.
%
%   inputs is a struct; every field is optional:
%     .resistance300_csv   CSV with columns [speed_kn, resistance_N] for the
%                          300 kg condition. Replaces the "data unavailable"
%                          state and enables the displacement sensitivity case.
%     .wakeField_csv       CSV with columns [rR, w] from CFD. Switches
%                          hull_interaction.m off the uniform-wake model.
%     .polars_mat          .mat containing a struct with fields alpha [rad],
%                          Re, Cl, Cd (Cl/Cd sized numel(alpha) x numel(Re)).
%                          Replaces the provisional analytical section model.
%     .motorMap            function handle eta = f(rpm, torque), or a .mat file
%                          containing one in a variable named etaMap.
%     .material            struct of material properties to merge (rho, E, nu,
%                          sigma_yield, sigma_ult, sigma_fatigue).
%     .cfd                 struct merged into params.validation.cfd (may supply
%                          the missing thrust T_N and diameter D_m).
%     .cfdGeometry         design struct for validation.m to run the model at
%                          the CFD reference condition (fields as unpack_design
%                          produces: D, Z, P07, pitchSlope, EAR, cp1, cp2,
%                          fc_root, fc_tip, toc_root, toc_tip, hubRatio).
%
%   Nothing is silently defaulted: a requested file that cannot be read raises
%   an error rather than falling back to the assumption, because a silent
%   fallback is exactly how an unvalidated number reaches a build decision.

if nargin < 2 || isempty(inputs), inputs = struct(); end
report = {};

% ---- 300 kg resistance curve -------------------------------------------
if isfield(inputs,'resistance300_csv') && ~isempty(inputs.resistance300_csv)
    D = read_two_column(inputs.resistance300_csv);
    params.resistance.speed_kn_300  = D(:,1).';
    params.resistance.R_total_N_300 = D(:,2).';
    report{end+1} = sprintf('300 kg resistance curve loaded (%d points) from %s', ...
        size(D,1), inputs.resistance300_csv);
end

% ---- CFD wake field -----------------------------------------------------
if isfield(inputs,'wakeField_csv') && ~isempty(inputs.wakeField_csv)
    D = read_two_column(inputs.wakeField_csv);
    params.hull.wakeField    = D;
    params.hull.useWakeField = true;
    report{end+1} = sprintf('radial wake field loaded (%d points); uniform-wake model DISABLED', size(D,1));
    params = drop_assumption(params, 'Wake fraction w');
end

% ---- section polars ----------------------------------------------------
if isfield(inputs,'polars_mat') && ~isempty(inputs.polars_mat)
    L = load(inputs.polars_mat);
    fn = fieldnames(L);
    P = L.(fn{1});
    for req = {'alpha','Re','Cl','Cd'}
        if ~isfield(P, req{1})
            error('load_inputs:polars','Polar struct is missing field "%s".', req{1});
        end
    end
    params.polar.external    = P;
    params.polar.useExternal = true;
    params.polar.source      = sprintf('EXTERNAL tabulated polars from %s', inputs.polars_mat);
    report{end+1} = sprintf('section polars loaded: %d incidences x %d Reynolds numbers', ...
        numel(P.alpha), numel(P.Re));
    params = drop_assumption(params, 'Hydrofoil polars');
end

% ---- motor efficiency map ----------------------------------------------
if isfield(inputs,'motorMap') && ~isempty(inputs.motorMap)
    m = inputs.motorMap;
    if ischar(m)
        L = load(m);
        if ~isfield(L,'etaMap')
            error('load_inputs:motorMap','%s does not contain a variable named etaMap.', m);
        end
        m = L.etaMap;
    end
    if ~isa(m,'function_handle')
        error('load_inputs:motorMap','motorMap must be a function handle eta = f(rpm, torque).');
    end
    params.motor.etaMap = m;
    report{end+1} = 'motor efficiency map loaded; constant-efficiency assumption REPLACED';
end

% ---- material ----------------------------------------------------------
if isfield(inputs,'material') && ~isempty(inputs.material)
    f = fieldnames(inputs.material);
    for k = 1:numel(f)
        params.material.(f{k}) = inputs.material.(f{k});
    end
    report{end+1} = sprintf('material properties overridden: %s', strjoin_c(f, ', '));
    params = drop_assumption(params, 'Stainless steel properties');
end

% ---- CFD validation data ----------------------------------------------
if isfield(inputs,'cfd') && ~isempty(inputs.cfd)
    f = fieldnames(inputs.cfd);
    for k = 1:numel(f)
        params.validation.cfd.(f{k}) = inputs.cfd.(f{k});
    end
    report{end+1} = sprintf('CFD reference data updated: %s', strjoin_c(f, ', '));
end
if isfield(inputs,'cfdGeometry') && ~isempty(inputs.cfdGeometry)
    params.validation.geometry = inputs.cfdGeometry;
    report{end+1} = 'CFD propeller geometry supplied; validation.m will run the model against it';
end

if isempty(report)
    report{end+1} = 'No external inputs supplied: running entirely on config.m defaults and declared assumptions.';
end
end

% =========================================================================
function D = read_two_column(fname)
if ~exist(fname,'file')
    error('load_inputs:missingFile','Input file not found: %s', fname);
end
D = [];
fid = fopen(fname,'r');
while true
    ln = fgetl(fid);
    if ~ischar(ln), break; end
    ln = strtrim(ln);
    if isempty(ln) || ln(1) == '#' || ln(1) == '%', continue; end
    v = sscanf(strrep(ln, ',', ' '), '%f');
    if numel(v) >= 2, D(end+1,1:2) = v(1:2).'; end %#ok<AGROW>
end
fclose(fid);
if size(D,1) < 2
    error('load_inputs:badFile','%s yielded fewer than two usable rows.', fname);
end
[~,i] = sort(D(:,1));  D = D(i,:);
end

% =========================================================================
function params = drop_assumption(params, name)
%DROP_ASSUMPTION  Remove an entry from the assumption register once the value
%   has been measured, so the report stops calling it an assumption.
keep = {};
for k = 1:numel(params.assumptions)
    if ~strcmp(params.assumptions{k}.name, name)
        keep{end+1} = params.assumptions{k}; %#ok<AGROW>
    end
end
params.assumptions = keep;
end

% =========================================================================
function s = strjoin_c(c, sep)
if isempty(c), s = ''; return; end
s = c{1};
for k = 2:numel(c), s = [s sep c{k}]; end %#ok<AGROW>
end
