% Portability and parse check for the MATLAB sources.
%
% Runs under GNU Octave, which is what CI has. Two jobs:
%   1. Every .m file must parse.
%   2. No file may use MATLAB-only syntax that Octave cannot read.
%
% This exists because no Claude Code session and no CI runner has MATLAB.
% Without it, a syntax error or a `string()` call sits undetected until
% someone opens the project on a laptop. See propulsor/DESIGN.md section 2.
%
%   octave --no-gui --quiet tools/octave_check.m

more off;
root = fileparts(fileparts(mfilename('fullpath')));
dirs = {'propulsor'};          % add 'powertrain' once it is Octave-clean

% Constructs Octave 8 cannot parse. Each entry: {pattern, explanation}.
banned = {
  '^\s*arguments\s*$',      'arguments block (MATLAB R2019b+); validate inputs manually'
  '\<string\s*\(',          'string() type; use char arrays or cellstr'
  '\<dictionary\s*\(',      'dictionary() (MATLAB R2022b+); use struct or containers.Map'
  '^\s*classdef\>',         'classdef; prefer functions and structs here'
};

files = {};
for d = 1:numel(dirs)
    listing = dir(fullfile(root, dirs{d}, '*.m'));
    for k = 1:numel(listing)
        files{end+1} = fullfile(root, dirs{d}, listing(k).name); %#ok<AGROW>
    end
end

if isempty(files)
    printf('octave check: no .m files found\n');
    exit(0);
end

problems = {};
for k = 1:numel(files)
    [~, name] = fileparts(files{k});
    src = fileread(files{k});

    % 1. banned constructs
    for b = 1:size(banned, 1)
        lines = strsplit(src, "\n");
        for L = 1:numel(lines)
            if ~isempty(regexp(lines{L}, banned{b,1}, 'once'))
                problems{end+1} = sprintf('%s:%d  %s', name, L, banned{b,2}); %#ok<AGROW>
            end
        end
    end

    % 2. does Octave accept the file? A script with no leading `function`
    %    cannot be probed this way, so only functions are checked.
    if ~isempty(regexp(src, '^\s*function\>', 'once'))
        try
            eval(sprintf('h = @%s; clear h;', name));
        catch err
            problems{end+1} = sprintf('%s  will not parse: %s', name, err.message); %#ok<AGROW>
        end
    end
end

if isempty(problems)
    printf('octave check: %d file(s) clean\n', numel(files));
    exit(0);
end

printf('octave check: %d problem(s)\n\n', numel(problems));
for k = 1:numel(problems)
    printf('  - %s\n', problems{k});
end
exit(1);
