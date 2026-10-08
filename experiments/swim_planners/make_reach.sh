#!/bin/bash
# Generate the PLA-SDP reachability relations for SWIM (the "rubis" models).
#
# Runs inside selas-swim-pla:dev (used by the Dockerfile at build time). It does
# what clayness/thallium's run_reach.sh does for `rubis`: substitute the scope
# placeholders in model/rubis.als and model/rubis-step.als, then run pladapt's
# Alloy-based `reach` tool once in immediate mode (-i) and once in step mode.
#
#   make_reach.sh OUTDIR [MAX_S MAX_P MAX_D]
#
# Defaults are thallium's default.env and the values hard-coded in the SWIM
# manager (DartConfigurationManager(12, 10, 3)): 12 servers, 3 add-server
# progress states (180 s boot / 60 s period), 10 dimmer levels.
set -euo pipefail

OUT="${1:?output directory}"
MAX_S="${2:-12}"; MAX_P="${3:-3}"; MAX_D="${4:-10}"
PLA=/headless/pla
MODELS="$PLA/thallium/model"
CP="$PLA/reach-bin:$PLA/reach-lib/alloy5.0.jar:$PLA/reach-lib/yamlbeans-1.11.jar"
export LD_LIBRARY_PATH="$PLA/reach-lib/amd64-linux${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

mkdir -p "$OUT"
for i in rubis.als rubis-step.als; do
    sed -E "s/\/\*MAX_SERVERS=\*\/ *[0-9]+/$MAX_S/" "$MODELS/$i" \
        | sed -E "s/\/\*MAX_PROGRESS=\*\/ *[0-9]+/$MAX_P/" \
        | sed -E "s/\/\*MAX_DIMMER=\*\/ *[0-9]+/$MAX_D/" > "$OUT/$i"
done
# reach does not overwrite an existing output file, so a stale one would win.
rm -f "$OUT/rubis.yaml" "$OUT/rubis-step.yaml"
java -classpath "$CP" reach.Reach -i "$OUT/rubis.als" "$OUT/rubis.yaml"
java -classpath "$CP" reach.Reach "$OUT/rubis-step.als" "$OUT/rubis-step.yaml"
test -s "$OUT/rubis.yaml" && test -s "$OUT/rubis-step.yaml"
echo "reachability relations written to $OUT"
