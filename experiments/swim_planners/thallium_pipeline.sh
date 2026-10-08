#!/bin/bash
# Thallium's trimming pipeline for SWIM, as clayness/thallium (fec1448) runs it
# in run_rubis.sh, inside selas-swim-pla:dev:
#
#   1. reach      the PLA relation (rubis.yaml, rubis-step.yaml) -- taken from
#                 the image, where make_reach.sh generated it at build time;
#   2. bounds     run_bounds.sh rubis: PRISM-games on model/rubis.smg, best /
#                 expected / worst arrivals, every initial configuration;
#   3. fuzzy      FuzzyValueCalculatorMain, per weighting;
#   4. Pareto     GraphTrimmerMain, per weighting -> trim<W>/trimmed.txt;
#   5. trim       thallium_trim.py (port of python/trim-rubis.py) -> trim<W>/rubis.yaml.
#
#   ./thallium_pipeline.sh OUTDIR
#
# Model constants come from the environment, defaulting to thallium's
# default.env (the values that reproduce the paper's Experiment 1). Weightings
# are thallium's default.weights unless WEIGHTS_FILE names another file.
#
# Two fixes to how run_rubis.sh calls run_bounds.sh, without editing either:
# run_rubis.sh passes the PRISM path where run_bounds.sh expects `rubis`, and
# run_bounds.sh tests MAX_DIMMER/MAX_PROGRESS/MAX_SERVERS, which default.env
# never sets (it sets MAX_D/MAX_P/MAX_S), so without them PRISM would analyse
# one initial configuration and the Java trimmer would fail on the rest.
set -euo pipefail

OUT="${1:?output directory}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
IMAGE="${SELAS_PLA_IMAGE:-selas-swim-pla:dev}"
PY="${SELAS_PYTHON:-$REPO/POLARIS/.venv/bin/python}"

: "${HORIZON:=10}" "${SECS_PER_STEP:=10}" "${SERVICE_RATE:=10}" "${DIMMER_ADJ:=1.15}"
: "${THRESHOLD:=3000}" "${SRV_COST_PER_HOUR:=0.10}" "${EXP_ARRIVAL_RATE:=42}"
: "${MAX_ARRIVAL_RATE:=200}" "${MAX_S:=12}" "${MAX_P:=3}" "${MAX_D:=10}"

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
PARAMS="HORIZON=$HORIZON SECS_PER_STEP=$SECS_PER_STEP SERVICE_RATE=$SERVICE_RATE DIMMER_ADJ=$DIMMER_ADJ
THRESHOLD=$THRESHOLD SRV_COST_PER_HOUR=$SRV_COST_PER_HOUR EXP_ARRIVAL_RATE=$EXP_ARRIVAL_RATE
MAX_ARRIVAL_RATE=$MAX_ARRIVAL_RATE MAX_S=$MAX_S MAX_P=$MAX_P MAX_D=$MAX_D
MAX_SERVERS=$MAX_S MAX_PROGRESS=$MAX_P MAX_DIMMER=$MAX_D"
echo "$PARAMS" | tr ' ' '\n' > "$OUT/params.env"
if [ -n "${WEIGHTS_FILE:-}" ]; then cp "$WEIGHTS_FILE" "$OUT/weights"; fi

docker run --rm --name "pla-thallium-$$" --network none --user "$(id -u):$(id -g)" \
    -v "$OUT":/work --entrypoint bash "$IMAGE" -lc "
set -euo pipefail
export $(echo $PARAMS) RESULTS_DIR=/work PRISM_JAVAMAXMEM=2g
mkdir -p /work/reach
cp /headless/pla/yaml/pladapt/rubis.yaml /headless/pla/yaml/pladapt/rubis-step.yaml /work/reach/
[ -f /work/weights ] || cp /headless/pla/thallium/default.weights /work/weights
cd /headless/pla/thallium
if [ ! -s /work/prism/rubis-exp.txt ]; then
    bash ./run_bounds.sh rubis /headless/pla/prism-games-2.0.beta3-linux64/bin > /work/bounds.log 2>&1
fi
CP='/headless/pla/thallium-bin:/headless/pla/thallium-lib/*'
J='java -Duser.language=en -Duser.country=US -cp '\$CP
while read -r W; do
    [ -n \"\$W\" ] || continue
    T=\${W//,/-}
    \$J thallium.impl.FuzzyValueCalculatorMain rubis /work/prism /work/fuzzy\$T \$W >> /work/fuzzy.log 2>&1
    \$J thallium.impl.GraphTrimmerMain rubis /work/reach/rubis.yaml /work/fuzzy\$T /work/trim\$T \$W >> /work/pareto.log 2>&1
done < /work/weights
"
cd "$HERE"
"$PY" thallium_trim.py "$OUT" | tee "$OUT/trim-summary.txt"
