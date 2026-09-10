function ok = run_tests()
%RUN_TESTS  Run every propulsor test. Exit non-zero on failure.
%
%   From the propulsor/ directory, in MATLAB or Octave:
%       cd tests; run_tests
%
%   Headless, which is what CI does, via the script wrapper:
%       octave --no-gui --quiet tests/ci.m
%
%   Each DESIGN.md build stage has a test file here and must stay green before
%   the next stage starts. A stage without a passing gate is not finished, it
%   is merely written.

    here = fileparts(mfilename('fullpath'));
    if isempty(here), here = pwd; end
    addpath(fileparts(here));      % propulsor/ itself
    addpath(here);

    listing = dir(fullfile(here, 'test_*.m'));
    names = sort({listing.name});

    total = 0; failed = 0;
    fprintf('\n');
    for f = 1:numel(names)
        [~, fn] = fileparts(names{f});
        fprintf('%s\n', fn);
        fprintf('%s\n', repmat('-', 1, numel(fn)));
        T = feval(fn);
        for k = 1:numel(T)
            total = total + 1;
            if T(k).passed
                fprintf('  pass  %s\n', T(k).name);
            else
                failed = failed + 1;
                fprintf('  FAIL  %s\n', T(k).name);
                if ~isempty(T(k).detail)
                    fprintf('        %s\n', T(k).detail);
                end
            end
        end
        fprintf('\n');
    end

    fprintf('%d checks, %d failed\n\n', total, failed);
    ok = (failed == 0);

end
