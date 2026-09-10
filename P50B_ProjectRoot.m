function root = P50B_ProjectRoot()
%P50B_PROJECTROOT  Absolute path to the project root directory.
%
%   root = P50B_ProjectRoot() returns the top-level P50B_26S21P folder,
%   resolved from this file's own location rather than from pwd.
%
%   Every file-reading function in the project uses this instead of a
%   relative path, so that data loads correctly no matter which folder
%   MATLAB happens to be sitting in when a script is run.

    thisFile = mfilename("fullpath");

    commonFolder = fileparts(thisFile);      % .../P50B_26S21P/00_common

    root = fileparts(commonFolder);          % .../P50B_26S21P

end
