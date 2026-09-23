# Ground truth for swim_utility.py: SWIM's own utility computation, run as-is.
#
# plotResults() cannot be called directly without ggplot2, cowplot and friends,
# which exist only to draw the figure. So this sources SWIM's plotResults.R for
# its helper and utility functions -- periodicAverage, timeWeightedAverage,
# readVector, periodUtilitySEAMS2017A, periodUtilityICAC2016, unmodified -- and
# repeats the lines of plotResults() that compute totalUtility, copied verbatim
# apart from taking the file paths as arguments.
#
#   Rscript swim_utility_reference.R <plotResults.R> <run.sca> <run.vec> ...
suppressMessages(library(RSQLite))
args <- commandArgs(trailingOnly = TRUE)
source(args[1])

swimUtility <- function(scalarDBPath, vectorDBPath, utilityFc) {
  sdb <- dbConnect(RSQLite::SQLite(), scalarDBPath)
  scalars <- dbReadTable(sdb, "scalar")
  dbDisconnect(sdb)

  # ---- from plotResults(), verbatim ----
  network = scalars[scalars$scalarName=="maxServers", "moduleName"]
  bootDelay = scalars[scalars$scalarName=="bootDelay", "scalarValue"]
  evaluationPeriod = scalars[scalars$scalarName=="evaluationPeriod", "scalarValue"]
  RT_THRESHOLD_SEC = scalars[scalars$scalarName=="responseTimeThreshold", "scalarValue"]
  maxServers = scalars[scalars$scalarName=="maxServers", "scalarValue"]
  maxServiceRate = scalars[scalars$scalarName=="maxServiceRate", "scalarValue"]

  vdb <- dbConnect(RSQLite::SQLite(), vectorDBPath)
  servers <- readVector(vdb, "serverCost:vector")
  activeServers <- readVector(vdb, "activeServers:vector")
  dimmer <- transform(readVector(vdb, "brownoutFactor:vector"), y = 1 - y)
  responses <- readVector(vdb, "lifeTime:vector") # this gets both low and high
  avgInterarrival <- periodicAverage(readVector(vdb, "interArrival:vector"), evaluationPeriod)
  avgArrivalRate <- transform(avgInterarrival, y = 1 / y)

  start <- floor(min(servers$x) / evaluationPeriod) * evaluationPeriod
  end <- ceiling(max(servers$x) / evaluationPeriod) * evaluationPeriod
  avgresponse <- periodicAverage(responses, evaluationPeriod)

  dimmerMean <- timeWeightedAverage(dimmer, evaluationPeriod)
  dimmerMean$x = dimmerMean$x + evaluationPeriod
  serversMean <- timeWeightedAverage(servers, evaluationPeriod)
  serversMean$x = serversMean$x + evaluationPeriod

  avgArrivalRate <- subset(avgArrivalRate, x <= end)
  dimmerMean <- subset(dimmerMean, x <= end)
  serversMean <- subset(serversMean, x <= end)
  avgresponse <- subset(avgresponse, x <= end)

  utility <- as.data.frame(cbind(x=avgresponse$x,
                                 y=utilityFc(maxServers, maxServiceRate,
                                             avgArrivalRate$y, dimmerMean$y,
                                             evaluationPeriod, RT_THRESHOLD_SEC,
                                             avgresponse$y, serversMean$y)))
  totalUtility <- sum(utility$y)
  # ---- end verbatim ----
  dbDisconnect(vdb)
  totalUtility
}

paths <- args[-1]
for (i in seq(1, length(paths), by = 2)) {
  sca <- paths[i]; vec <- paths[i + 1]
  a <- swimUtility(sca, vec, periodUtilitySEAMS2017A)
  b <- swimUtility(sca, vec, periodUtilityICAC2016)
  cat(sprintf("%s\tSEAMS2017A\t%.6f\tICAC2016\t%.6f\n", basename(vec), a, b))
}
