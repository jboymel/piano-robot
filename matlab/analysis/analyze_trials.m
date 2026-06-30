% Reads a CSV with columns: trial_num, timestamp, onset_time, fsr_peak_v
% Computes summary stats (mean, std, coefficient of variation) and
% generates diagnostic plots (onset time histogram, force distribution)

clear;
clc;

%% Configuration

dataDir   = fullfile(pwd, 'data');  % data/subfolder relative to wherever 
                                    % script is run from
csvPath   = fullfile(dataDir, 'trial_data.csv');
numTrials = 50;   % only used if falling back to fake data

if ~exist(dataDir, 'dir') 
    mkdir(dataDir);
end

%% Load real data, fall back to fake data if unavailable
try
    T = readtable(csvPath);   % detects column headers from first row
    fprintf('Loaded real data from %s\n', csvPath);
catch
    fprintf(['Could not load %s — generating placeholder data ' ...
        '(%d trials)...\n'], csvPath, numTrials);
    T = generate_fake_data(numTrials);
    writetable(T, csvPath);   % has something to load even if real 
                              % logging hasn't started
end

expectedCols = {'trial_num', 'timestamp', 'onset_time', 'fsr_peak_v'};

% Checks each expected name exists in the actual columns
missing = expectedCols(~ismember(expectedCols,T.Properties.VariableNames));
assert(isempty(missing), 'CSV is missing columns: %s', strjoin(missing, ', '));

%% Compute summary stats
onsetStats = trial_stats(T.onset_time);
forceStats = trial_stats(T.fsr_peak_v);
 
fprintf('\nOnset Time Stats (s):\n');
print_stats(onsetStats);
 
fprintf('\nFSR Peak Voltage Stats:\n');
print_stats(forceStats);

%% Onset time histogram 

figure('Name', 'Onset Time Distribution');
histogram(T.onset_time, 15, 'FaceColor', [0.2 0.4 0.8]);
xlabel('Onset Time (s)');
ylabel('Count');
title('Distribution of Onset Times');
grid on;
 
%% Force (FSR peak voltage) distribution
figure('Name', 'Force Distribution');
histogram(T.fsr_peak_v, 15, 'FaceColor', [0.8 0.3 0.2]);
xlabel('FSR Peak Voltage (V)');
ylabel('Count');
title('Distribution of FSR Peak Voltage');
grid on;
 
%% ================== Local Functions ====================

function T = generate_fake_data(n)
% Generates placeholder trial data with plausible ranges
%   trial_num   : 1..n
%   timestamp   : seconds since start, roughly evenly spaced w/ jitter
%   onset_time  : actuator onset latency, ~5-40 ms range (in seconds)
%   fsr_peak_v  : FSR 402 peak voltage under a 5V divider, ~0.2-4.5V
 
    trial_num  = (1:n)';
    timestamp  = cumsum(0.8 + 0.4*rand(n,1)); % timestamps increasing
    onset_time = (0.005 + 0.035*rand(n,1));   % 5-40 ms
    fsr_peak_v = 0.2 + 4.3*rand(n,1);         % 0.2-4.5 V
 
    T = table(trial_num, timestamp, onset_time, fsr_peak_v, ...
        'VariableNames', {'trial_num','timestamp','onset_time', ...
        'fsr_peak_v'});
end

function s = trial_stats(col)
% Computes mean, standard deviation, and coefficient of 
% variation for a numeric trial column.
    s.mean = mean(col);
    s.std  = std(col);
    if s.mean ~= 0   % avoid divide-by-zero if all values happen to be 0
        s.cv = 100 * s.std / s.mean;
    else
        s.cv = NaN;
    end
end

function print_stats(s)
    fprintf('Mean: %.5f\n', s.mean);
    fprintf('Std:  %.5f\n', s.std);
    fprintf('CV:   %.3f %%\n', s.cv);
end