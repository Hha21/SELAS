# syntax=docker/dockerfile:1.7
#
# selas-swim-pla:dev -- SWIM with the PLA-SDP adaptation manager that produced
# SWIM's shipped PLA and Thallium results (SWIM/tools/THALLIUM/*-0.sca).
#
# Built on the same image our other SWIM runs use, so OMNeT++ 5.4.1, gcc 5.4,
# Boost 1.58 and the compiled queueinglib are exactly those. On top of it:
#
#   * clayness/swim @ cfad67a (Clay Stevens, 2019-01-22 04:12 UTC): SWIM plus
#     ProactiveAdaptationManager, a port of pladapt's PLA-SDP. The shipped runs
#     are stamped 03:50-03:52 that morning and record the transitionsEvaluated
#     vector this commit adds.
#   * yaml-cpp 0.5.2 from Ubuntu 16.04, which the manager links against.
#   * pladapt's Alloy `reach` tool (clayness/pladapt @ 27d8d48, the last change
#     to reach/ before the runs) with Alloy 5.0.0.1 and yamlbeans 1.11, and
#     the SWIM reachability models from clayness/thallium @ fec1448.
#
# The PLA relation is generated at build time into /headless/pla/yaml/pladapt.
# The manager reads /headless/yaml/rubis{,-step}.yaml (a hard-coded path), so
# a run mounts or links the relation it wants there; see run_planners.sh.
#
#   docker build -t selas-swim-pla:dev experiments/swim_planners
FROM gabrielmoreno/swim:latest

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/omnetpp-5.4.1/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LD_LIBRARY_PATH=/opt/omnetpp-5.4.1/lib

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libyaml-cpp-dev=0.5.2-4ubuntu1~16.04.4 libyaml-cpp0.5v5=0.5.2-4ubuntu1~16.04.4 \
        openjdk-8-jdk-headless \
 && rm -rf /var/lib/apt/lists/*

# Sources, pinned by commit.
ADD https://github.com/clayness/swim.git#cfad67a71428215f87c820596bada3e140553b9c /headless/pla/swim
ADD https://github.com/clayness/pladapt.git#27d8d48b2cab39b28dc85265ae3c440aa0c18cfb /headless/pla/pladapt
ADD https://github.com/clayness/thallium.git#fec1448f33e2e42b93eb36eaec3dbedca0cac4e7 /headless/pla/thallium
# The jars pladapt's reach/build.sh downloads, pinned by hash.
ADD --checksum=sha256:84f7229838ee7604930b958486d7c65190923beabd814e859952cfb4558ae64f \
    https://github.com/AlloyTools/org.alloytools.alloy/releases/download/v5.0.0.1/Alloy-5.0.0.1.jar \
    /headless/pla/reach-lib/alloy5.0.jar
ADD --checksum=sha256:00c169df65f32282e26210539afbcdcf034fa170c42873993ecbfbc9d807c5e7 \
    https://github.com/EsotericSoftware/yamlbeans/releases/download/1.11/yamlbeans-1.11.jar \
    /headless/pla/reach-lib/yamlbeans-1.11.jar

WORKDIR /headless/pla
# SWIM's Makefile expects queueinglib beside the swim checkout: use the image's
# build of it, the one every other SWIM run of ours uses. A copy, not a symlink:
# OMNeT++ resolves NED paths through links, and package.ned's @namespace is then
# not found for a NED folder given by its linked name ("Class Sink not found").
RUN cp -a /headless/seams-swim/queueinglib /headless/pla/queueinglib

# Clay's fork predates SWIM's OMNeT++ 5.4.1 update (cps-sei/swim 44289ef); the
# one source change that update needed is applied as a patch. It does not change
# any computed value (see patches/README in the experiment's README.md).
COPY patches /headless/pla/patches
RUN cd swim && for p in /headless/pla/patches/swim-*.patch; do \
        echo "applying $p"; patch -p1 --forward < "$p" || exit 1; done

# Clay's src/Makefile was generated for OMNeT++ 5.2.1; regenerate it for 5.4.1
# with his extra library (-lyaml-cpp, which he added by hand).
RUN cd swim/src \
 && opp_makemake -f --deep -o swim -I. -Imodel/pladaptMock -I../../queueinglib \
        -L../libs -L../../queueinglib/ -lqueueinglib -lboost_serialization \
        -lboost_system -lboost_filesystem -lyaml-cpp -lpthread \
 && make MODE=release -j4 \
 && test -x swim

# reach: compile and generate the PLA relation.
COPY make_reach.sh /headless/pla/make_reach.sh
RUN cd reach-lib && jar xf alloy5.0.jar amd64-linux \
 && mkdir -p /headless/pla/reach-bin \
 && javac -nowarn -source 1.8 -target 1.8 -d /headless/pla/reach-bin \
        -cp alloy5.0.jar:yamlbeans-1.11.jar /headless/pla/pladapt/reach/src/reach/*.java \
 && chmod +x /headless/pla/make_reach.sh \
 && /headless/pla/make_reach.sh /headless/pla/yaml/pladapt \
 && chmod -R a+rX /headless/pla

# --- Thallium (clayness/thallium @ fec1448), for thallium_pipeline.sh ----------
# PRISM-games 2.0.beta3 (the release current in 2019) for the utility bounds,
# and the jars thallium's build.gradle names, from Maven Central.
ADD --checksum=sha256:cc33bd5f5faf1eea8822044960a92f381e2221147229cb4478e92e0fc5c67f26 \
    https://www.prismmodelchecker.org/dl/prism-games-2.0.beta3-linux64.tar.gz /tmp/prism-games.tar.gz
ADD --checksum=sha256:dac807f65b07698ff39b1b07bfef3d87ae3fd46d91bbf8a2bc02b2a831616f68 \
    https://repo1.maven.org/maven2/org/apache/commons/commons-lang3/3.8.1/commons-lang3-3.8.1.jar /headless/pla/thallium-lib/
ADD --checksum=sha256:2351c3eba73a545db9079f5d6d768347ad72666537362c8220fe3e950a55a864 \
    https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-databind/2.9.8/jackson-databind-2.9.8.jar /headless/pla/thallium-lib/
ADD --checksum=sha256:d934dab0bd48994eeea2c1b493cb547158a338a80b58c4fbc8e85fb0905e105f \
    https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-core/2.9.8/jackson-core-2.9.8.jar /headless/pla/thallium-lib/
ADD --checksum=sha256:45d32ac61ef8a744b464c54c2b3414be571016dd46bfc2bec226761cf7ae457a \
    https://repo1.maven.org/maven2/com/fasterxml/jackson/core/jackson-annotations/2.9.0/jackson-annotations-2.9.0.jar /headless/pla/thallium-lib/
ADD --checksum=sha256:ec6c80f083d9f0f5530bae59fe7ce359e07b8b562d7e3dbe548e33c284deed22 \
    https://repo1.maven.org/maven2/com/fasterxml/jackson/dataformat/jackson-dataformat-yaml/2.9.8/jackson-dataformat-yaml-2.9.8.jar /headless/pla/thallium-lib/
ADD --checksum=sha256:13009fb5ede3cf2be5a8d0f1602155aeaa0ce5ef5f9366892bd258d8d3d4d2b1 \
    https://repo1.maven.org/maven2/org/yaml/snakeyaml/1.23/snakeyaml-1.23.jar /headless/pla/thallium-lib/
RUN tar xzf /tmp/prism-games.tar.gz -C /headless/pla && rm /tmp/prism-games.tar.gz \
 && cd /headless/pla/prism-games-2.0.beta3-linux64 && ./install.sh > /dev/null \
 && mkdir -p /headless/pla/thallium-bin \
 && javac -nowarn -source 1.8 -target 1.8 -encoding UTF-8 -d /headless/pla/thallium-bin \
        -cp "/headless/pla/thallium-lib/*" $(find /headless/pla/thallium/java/src/main/java -name '*.java') \
 && chmod -R a+rX /headless/pla

WORKDIR /headless/pla/swim/simulations/swim_sa
