% CI entry point. A script, not a function, because Octave loads a function
% file from the command line without calling it.
%
%   octave --no-gui --quiet tests/ci.m
%
% Exits 0 when every gate passes, 1 otherwise, so the build fails loudly.

here = fileparts(mfilename('fullpath'));
if isempty(here), here = pwd; end
addpath(here);
addpath(fileparts(here));

ok = run_tests();

if ok
    exit(0);
else
    exit(1);
end
